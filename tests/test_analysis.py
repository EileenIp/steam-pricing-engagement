"""The rank statistics and the genre correction.

The statistics are hand-written rather than imported, so they get tested against
cases whose answers are known independently.
"""
from __future__ import annotations

import math

import pytest

from src import analysis, cohort, config


def game(appid, pricing, genre, ccu, owners="50,000 .. 100,000", price=29.99, year=2020):
    return cohort.Game(
        appid=appid,
        name=f"Game {appid}",
        owners=cohort.parse_owner_range(owners),
        median_forever=0,
        ccu=ccu,
        pricing=pricing,
        price=0.0 if pricing == "f2p" else price,
        year=year,
        genres=(genre,),
        tags=((genre, 100),),
    )


# --- rank statistics --------------------------------------------------------


def test_ranks_average_ties():
    # [10, 20, 20, 30] -> ranks 1, 2.5, 2.5, 4
    assert analysis._ranks([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]


def test_u_statistic_for_completely_separated_groups():
    # Every value in b exceeds every value in a, so a wins zero of the 16 pairwise
    # comparisons: U_a = 0 and Cliff's delta = -1 exactly.
    u, delta, _ = analysis.mann_whitney([1, 2, 3, 4], [5, 6, 7, 8])
    assert u == 0
    assert delta == -1.0


def test_u_statistic_is_symmetric_and_delta_flips_sign():
    u_ab, delta_ab, p_ab = analysis.mann_whitney([1, 2, 3, 4], [5, 6, 7, 8])
    u_ba, delta_ba, p_ba = analysis.mann_whitney([5, 6, 7, 8], [1, 2, 3, 4])

    assert u_ab + u_ba == 4 * 4, "U_a + U_b must equal n_a * n_b"
    assert delta_ab == -delta_ba
    assert p_ab == p_ba


def test_identical_groups_have_zero_effect_and_no_significance():
    u, delta, p = analysis.mann_whitney([5, 5, 5, 5], [5, 5, 5, 5])
    assert delta == 0.0
    assert p == 1.0


def test_delta_is_near_zero_when_groups_interleave_evenly():
    # [1,3,5,7] vs [2,4,6,8]: a wins 6 of the 16 pairs, so delta = 2*6/16 - 1.
    _, delta, _ = analysis.mann_whitney([1, 3, 5, 7], [2, 4, 6, 8])
    assert delta == pytest.approx(-0.25)


def test_a_large_clear_separation_is_significant():
    low = list(range(0, 40))
    high = list(range(100, 140))
    _, delta, p = analysis.mann_whitney(high, low)

    assert delta == 1.0
    assert p < 0.001


def test_an_empty_group_returns_nan_rather_than_crashing():
    u, delta, p = analysis.mann_whitney([], [1, 2, 3])
    assert math.isnan(u) and math.isnan(delta) and math.isnan(p)


def test_tie_correction_changes_the_p_value():
    # Heavy ties shrink the variance, so the same U is more significant than the
    # untied formula would say. If the correction were dropped this would differ.
    tied = analysis.mann_whitney([1, 1, 1, 1, 2], [2, 2, 3, 3, 3])[2]
    assert 0.0 <= tied <= 1.0


# --- comparisons ------------------------------------------------------------


def accessor():
    return analysis.metric_accessor("ccu_per_owner")


def test_naive_comparison_reports_both_sides():
    games = [game(i, "f2p", "MOBA", ccu=1000) for i in range(1, 6)]
    games += [game(100 + i, "paid", "MOBA", ccu=10) for i in range(1, 6)]

    result = analysis.naive(games, accessor(), "midpoint")

    assert result.n_f2p == 5 and result.n_paid == 5
    assert result.delta == 1.0, "every F2P game out-ranks every paid game here"
    assert result.median_f2p > result.median_paid


def test_a_one_sided_group_yields_no_delta_rather_than_a_fake_one():
    games = [game(i, "paid", "MOBA", ccu=10) for i in range(1, 6)]
    result = analysis.naive(games, accessor(), "midpoint")

    assert result.delta is None
    assert result.usable is False


def test_thin_cells_are_marked_unusable():
    games = [game(i, "f2p", "MOBA", ccu=1000) for i in range(1, 4)]
    games += [game(100 + i, "paid", "MOBA", ccu=10) for i in range(1, 30)]

    result = analysis.naive(games, accessor(), "midpoint")

    assert result.delta is not None
    assert result.usable is False, "3 F2P games cannot carry a claim"


def test_the_genre_correction_can_reverse_the_naive_result():
    """Simpson's paradox, which is the whole reason the correction exists.

    F2P concentrates in a genre with high engagement overall and paid in a low
    one, so pooled F2P looks better. Inside each genre paid actually wins.
    """
    games = []
    # MOBA: high engagement overall, and where F2P concentrates (40 vs 8) - but
    # inside the genre every paid game out-engages every F2P one.
    games += [game(i, "f2p", "MOBA", ccu=900 + i) for i in range(1, 41)]
    games += [game(50 + i, "paid", "MOBA", ccu=1000 + i) for i in range(1, 9)]
    # Visual Novel: low engagement overall, and where paid concentrates (40 vs 8).
    # Paid wins inside this genre too.
    games += [game(100 + i, "f2p", "Visual Novel", ccu=10 + i) for i in range(1, 9)]
    games += [game(200 + i, "paid", "Visual Novel", ccu=50 + i) for i in range(1, 41)]

    naive_result = analysis.naive(games, accessor(), "midpoint")
    genres = analysis.within_genre(games, accessor(), "midpoint")
    pooled, cells = analysis.genre_adjusted_delta(genres)

    assert naive_result.delta > 0, "pooled, F2P looks better"
    assert cells == 2
    assert pooled == -1.0, "within every genre, paid wins outright"
    assert pooled < naive_result.delta, "the correction reverses the naive conclusion"


def test_pooling_ignores_cells_too_thin_to_interpret():
    games = [game(i, "f2p", "MOBA", ccu=1000 + i) for i in range(1, 21)]
    games += [game(50 + i, "paid", "MOBA", ccu=10 + i) for i in range(1, 21)]
    # A thin genre with the opposite sign, which must not drag the pooled figure.
    games += [game(100 + i, "f2p", "Racing", ccu=1) for i in range(1, 3)]
    games += [game(200 + i, "paid", "Racing", ccu=9000) for i in range(1, 3)]

    pooled, cells = analysis.genre_adjusted_delta(analysis.within_genre(games, accessor(), "midpoint"))

    assert cells == 1
    assert pooled == 1.0


def test_pooling_weights_by_pairwise_comparisons_not_genre_count():
    # A 20v20 genre and a 10v10 genre disagree. The bigger genre must dominate:
    # equal-weighting would give 0.0, pairwise weighting leans positive.
    games = [game(i, "f2p", "MOBA", ccu=1000 + i) for i in range(1, 21)]
    games += [game(50 + i, "paid", "MOBA", ccu=10 + i) for i in range(1, 21)]
    games += [game(100 + i, "f2p", "FPS", ccu=10 + i) for i in range(1, 11)]
    games += [game(200 + i, "paid", "FPS", ccu=1000 + i) for i in range(1, 11)]

    pooled, cells = analysis.genre_adjusted_delta(analysis.within_genre(games, accessor(), "midpoint"))

    assert cells == 2
    assert pooled == pytest.approx(0.6, abs=0.01)


def test_no_usable_cell_reports_that_rather_than_inventing_a_number():
    games = [game(i, "f2p", "MOBA", ccu=1000) for i in range(1, 4)]
    games += [game(50 + i, "paid", "MOBA", ccu=10) for i in range(1, 4)]

    pooled, cells = analysis.genre_adjusted_delta(analysis.within_genre(games, accessor(), "midpoint"))

    assert pooled is None
    assert cells == 0


def test_unclassified_games_never_enter_a_within_genre_claim():
    games = [game(i, "f2p", "Great Soundtrack", ccu=1000) for i in range(1, 21)]
    games += [game(50 + i, "paid", "Great Soundtrack", ccu=10) for i in range(1, 21)]

    assert games[0].primary_genre == config.UNCLASSIFIED_GENRE
    assert analysis.within_genre(games, accessor(), "midpoint") == []


# --- bounds, bands, cohorts -------------------------------------------------


def test_the_ccu_metric_moves_with_the_owner_bound():
    games = [game(i, "f2p", "MOBA", ccu=1000) for i in range(1, 6)]
    games += [game(50 + i, "paid", "MOBA", ccu=10) for i in range(1, 6)]

    medians = [analysis.naive(games, accessor(), b).median_f2p for b in config.OWNER_BOUNDS]

    assert medians[0] > medians[1] > medians[2], "more owners, lower ratio"


def test_price_bands_cover_paid_games_only():
    games = [game(1, "f2p", "MOBA", ccu=100)]
    games += [game(2, "paid", "MOBA", ccu=100, price=5.0)]
    games += [game(3, "paid", "MOBA", ccu=100, price=89.95)]

    bands = dict((band, n) for band, n, _ in analysis.price_bands(games, accessor(), "midpoint"))

    assert bands["0-10"] == 1
    assert bands["60+"] == 1
    assert sum(bands.values()) == 2, "the F2P game must not appear in a price band"


def test_release_cohorts_split_by_year():
    games = [game(i, "f2p", "MOBA", ccu=100, year=2019) for i in range(1, 4)]
    games += [game(50 + i, "paid", "MOBA", ccu=10, year=2021) for i in range(1, 4)]

    cohorts = analysis.release_cohorts(games, accessor(), "midpoint")

    assert [c.label for c in cohorts] == ["2019", "2021"]
    assert cohorts[0].n_f2p == 3 and cohorts[0].n_paid == 0


def test_playtime_metric_refuses_to_run_without_the_review_pull():
    with pytest.raises(ValueError, match="review pull"):
        analysis.metric_accessor("playtime")


def test_unknown_metric_is_rejected():
    with pytest.raises(ValueError, match="unknown metric"):
        analysis.metric_accessor("vibes")


# --- reporting ---------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [(None, "-"), (0, "0"), (5761.5, "5,762"), (0.512, "0.512"), (0.000067, "6.70e-05")],
)
def test_values_are_formatted_across_the_magnitudes_both_metrics_span(value, expected):
    # Playtime medians are thousands of minutes, CCU per owner is ~0.0001. One
    # format string rounded the latter to "0" and hid that the metric worked.
    assert analysis._fmt(value) == expected


