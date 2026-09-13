"""Phase 1: turn raw pulls into the comparison set.

Everything ownership-related is an interval, never a number. SteamSpy stopped
reporting exact owner counts when Steam's privacy changes landed, so a row says
"1,000,000 .. 2,000,000" and the honest move is to carry that interval all the
way through instead of silently collapsing it on the first line of analysis.

Checkpoint decisions this module implements (Eileen, 2026-09-13):
  - owner ranges: interval midpoint for the headline, every owner-dependent
    result re-run at the lower and upper bound
  - inclusion: released 2015 or later, owner midpoint at or above 20,000
  - headline metric: median playtime forever; robustness check: CCU per owner

Run: python -m src.cohort report
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter
from dataclasses import dataclass

from src import config

# SteamSpy formats owners as "1,000,000 .. 2,000,000". Tolerant of the separator
# drifting (extra spaces, a non-breaking space) because the string is scraped
# presentation, not a contract.
_OWNER_SPLIT = re.compile(r"\.\.")
_DIGITS = re.compile(r"\d+")
_YEAR = re.compile(r"\b(19|20)\d{2}\b")


class OwnerParseError(ValueError):
    pass


@dataclass(frozen=True)
class OwnerRange:
    """An owner count as SteamSpy actually knows it: a band, not a number."""

    lower: int
    upper: int

    @property
    def midpoint(self) -> float:
        return (self.lower + self.upper) / 2

    def at(self, bound: str) -> float:
        if bound == "lower":
            return float(self.lower)
        if bound == "upper":
            return float(self.upper)
        if bound == "midpoint":
            return self.midpoint
        raise ValueError(f"unknown bound: {bound}")


def parse_owner_range(raw: str) -> OwnerRange:
    """'1,000,000 .. 2,000,000' -> OwnerRange(1000000, 2000000)."""
    if raw is None:
        raise OwnerParseError("owners field was absent")

    parts = _OWNER_SPLIT.split(str(raw))
    if len(parts) != 2:
        raise OwnerParseError(f"expected two bounds, got {raw!r}")

    bounds = []
    for part in parts:
        digits = "".join(_DIGITS.findall(part))
        if not digits:
            raise OwnerParseError(f"no digits in bound {part!r} of {raw!r}")
        bounds.append(int(digits))

    lower, upper = bounds
    if upper < lower:
        raise OwnerParseError(f"upper bound below lower in {raw!r}")
    return OwnerRange(lower, upper)


def format_owner_range(owners: OwnerRange) -> str:
    """Inverse of parse_owner_range, in SteamSpy's own formatting."""
    return f"{owners.lower:,} .. {owners.upper:,}"


# --- storefront field extraction --------------------------------------------


def release_year(store_entry: dict) -> int | None:
    """Year from the storefront's free-text release date, or None if unusable.

    The field is presentation text ("12 Aug, 2024", "Q3 2025", "Coming soon"),
    so only the year is trusted. Unreleased and undated apps return None and are
    excluded, with the count reported rather than buried.
    """
    if not store_entry.get("success"):
        return None
    release = (store_entry.get("data") or {}).get("release_date") or {}
    if release.get("coming_soon"):
        return None
    match = _YEAR.search(str(release.get("date", "")))
    return int(match.group(0)) if match else None


def price_aud(store_entry: dict) -> float | None:
    """Current AUD price. 0.0 for free apps, None when the storefront won't say."""
    if not store_entry.get("success"):
        return None
    data = store_entry.get("data") or {}
    if data.get("is_free"):
        return 0.0
    overview = data.get("price_overview")
    if not overview:
        # Paid app with no price block: usually delisted-but-listed, or a regional
        # gap. Not guessed at — excluded, and counted as such.
        return None
    if overview.get("currency") != "AUD":
        # cc=au should guarantee AUD. If it ever doesn't, the band boundaries would
        # silently mean something else, so refuse rather than convert.
        return None
    return overview["final"] / 100.0


def genres(store_entry: dict) -> list[str]:
    if not store_entry.get("success"):
        return []
    return [g["description"] for g in (store_entry.get("data") or {}).get("genres", [])]


