"""Phase 2: the engagement metric, rebuilt on Steam review payloads.

Why this exists. The spec's headline metric was SteamSpy's median playtime
forever. On 2026-09-13 that field was found to be zero for every one of the
1,000 apps on the first `all` page and for both spot-checked apps - SteamSpy
still serves the field, it just carries nothing. Steam's own review endpoint
does carry per-player playtime (`author.playtime_forever`), so the metric is
taken from there instead.

What that costs, stated rather than absorbed:

  - **Reviewer selection bias.** A median over reviewers is not a median over
    owners. People who write reviews have played more than people who don't,
    so every playtime figure here is biased upward. It is comparable *across*
    games, which is what the F2P-vs-paid question needs, but it is not an
    estimate of what a typical owner played.
  - **Recent-reviewer skew.** Pages come back newest-first, so a long-lived
    game's sample is its current reviewers, not its launch cohort. The
    alternative sort is by helpfulness, which re-orders as votes accrue and
    would make the pull unreproducible; reproducibility won.
  - **Sampling.** A review pull per game is seconds, and the cohort is
    thousands of games, so playtime runs on a stratified sample by (pricing,
    primary genre). CCU per owner still runs on the whole cohort.

Run: python -m src.playtime one 1245620
     python -m src.playtime sample
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass

import requests

from src import console
from src import config, cohort
from src.steamspy_fetch import _PACER, _http_get, _write_json, SteamAPIError


@dataclass(frozen=True)
class PlaytimeSample:
    """One game's playtime sample. `median` is None when too few reviewers."""

    appid: int
    reviewers: int
    median_minutes: float | None
    zero_playtime: int

    @property
    def usable(self) -> bool:
        return self.median_minutes is not None


def fetch_review_page(appid: int, cursor: str = "*", session: requests.Session | None = None) -> dict:
    """One page of reviews, cached on disk by (appid, cursor)."""
    # Cursors contain characters that are not filesystem-safe; index the cache by
    # page order instead, which is stable because filter=recent is deterministic.
    safe = "".join(c if c.isalnum() else "_" for c in cursor)[:40]
    path = config.REVIEW_CACHE_DIR / str(appid) / f"{safe}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    # Same key as fetch_store on purpose: appreviews and appdetails are both
    # store.steampowered.com, and a rate limit belongs to a host, not an endpoint.
    # With separate keys two concurrent pullers would each assume the whole
    # budget and together halve the spacing.
    _PACER.wait("store", config.REVIEW_DELAY_SECONDS)
    payload = _http_get(
        config.STEAM_APPREVIEWS_URL.format(appid=appid),
        {
            "json": 1,
            "filter": config.REVIEW_FILTER,
            "language": config.REVIEW_LANGUAGE,
            "review_type": config.REVIEW_TYPE,
            "purchase_type": config.REVIEW_PURCHASE_TYPE,
            "num_per_page": config.REVIEWS_PER_PAGE,
            "cursor": cursor,
        },
        session,
    )
    _write_json(path, payload)
    return payload


def collect_playtimes(appid: int, session: requests.Session | None = None) -> dict[str, int]:
    """{steamid: playtime_forever} for one game, up to the target sample size.

    Keyed by steamid because Steam's cursor paging can repeat a review across
    page boundaries, and a duplicated reviewer would be counted twice in the
    median.
    """
    playtimes: dict[str, int] = {}
    cursor = "*"

    for _ in range(config.MAX_REVIEW_PAGES_PER_GAME):
        payload = fetch_review_page(appid, cursor, session)
        reviews = payload.get("reviews") or []
        if not reviews:
            break

        for review in reviews:
            author = review.get("author") or {}
            steamid = author.get("steamid")
            minutes = author.get("playtime_forever")
            if steamid is None or minutes is None:
                continue
            playtimes[steamid] = int(minutes)

        if len(playtimes) >= config.TARGET_REVIEWS_PER_GAME:
            break

        next_cursor = payload.get("cursor")
        # Steam sometimes returns the same cursor forever instead of an empty
        # page at the end of a listing. Without this check that is a hard loop.
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor

    return playtimes


def sample_playtime(appid: int, session: requests.Session | None = None) -> PlaytimeSample:
    """Median playtime in minutes for one game, or None if too few reviewers."""
    playtimes = collect_playtimes(appid, session)
    values = list(playtimes.values())

    # Kept in the count, not filtered out: a reviewer with zero minutes is real
    # (refunded, family-shared, reviewed without launching) and dropping them
    # would quietly lift every median.
    zeros = sum(1 for v in values if v == 0)

    if len(values) < config.MIN_REVIEWERS_FOR_MEDIAN:
        return PlaytimeSample(appid, len(values), None, zeros)
    return PlaytimeSample(appid, len(values), statistics.median(values), zeros)