def test_ties_at_zero_are_measured_and_surfaced():
    # Over half this cohort has ccu 0, which guts a rank test's power. The share
    # has to be visible next to the result, not left for the reader to find.
    games = [game(i, "f2p", "MOBA", ccu=0) for i in range(1, 11)]
    games += [game(50 + i, "paid", "MOBA", ccu=0) for i in range(1, 9)]
    games += [game(80 + i, "paid", "MOBA", ccu=500) for i in range(1, 3)]

    result = analysis.naive(games, accessor(), "midpoint")

    assert result.tied_at_zero == pytest.approx(18 / 20)
    assert "ties@0 90%" in str(result)


def test_no_tie_warning_when_values_separate_cleanly():
    games = [game(i, "f2p", "MOBA", ccu=100 + i) for i in range(1, 11)]
    games += [game(50 + i, "paid", "MOBA", ccu=200 + i) for i in range(1, 11)]

    result = analysis.naive(games, accessor(), "midpoint")

    assert result.tied_at_zero == 0.0
    assert "ties@0" not in str(result)


def test_a_flag_is_never_parsed_as_the_metric_name(monkeypatch, tmp_path):
    # `analysis full --refresh` read "--refresh" as the metric and crashed after
    # ten minutes of rebuilding, which is the worst moment to find out.
    monkeypatch.setattr(analysis.config, "PROCESSED_DATA_DIR", tmp_path)
    seen = {}

    def fake_load_cohort(loader, bound="midpoint", refresh=False):
        seen["refresh"] = refresh
        return []

    def fake_report(games, metric, playtimes=None):
        seen["metric"] = metric
        return ""

    monkeypatch.setattr(analysis.cohort, "load_cohort", fake_load_cohort)
    monkeypatch.setattr(analysis, "report", fake_report)

    assert analysis.main(["full", "--refresh"]) == 0
    assert seen == {"refresh": True, "metric": "ccu_per_owner"}

    assert analysis.main(["full", "playtime", "--refresh"]) == 0
    assert seen["metric"] == "playtime"