def price_band(price: float) -> str:
    """AUD band label for a paid game."""
    for low, high in config.PRICE_BANDS_AUD:
        if high is None:
            if price >= low:
                return f"{low}+"
        elif low <= price < high:
            return f"{low}-{high}"
    raise ValueError(f"price outside every band: {price}")


# --- the comparison set -----------------------------------------------------


def primary_genre_from_tags(tags: dict) -> str:
    """The highest-voted tag that the genre vocabulary actually recognises.

    Not simply the top tag. Dota 2's top tag is "Free to Play" at 60,040 votes,
    which would make the strata a restatement of the pricing model - see the
    reasoning in config. Only tags in GENRE_TAGS are eligible, and business-model
    tags are excluded by name on top of that.

    Ties break alphabetically so the assignment is deterministic: the same tag
    dictionary always produces the same stratum, run to run.
    """
    eligible = {
        tag: votes
        for tag, votes in (tags or {}).items()
        if tag in config.GENRE_TAGS and tag not in config.PRICING_MODEL_TAGS
    }
    if not eligible:
        return config.UNCLASSIFIED_GENRE

    # Specificity beats votes. Steam's umbrella tags ("Action", "Casual") out-vote
    # the informative ones on most games, so a pure highest-votes rule put 65% of
    # the audit sample into a broad bucket - no better than the storefront genres
    # this replaced. Umbrellas are a fallback, reached only when a game has
    # nothing more specific.
    specific = {t: v for t, v in eligible.items() if t not in config.BROAD_GENRE_TAGS}
    pool = specific or eligible

    return max(sorted(pool), key=lambda tag: pool[tag])


@dataclass(frozen=True)
class Game:
    appid: int
    name: str
    owners: OwnerRange
    median_forever: int
    ccu: int
    pricing: str  # "f2p" or "paid"
    price: float
    year: int
    genres: tuple[str, ...]
    tags: tuple[tuple[str, int], ...] = ()

    @property
    def primary_genre(self) -> str:
        """The stratum. Tag-derived, because that is where the confound lives."""
        return primary_genre_from_tags(dict(self.tags))

    @property
    def store_genre(self) -> str:
        """Steam's own broad genre. Kept for the coarse-vs-fine comparison.

        Showing the correction at both resolutions is worth a chart: if the naive
        gap survives Steam's three buckets but dies under tags, that difference is
        itself the argument for why the tag-level correction was necessary.
        """
        return self.genres[0] if self.genres else "Uncategorised"

    @property
    def classified(self) -> bool:
        return self.primary_genre != config.UNCLASSIFIED_GENRE

    def ccu_per_owner(self, bound: str) -> float:
        return self.ccu / self.owners.at(bound)


def classify_pricing(store_entry: dict) -> str | None:
    """'f2p', 'paid', or None when the storefront gives nothing to go on.

    The storefront's is_free flag is the authority, not price == 0, because a
    temporarily-free promotion also reads as zero. One thing this cannot see: a
    paid game that went free-to-play later reads as F2P today, since both sources
    report current state, not launch state. That is a stated limitation, not a
    bug to paper over - it is also exactly the publisher decision the project is
    about, so it belongs in the write-up.
    """
    if not store_entry.get("success"):
        return None
    data = store_entry.get("data") or {}
    if data.get("is_free"):
        return "f2p"
    price = price_aud(store_entry)
    return "paid" if price is not None else None


def candidate_appids(catalogue: dict) -> list[int]:
    """Pre-filter the catalogue before paying 2.5s per app to enrich it.

    Only the owner floor is applied here - release year and genre live on the
    storefront, which is the thing being paid for. Applied at the *upper* bound
    so nothing that could survive the real filter at any bound is discarded
    before it has been looked at.
    """
    out = []
    for appid, row in catalogue.items():
        try:
            owners = parse_owner_range(row.get("owners"))
        except OwnerParseError:
            continue
        if owners.upper > config.MIN_OWNERS_MIDPOINT:
            out.append(int(appid))
    return sorted(out)