def stratify(games: list[cohort.Game]) -> dict[tuple[str, str], list[cohort.Game]]:
    """Group the cohort into (pricing, primary genre) cells."""
    cells: dict[tuple[str, str], list[cohort.Game]] = defaultdict(list)
    for game in games:
        cells[(game.pricing, game.primary_genre)].append(game)
    return dict(cells)


def stratified_sample(games: list[cohort.Game]) -> tuple[list[cohort.Game], dict[tuple[str, str], int]]:
    """Pick up to GAMES_PER_STRATUM from each cell. Returns (sample, cell sizes).

    Deterministic: seeded, and the pool is sorted by appid before sampling, so
    the same cohort always yields the same sample and the pull stays cacheable.

    Cells thinner than MIN_GAMES_PER_STRATUM are still sampled and returned -
    excluding them here would hide how thin they are. The cell sizes come back
    alongside so the analysis can refuse to draw a within-genre conclusion from
    a cell of three.
    """
    rng = random.Random(config.RANDOM_SEED)
    cells = stratify(games)
    sample: list[cohort.Game] = []

    for key in sorted(cells):
        pool = sorted(cells[key], key=lambda g: g.appid)
        take = min(config.GAMES_PER_STRATUM, len(pool))
        sample.extend(rng.sample(pool, take))

    return sorted(sample, key=lambda g: g.appid), {k: len(v) for k, v in cells.items()}


def thin_cells(cell_sizes: dict[tuple[str, str], int]) -> list[tuple[str, str]]:
    """Cells too small to support a within-genre claim. Reported, not deleted."""
    return sorted(k for k, n in cell_sizes.items() if n < config.MIN_GAMES_PER_STRATUM)


def pull_playtimes(sample, session=None):
    """Pull each game's playtime. Returns (results, failed appids, aborted).

    Two failure modes that look identical per-request and must not be treated
    alike. A single app failing is routine - delisted, region-locked, a blip -
    and ending a three-hour run over one of them wastes everything after it. The
    network being gone is not routine: every remaining game would burn its full
    retry budget, roughly three minutes each, so the run would spend hours
    marking the whole sample failed and cache nothing to resume from.

    Consecutive failures separate them. Isolated failures are recorded and
    stepped over; a run of them stops the pull immediately so the cache stays a
    clean partial result that a restart can continue from.
    """
    results: dict[int, PlaytimeSample] = {}
    failed: list[int] = []
    consecutive = 0

    for index, game in enumerate(sample, start=1):
        try:
            result = sample_playtime(game.appid, session)
        except SteamAPIError as exc:
            failed.append(game.appid)
            consecutive += 1
            print(f"{index}/{len(sample)} {game.name}: FAILED ({exc})", flush=True)
            if consecutive >= config.MAX_CONSECUTIVE_FAILURES:
                print(
                    f"stopping after {consecutive} consecutive failures — the network is "
                    f"probably down. {len(results):,} games are cached; re-run to continue.",
                    flush=True,
                )
                return results, failed, True
            continue

        consecutive = 0
        results[game.appid] = result
        print(f"{index}/{len(sample)} {game.name}: {result}", flush=True)

    return results, failed, False


def main(argv: list[str]) -> int:
    console.use_utf8()
    if argv and argv[0] == "one":
        result = sample_playtime(int(argv[1]))
        print(result)
        return 0

    if argv and argv[0] == "sample":
        from src import steamspy_fetch

        def load_records():
            catalogue = steamspy_fetch.fetch_catalogue()
            return steamspy_fetch.enrich(cohort.candidate_appids(catalogue))

        games = cohort.load_cohort(load_records, refresh="--refresh" in argv)
        sample, sizes = stratified_sample(games)
        print(f"{len(games)} games in cohort, {len(sizes)} cells, {len(sample)} sampled")
        for key in thin_cells(sizes):
            print(f"  thin cell (reported, not analysed): {key} = {sizes[key]}")

        with requests.Session() as session:
            results, failed, aborted = pull_playtimes(sample, session)

        print()
        print(f"{len(results):,} pulled, {len(failed)} failed"
              + (" - ABORTED, see above" if aborted else ""))
        return 1 if aborted else 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
