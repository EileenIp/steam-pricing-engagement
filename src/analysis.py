"""Phase 2b: the comparison, and the correction that is the point of the project.

The order matters. The naive F2P-vs-paid comparison goes first, not because it is
the answer but because it is the answer everyone expects; the within-genre
correction is then shown against it, so the reader watches the gap move. If the
correction kills the naive result, that is the finding.

Statistics. Playtime and CCU-per-owner are both savagely skewed - a handful of
4,000-hour players and a handful of persistent-world games drag any mean off the
map - so every comparison is rank-based: Mann-Whitney U, with Cliff's delta as
the effect size. Delta is reported as the primary number and p as secondary, on
purpose: with cells as small as 8 games the normal approximation to U is shaky,
and an effect size with a visible cell count is more honest than a p-value that
implies more precision than the cell can carry.

Cliff's delta reads directly: +1 means every F2P game out-plays every paid game,
-1 the reverse, 0 no separation. It is also the same quantity as the rank-biserial
correlation, so it can be quoted either way.

Run: python -m src.analysis sample          (the audit sample, CCU metric)
     python -m src.analysis sample playtime (needs the playtime pull first)
"""
from __future__ import annotations

import math
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass

from src import config, cohort


# --- rank statistics --------------------------------------------------------


def _ranks(values: list[float]) -> list[float]:
    """Ranks with ties averaged, which is what the tie correction below assumes."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        stop = index
        while stop + 1 < len(order) and values[order[stop + 1]] == values[order[index]]:
            stop += 1
        average = (index + stop) / 2 + 1
        for position in range(index, stop + 1):
            ranks[order[position]] = average
        index = stop + 1
    return ranks


def _fmt(value: float | None) -> str:
    """Format across the magnitudes these metrics span.

    Playtime medians are thousands of minutes; CCU per owner is ~0.0001. A single
    format string rounds one of them to nothing - which it did, printing every
    CCU median as "0" and hiding that the metric was working.
    """
    if value is None:
        return "-"
    if value == 0:
        return "0"
    if abs(value) >= 100:
        return f"{value:,.0f}"
    if abs(value) >= 0.01:
        return f"{value:,.3f}"
    return f"{value:.2e}"


@dataclass(frozen=True)
class Comparison:
    """One F2P-vs-paid comparison on one metric."""

    label: str
    n_f2p: int
    n_paid: int
    median_f2p: float | None
    median_paid: float | None
    delta: float | None       # Cliff's delta: + means F2P higher
    p_value: float | None
    tied_at_zero: float = 0.0  # share of values equal to zero, across both groups

    @property
    def usable(self) -> bool:
        """Whether the cell is big enough to carry a within-genre claim at all."""
        return (
            self.n_f2p >= config.MIN_GAMES_PER_STRATUM
            and self.n_paid >= config.MIN_GAMES_PER_STRATUM
        )

    def __str__(self) -> str:
        if self.delta is None:
            return f"{self.label:<24} n={self.n_f2p:>4}/{self.n_paid:<4}  (too thin)"
        flag = "" if self.usable else "  [thin]"
        # Heavy ties at a single value gut a rank test's power, so the share is
        # printed next to the result rather than left for the reader to discover.
        ties = f"  ties@0 {self.tied_at_zero:.0%}" if self.tied_at_zero >= 0.2 else ""
        return (
            f"{self.label:<24} n={self.n_f2p:>4}/{self.n_paid:<4} "
            f"median {_fmt(self.median_f2p):>9} vs {_fmt(self.median_paid):>9}  "
            f"delta {self.delta:+.3f}  p {self.p_value:.3g}{flag}{ties}"
        )


def mann_whitney(group_a: list[float], group_b: list[float]) -> tuple[float, float, float]:
    """(U for group_a, Cliff's delta, two-sided p). Empty group -> nan.

    Normal approximation with tie correction and a continuity correction. Written
    out rather than pulled from scipy: it is thirty lines, it keeps the project's
    dependencies to three, and being able to say exactly what the test does is
    worth more in an interview than importing it.

    The approximation degrades below roughly 20 per group, which is why delta is
    the headline and every cell prints its n.
    """
    n_a, n_b = len(group_a), len(group_b)
    if n_a == 0 or n_b == 0:
        return math.nan, math.nan, math.nan

    combined = group_a + group_b
    ranks = _ranks(combined)
    rank_sum_a = sum(ranks[:n_a])

    u_a = rank_sum_a - n_a * (n_a + 1) / 2
    delta = (2 * u_a) / (n_a * n_b) - 1

    total = n_a + n_b
    counts: dict[float, int] = defaultdict(int)
    for value in combined:
        counts[value] += 1
    tie_term = sum(t**3 - t for t in counts.values())

    if total < 2:
        return u_a, delta, math.nan
    variance = (n_a * n_b / 12) * ((total + 1) - tie_term / (total * (total - 1)))
    if variance <= 0:
        # Every value identical: no separation to detect.
        return u_a, delta, 1.0

    mean_u = n_a * n_b / 2
    z = (abs(u_a - mean_u) - 0.5) / math.sqrt(variance)
    z = max(z, 0.0)
    p_value = math.erfc(z / math.sqrt(2))

    return u_a, delta, p_value


# --- metrics ----------------------------------------------------------------


def metric_accessor(metric: str, playtimes: dict | None = None):
    """A function (game, bound) -> value or None.

    Note which metrics move with the owner bound and which do not. CCU per owner
    divides by the owner interval, so it shifts at every bound. Review-derived
    playtime does not - it is a median over reviewers, with no owner term. The
    owner interval still moves the playtime comparison, but only through cohort
    membership, which is a subtler effect and worth saying out loud rather than
    letting a flat sensitivity band imply the metric was never uncertain.
    """
    if metric == "ccu_per_owner":
        return lambda game, bound: game.ccu_per_owner(bound)

    if metric == "playtime":
        if playtimes is None:
            raise ValueError("playtime metric needs the review pull: python -m src.playtime sample")

        def accessor(game, bound):
            sample = playtimes.get(game.appid)
            return sample.median_minutes if sample and sample.usable else None

        return accessor

    raise ValueError(f"unknown metric: {metric}")


def compare(games: list[cohort.Game], accessor, bound: str, label: str) -> Comparison:
    """One F2P-vs-paid comparison over a set of games."""
    split = cohort.split_by_pricing(games)
    values = {
        pricing: [v for v in (accessor(g, bound) for g in group) if v is not None]
        for pricing, group in split.items()
    }
    f2p, paid = values["f2p"], values["paid"]

    if not f2p or not paid:
        return Comparison(label, len(f2p), len(paid), None, None, None, None)

    _, delta, p_value = mann_whitney(f2p, paid)
    combined = f2p + paid
    zeros = sum(1 for v in combined if v == 0) / len(combined)

    return Comparison(
        label,
        len(f2p),
        len(paid),
        statistics.median(f2p),
        statistics.median(paid),
        delta,
        p_value,
        zeros,
    )


# --- the three views --------------------------------------------------------


def naive(games: list[cohort.Game], accessor, bound: str) -> Comparison:
    """F2P vs paid across the whole cohort. The answer that is probably wrong."""
    return compare(games, accessor, bound, "ALL GAMES (naive)")


def within_genre(games: list[cohort.Game], accessor, bound: str) -> list[Comparison]:
    """The same comparison inside each genre. Sorted widest cell first."""
    by_genre: dict[str, list[cohort.Game]] = defaultdict(list)
    for game in games:
        if game.classified:
            by_genre[game.primary_genre].append(game)

    results = [compare(group, accessor, bound, name) for name, group in by_genre.items()]
    return sorted(results, key=lambda c: -(c.n_f2p + c.n_paid))


def genre_adjusted_delta(comparisons: list[Comparison]) -> tuple[float | None, int]:
    """Pool the within-genre deltas into one number, and say how many cells it used.

    Weighted by n_f2p * n_paid, the number of pairwise comparisons each stratum
    actually contributes - the standard weighting for combining rank-biserial
    correlations, and the one that stops a genre with four games carrying the same
    weight as one with four hundred.

    Only cells that clear the minimum on both sides are pooled. A stratified
    estimate built from cells too thin to interpret individually would be a
    laundered version of the same noise.
    """
    usable = [c for c in comparisons if c.usable and c.delta is not None]
    if not usable:
        return None, 0

    weights = [c.n_f2p * c.n_paid for c in usable]
    pooled = sum(c.delta * w for c, w in zip(usable, weights)) / sum(weights)
    return pooled, len(usable)


def price_bands(games: list[cohort.Game], accessor, bound: str) -> list[tuple[str, int, float | None]]:
    """Engagement by AUD price band, paid games only. (band, n, median)."""
    bands: dict[str, list[float]] = defaultdict(list)
    for game in games:
        if game.pricing != "paid":
            continue
        value = accessor(game, bound)
        if value is not None:
            bands[cohort.price_band(game.price)].append(value)

    ordered = [f"{low}-{high}" if high else f"{low}+" for low, high in config.PRICE_BANDS_AUD]
    return [
        (band, len(bands[band]), statistics.median(bands[band]) if bands[band] else None)
        for band in ordered
    ]


def release_cohorts(games: list[cohort.Game], accessor, bound: str) -> list[Comparison]:
    """The comparison by release year: is any F2P edge growing or shrinking?"""
    by_year: dict[int, list[cohort.Game]] = defaultdict(list)
    for game in games:
        by_year[game.year].append(game)
    return [compare(by_year[year], accessor, bound, str(year)) for year in sorted(by_year)]


# --- report -----------------------------------------------------------------


def report(games: list[cohort.Game], metric: str, playtimes: dict | None = None) -> str:
    """The whole Phase 2b view, at every owner bound."""
    accessor = metric_accessor(metric, playtimes)
    lines = [
        f"metric: {metric}   cohort: {len(games):,} games",
        "delta is Cliff's delta, + means F2P higher. n is f2p/paid.",
        "",
    ]

    for bound in config.OWNER_BOUNDS:
        lines.append(f"=== owner bound: {bound} ===")

        naive_result = naive(games, accessor, bound)
        lines.append(str(naive_result))

        genres = within_genre(games, accessor, bound)
        pooled, cells = genre_adjusted_delta(genres)

        if pooled is None:
            lines.append(
                f"  genre-adjusted: no genre has {config.MIN_GAMES_PER_STRATUM}+ games "
                "of each pricing model - the correction cannot be made at this scale"
            )
        else:
            moved = pooled - (naive_result.delta or 0)
            lines.append(
                f"  genre-adjusted delta {pooled:+.3f} over {cells} usable genres "
                f"(naive {naive_result.delta:+.3f}, moved {moved:+.3f})"
            )

        lines.append("  by genre:")
        for comparison in genres[:12]:
            lines.append(f"    {comparison}")

        lines.append("  paid games by price band (AUD):")
        for band, count, median in price_bands(games, accessor, bound):
            lines.append(f"    {band:>8}  n={count:>4}  median {_fmt(median)}")

        lines.append("")

    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if not argv or argv[0] != "sample":
        print(__doc__)
        return 1

    metric = argv[1] if len(argv) > 1 else "ccu_per_owner"

    from src import steamspy_fetch

    catalogue = steamspy_fetch.fetch_catalogue()
    records = steamspy_fetch.enrich(cohort.audit_sample(catalogue))
    games, _ = cohort.build_cohort(records)

    playtimes = None
    if metric == "playtime":
        from src import playtime

        subset, _ = playtime.stratified_sample(games)
        playtimes = {g.appid: playtime.sample_playtime(g.appid) for g in subset}

    print(report(games, metric, playtimes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