def build_cohort(records: dict, bound: str = "midpoint") -> tuple[list[Game], Counter]:
    """Apply the inclusion rule at one owner bound. Returns (games, exclusions).

    The cohort itself moves with the bound: the owner floor is applied to an
    interval, so a game sitting on the boundary is in at the upper bound and out
    at the lower one. Reporting one cohort size would hide that.
    """
    games: list[Game] = []
    excluded: Counter = Counter()

    for appid, record in records.items():
        spy = record.get("steamspy") or {}
        store = record.get("store") or {}

        try:
            owners = parse_owner_range(spy.get("owners"))
        except OwnerParseError:
            excluded["unparseable owners"] += 1
            continue

        # Strict: the bottom band is 0 .. 20,000, so its upper bound is exactly
        # the floor. A >= comparison would readmit the whole band at the upper
        # sensitivity bound, which is the opposite of dropping it.
        if owners.at(bound) <= config.MIN_OWNERS_MIDPOINT:
            excluded["below owner floor"] += 1
            continue

        year = release_year(store)
        if year is None:
            excluded["no usable release date"] += 1
            continue
        if year < config.MIN_RELEASE_YEAR:
            excluded[f"released before {config.MIN_RELEASE_YEAR}"] += 1
            continue

        store_genres = genres(store)
        if any(g in config.NON_GAME_STORE_GENRES for g in store_genres):
            excluded["not a game (software)"] += 1
            continue

        pricing = classify_pricing(store)
        if pricing is None:
            excluded["pricing not determinable"] += 1
            continue

        price = price_aud(store)
        if price is None:
            excluded["pricing not determinable"] += 1
            continue

        median = spy.get("median_forever")
        if median is None:
            excluded["no playtime median"] += 1
            continue

        games.append(
            Game(
                appid=int(appid),
                name=spy.get("name", f"app {appid}"),
                owners=owners,
                median_forever=int(median),
                ccu=int(spy.get("ccu") or 0),
                pricing=pricing,
                price=price,
                year=year,
                genres=tuple(store_genres),
                # Tags only come from the per-app SteamSpy call, never from the
                # `all` rows - which is what justifies paying for that call.
                tags=tuple(sorted((spy.get("tags") or {}).items())),
            )
        )

    return games, excluded


def split_by_pricing(games: list[Game]) -> dict[str, list[Game]]:
    """F2P and paid, as disjoint sets by construction - one pass, one label each."""
    out: dict[str, list[Game]] = {"f2p": [], "paid": []}
    for game in games:
        out[game.pricing].append(game)
    return out


def cohort_report(records: dict) -> str:
    """Phase 1's deliverable: how many games survive, F2P vs paid, at each bound."""
    lines = [
        "Comparison set - released "
        f"{config.MIN_RELEASE_YEAR}+, owner floor {config.MIN_OWNERS_MIDPOINT:,}",
        "",
    ]
    for bound in config.OWNER_BOUNDS:
        games, excluded = build_cohort(records, bound)
        split = split_by_pricing(games)
        lines.append(
            f"{bound:>9} bound: {len(games):,} games "
            f"({len(split['f2p']):,} F2P / {len(split['paid']):,} paid)"
        )
        for reason, count in excluded.most_common():
            lines.append(f"            excluded, {reason}: {count:,}")
        lines.append("")
    return "\n".join(lines)


def unclassified_top_tags(games: list[Game], limit: int = 30) -> list[tuple[str, int]]:
    """For the games the vocabulary missed, the tag they would have fallen into.

    This is the honest check on a hand-written allowlist. It names exactly which
    tags to add next, ranked by how many games each would rescue, so the
    vocabulary grows from what the catalogue actually contains rather than from
    what seemed likely before the data arrived.
    """
    counter: Counter = Counter()
    for game in games:
        if game.classified:
            continue
        tags = {t: v for t, v in game.tags if t not in config.PRICING_MODEL_TAGS}
        if not tags:
            counter["(no tags at all)"] += 1
            continue
        counter[max(sorted(tags), key=lambda t: tags[t])] += 1
    return counter.most_common(limit)


def coverage_report(games: list[Game]) -> str:
    """How much of the cohort the genre vocabulary classifies, and what it misses."""
    by_pricing = split_by_pricing(games)
    lines = [f"Genre vocabulary: {len(config.GENRE_TAGS)} tags", ""]

    for label, group in (("all", games), ("f2p", by_pricing["f2p"]), ("paid", by_pricing["paid"])):
        if not group:
            continue
        classified = sum(1 for g in group if g.classified)
        share = 100 * classified / len(group)
        lines.append(f"{label:>5}: {classified:,}/{len(group):,} classified ({share:.1f}%)")

    # A coverage gap that falls unevenly on F2P vs paid is a bias, not just a
    # gap - it would thin one side of every comparison. Worth seeing side by side.
    lines.append("")
    lines.append("Top tags among unclassified games (candidates for the vocabulary):")
    for tag, count in unclassified_top_tags(games):
        lines.append(f"    {count:>6,}  {tag}")

    return "\n".join(lines)


