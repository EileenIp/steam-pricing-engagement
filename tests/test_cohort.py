"""The Phase 2 test list from the spec, minus the cache test (in test_steamspy_fetch).

  - owner-range parsing round-trips correctly
  - no game appears in both the F2P and the paid set
  - sensitivity bounds bracket the midpoint result
"""
from __future__ import annotations

import pytest

from src import config, cohort

# The real SteamSpy owner bands, verbatim. These are the strings the parser has to
# survive, so they are the fixture rather than invented ones.
REAL_BANDS = [
    "0 .. 20,000",
    "20,000 .. 50,000",
    "50,000 .. 100,000",
    "100,000 .. 200,000",
    "500,000 .. 1,000,000",
    "1,000,000 .. 2,000,000",
    "20,000,000 .. 50,000,000",
    "100,000,000 .. 200,000,000",
]


def store_entry(*, is_free=False, price_cents=2999, year="12 Aug, 2024", genre="Action"):
    entry = {
        "success": True,
        "data": {
            "is_free": is_free,
            "release_date": {"coming_soon": False, "date": year},
            "genres": [{"id": "1", "description": genre}],
        },
    }
    if not is_free:
        entry["data"]["price_overview"] = {"currency": "AUD", "final": price_cents}
    return entry


def record(appid, owners, *, is_free=False, median=600, ccu=100, **store_kwargs):
    return {
        "steamspy": {
            "appid": appid,
            "name": f"Game {appid}",
            "owners": owners,
            "median_forever": median,
            "ccu": ccu,
        },
        "store": store_entry(is_free=is_free, **store_kwargs),
    }


# --- owner ranges -----------------------------------------------------------


@pytest.mark.parametrize("raw", REAL_BANDS)
def test_owner_range_round_trips(raw):
    assert cohort.format_owner_range(cohort.parse_owner_range(raw)) == raw


def test_owner_range_tolerates_separator_drift():
    # Same band, three spacings SteamSpy has been seen to emit.
    parsed = {
        cohort.parse_owner_range(raw)
        for raw in ("1,000,000 .. 2,000,000", "1,000,000..2,000,000", "1,000,000 \xa0..\xa0 2,000,000")
    }
    assert parsed == {cohort.OwnerRange(1_000_000, 2_000_000)}


@pytest.mark.parametrize("raw", [None, "", "1,000,000", "lots .. more", "2,000 .. 1,000"])
def test_bad_owner_strings_raise_rather_than_guess(raw):
    with pytest.raises(cohort.OwnerParseError):
        cohort.parse_owner_range(raw)


def test_midpoint_sits_between_the_bounds():
    owners = cohort.parse_owner_range("1,000,000 .. 2,000,000")
    assert owners.at("lower") < owners.at("midpoint") < owners.at("upper")


# --- the two sets are disjoint ----------------------------------------------


def test_no_game_appears_in_both_pricing_sets():
    records = {
        "1": record(1, "50,000 .. 100,000", is_free=True),
        "2": record(2, "50,000 .. 100,000", is_free=False),
        "3": record(3, "1,000,000 .. 2,000,000", is_free=True),
        "4": record(4, "1,000,000 .. 2,000,000", is_free=False, price_cents=8999),
    }
    games, _ = cohort.build_cohort(records)
    split = cohort.split_by_pricing(games)

    f2p_ids = {g.appid for g in split["f2p"]}
    paid_ids = {g.appid for g in split["paid"]}

    assert f2p_ids & paid_ids == set()
    assert len(f2p_ids) + len(paid_ids) == len(games)


def test_free_flag_beats_a_zero_price():
    # A paid game discounted to zero is still paid; is_free is the authority.
    free_promo = store_entry(is_free=False, price_cents=0)
    assert cohort.classify_pricing(free_promo) == "paid"
    assert cohort.classify_pricing(store_entry(is_free=True)) == "f2p"


def test_unusable_storefront_entry_is_excluded_not_guessed():
    assert cohort.classify_pricing({"success": False}) is None
    records = {"1": record(1, "50,000 .. 100,000")}
    records["1"]["store"] = {"success": False}
    games, excluded = cohort.build_cohort(records)
    assert games == []
    assert excluded["no usable release date"] == 1


# --- sensitivity ------------------------------------------------------------


def test_bounds_bracket_the_midpoint_for_ccu_per_owner():
    game = cohort.Game(
        appid=1,
        name="Game 1",
        owners=cohort.parse_owner_range("1,000,000 .. 2,000,000"),
        median_forever=600,
        ccu=5_000,
        pricing="paid",
        price=29.99,
        year=2024,
        genres=("Action",),
    )
    values = [game.ccu_per_owner(bound) for bound in config.OWNER_BOUNDS]
    midpoint = game.ccu_per_owner("midpoint")

    assert min(values) <= midpoint <= max(values)
    # And the direction is the one that makes sense: more owners, lower ratio.
    assert game.ccu_per_owner("lower") > game.ccu_per_owner("upper")


def test_cohort_size_is_monotone_in_the_bound():
    # A game whose band straddles the floor is in at the upper bound and out at
    # the lower one. The cohort itself has to move, or the sensitivity check is
    # cosmetic.
    records = {
        "1": record(1, "0 .. 20,000"),            # midpoint 10k - out except at upper
        "2": record(2, "20,000 .. 50,000"),       # in at every bound but lower
        "3": record(3, "1,000,000 .. 2,000,000"),  # in everywhere
    }
    sizes = {bound: len(cohort.build_cohort(records, bound)[0]) for bound in config.OWNER_BOUNDS}

    assert sizes["lower"] <= sizes["midpoint"] <= sizes["upper"]
    assert sizes["upper"] == 3
    assert sizes["midpoint"] == 2


# --- inclusion rule ---------------------------------------------------------


def test_release_year_filter():
    records = {
        "1": record(1, "1,000,000 .. 2,000,000", year="3 Mar, 2014"),
        "2": record(2, "1,000,000 .. 2,000,000", year="3 Mar, 2015"),
    }
    games, excluded = cohort.build_cohort(records)
    assert [g.appid for g in games] == [2]
    assert excluded[f"released before {config.MIN_RELEASE_YEAR}"] == 1


def test_unreleased_games_are_excluded():
    entry = store_entry()
    entry["data"]["release_date"] = {"coming_soon": True, "date": "Q3 2026"}
    assert cohort.release_year(entry) is None


@pytest.mark.parametrize(
    "price,expected",
    [(0.0, "0-10"), (9.99, "0-10"), (10.0, "10-30"), (29.99, "10-30"), (30.0, "30-60"), (89.95, "60+")],
)
def test_price_bands(price, expected):
    assert cohort.price_band(price) == expected


def test_non_aud_price_is_refused_rather_than_converted():
    entry = store_entry()
    entry["data"]["price_overview"]["currency"] = "USD"
    assert cohort.price_aud(entry) is None


def test_candidate_prefilter_keeps_anything_that_could_survive_any_bound():
    catalogue = {
        "1": {"owners": "0 .. 20,000"},       # upper bound reaches the floor - keep
        "2": {"owners": "0 .. 0"},            # cannot survive at any bound - drop
        "3": {"owners": "not a range"},       # unparseable - drop, don't crash
        "4": {"owners": "500,000 .. 1,000,000"},
    }
    assert cohort.candidate_appids(catalogue) == [1, 4]