def _game_to_dict(game: Game) -> dict:
    return {
        "appid": game.appid,
        "name": game.name,
        "owners": format_owner_range(game.owners),
        "median_forever": game.median_forever,
        "ccu": game.ccu,
        "pricing": game.pricing,
        "price": game.price,
        "year": game.year,
        "genres": list(game.genres),
        "tags": [list(t) for t in game.tags],
    }


def _game_from_dict(raw: dict) -> Game:
    return Game(
        appid=raw["appid"],
        name=raw["name"],
        owners=parse_owner_range(raw["owners"]),
        median_forever=raw["median_forever"],
        ccu=raw["ccu"],
        pricing=raw["pricing"],
        price=raw["price"],
        year=raw["year"],
        genres=tuple(raw["genres"]),
        tags=tuple((t[0], t[1]) for t in raw["tags"]),
    )


def load_cohort(records_loader, bound: str = "midpoint", refresh: bool = False) -> list[Game]:
    """The built cohort, cached as one file so the raw archive is parsed once.

    Building from raw means reading and JSON-parsing every cached payload - about
    400 MB of storefront responses - which takes ten minutes and produces the
    same answer every time. The analysis gets re-run constantly while tuning, so
    the built cohort is written out once per bound and reloaded after.

    `refresh=True` rebuilds from raw. Do that whenever the enrichment has fetched
    anything new, or the inclusion rule changes - a stale cohort is a worse
    failure than a slow one, because it is silent.
    """
    path = config.PROCESSED_DATA_DIR / f"cohort_{bound}.json"
    if path.exists() and not refresh:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [_game_from_dict(g) for g in raw["games"]]

    games, excluded = build_cohort(records_loader(), bound)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"bound": bound, "excluded": dict(excluded), "games": [_game_to_dict(g) for g in games]}),
        encoding="utf-8",
    )
    return games


def audit_sample(catalogue: dict, size: int | None = None) -> list[int]:
    """A deterministic random sample of candidate appids, for the coverage audit.

    Auditing the whole candidate set means enriching tens of thousands of apps at
    ~2.5s each. A sample is enough for the question the audit asks - which tags
    the vocabulary is missing - because a tag worth adding is a frequent one, and
    frequent tags appear in a sample of a thousand.

    Seeded, and the sample is drawn from the sorted candidate list, so the same
    catalogue always yields the same sample. That matters: its enrichment is
    cached, so the audit run is not wasted work but a down payment on the full
    pull.
    """
    size = size or config.AUDIT_SAMPLE_SIZE
    candidates = candidate_appids(catalogue)
    if len(candidates) <= size:
        return candidates
    return sorted(random.Random(config.RANDOM_SEED).sample(candidates, size))


def _load_cohort(sample_size: int | None = None) -> list[Game]:
    from src import steamspy_fetch

    catalogue = steamspy_fetch.fetch_catalogue()
    appids = audit_sample(catalogue, sample_size) if sample_size else candidate_appids(catalogue)
    print(f"{len(appids):,} apps to enrich (~{len(appids) * 2.5 / 60:.0f} min if uncached)", flush=True)
    records = steamspy_fetch.enrich(appids)
    games, _ = build_cohort(records)
    return games


def main(argv: list[str]) -> int:
    if argv and argv[0] == "coverage":
        # `coverage` samples by default; `coverage full` audits every candidate.
        sample_size = None if argv[1:2] == ["full"] else config.AUDIT_SAMPLE_SIZE
        print(coverage_report(_load_cohort(sample_size)))
        return 0

    if argv and argv[0] == "report":
        from src import steamspy_fetch

        catalogue = steamspy_fetch.fetch_catalogue()
        candidates = candidate_appids(catalogue)
        records = steamspy_fetch.enrich(candidates)
        print(cohort_report(records))
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
