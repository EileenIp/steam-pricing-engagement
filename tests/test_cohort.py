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


def record(appid, owners, *, is_free=False, median=600, ccu=100, tags=None, **store_kwargs):
    return {
        "steamspy": {
            "appid": appid,
            "name": f"Game {appid}",
            "owners": owners,
            "median_forever": median,
            "ccu": ccu,
            "tags": tags or {},
        },
        "store": store_entry(is_free=is_free, **store_kwargs),
    }


# Real tag dictionaries, trimmed. These two are the cases the vocabulary exists
# for, so they are the fixture rather than invented ones.
DOTA_TAGS = {
    "Free to Play": 60040, "MOBA": 20225, "Multiplayer": 15411, "Strategy": 14289,
    "e-sports": 11816, "Team-Based": 10989, "Competitive": 8324, "Action": 7939,
}
ELDEN_RING_TAGS = {
    "Souls-like": 6994, "Open World": 5078, "Dark Fantasy": 4953, "RPG": 4707,
    "Difficult": 4595, "Action RPG": 3584, "Third Person": 3403, "Multiplayer": 3395,
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
        # The bottom band's upper bound is exactly the floor. It must stay out at
        # every bound, including upper - the floor was chosen to drop this band.
        "1": record(1, "0 .. 20,000"),
        "2": record(2, "20,000 .. 50,000"),       # straddles: out at lower, in above
        "3": record(3, "1,000,000 .. 2,000,000"),  # in everywhere
    }
    sizes = {bound: len(cohort.build_cohort(records, bound)[0]) for bound in config.OWNER_BOUNDS}

    assert sizes["lower"] <= sizes["midpoint"] <= sizes["upper"]
    assert sizes["lower"] == 1
    assert sizes["midpoint"] == 2
    assert sizes["upper"] == 2, "the bottom band must not return at the upper bound"


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
        "1": {"owners": "0 .. 20,000"},       # tops out exactly at the floor - drop
        "2": {"owners": "20,000 .. 50,000"},  # could survive above the lower bound
        "3": {"owners": "not a range"},       # unparseable - drop, don't crash
        "4": {"owners": "500,000 .. 1,000,000"},
    }
    assert cohort.candidate_appids(catalogue) == [2, 4]


# --- genre stratification on tags -------------------------------------------


def test_the_vocabulary_and_the_pricing_blocklist_do_not_overlap():
    # If a business-model tag ever got into the genre vocabulary, the circularity
    # guard below would silently stop working.
    assert config.GENRE_TAGS & config.PRICING_MODEL_TAGS == frozenset()


def test_pricing_model_tags_cannot_become_a_stratum():
    # The whole point. Dota 2's top tag is "Free to Play" at 60,040 votes, three
    # times the next; taking the top tag would make the strata a restatement of
    # the pricing model and leave no cell containing both models.
    assert cohort.primary_genre_from_tags(DOTA_TAGS) == "MOBA"


def test_descriptor_tags_are_not_genres():
    # "Open World", "Dark Fantasy", "Difficult", "Third Person" all outrank the
    # eligible tags by votes here, and none of them is a genre.
    assert cohort.primary_genre_from_tags(ELDEN_RING_TAGS) == "Souls-like"


def test_a_game_with_no_recognised_tag_is_unclassified_not_forced():
    tags = {"Great Soundtrack": 900, "Atmospheric": 800, "Female Protagonist": 700}
    assert cohort.primary_genre_from_tags(tags) == config.UNCLASSIFIED_GENRE
    assert cohort.primary_genre_from_tags({}) == config.UNCLASSIFIED_GENRE
    assert cohort.primary_genre_from_tags(None) == config.UNCLASSIFIED_GENRE


def test_tag_ties_break_deterministically():
    # Same votes, different insertion order - the stratum must not depend on which
    # order the dict happened to arrive in, or the sample stops being cacheable.
    first = cohort.primary_genre_from_tags({"Racing": 500, "Puzzle": 500})
    second = cohort.primary_genre_from_tags({"Puzzle": 500, "Racing": 500})
    assert first == second == "Puzzle"


def test_tags_survive_into_the_cohort_and_set_the_stratum():
    records = {"570": record(570, "1,000,000 .. 2,000,000", is_free=True, tags=DOTA_TAGS)}
    games, _ = cohort.build_cohort(records)

    assert games[0].primary_genre == "MOBA"
    assert games[0].classified is True
    # Steam's own genre is kept alongside, and is exactly the broad bucket the
    # tag-level correction exists to improve on.
    assert games[0].store_genre == "Action"


def test_coverage_report_names_the_tags_worth_adding():
    records = {
        "1": record(1, "1,000,000 .. 2,000,000", tags={"Colony Sim": 100}),
        "2": record(2, "1,000,000 .. 2,000,000", tags={"Cozy": 900, "Wholesome": 100}),
        "3": record(3, "1,000,000 .. 2,000,000", tags={"Cozy": 400}),
        "4": record(4, "1,000,000 .. 2,000,000", tags={}),
    }
    games, _ = cohort.build_cohort(records)

    assert cohort.unclassified_top_tags(games) == [("Cozy", 2), ("(no tags at all)", 1)]

    report = cohort.coverage_report(games)
    assert "1/4 classified (25.0%)" in report
    assert "Cozy" in report


def test_coverage_is_reported_per_pricing_model():
    # A vocabulary gap that falls unevenly on F2P vs paid thins one side of every
    # comparison, so the report has to show the split, not just the total.
    records = {
        "1": record(1, "1,000,000 .. 2,000,000", is_free=True, tags={"MOBA": 100}),
        "2": record(2, "1,000,000 .. 2,000,000", is_free=False, tags={"Cozy": 100}),
    }
    games, _ = cohort.build_cohort(records)
    report = cohort.coverage_report(games)

    assert "f2p: 1/1 classified (100.0%)" in report
    assert "paid: 0/1 classified (0.0%)" in report


def test_audit_sample_is_deterministic_and_bounded():
    catalogue = {str(i): {"owners": "50,000 .. 100,000"} for i in range(1, 501)}

    first = cohort.audit_sample(catalogue, 50)
    second = cohort.audit_sample(catalogue, 50)

    assert first == second, "the sample must be stable, or its cached enrichment is wasted"
    assert len(first) == 50
    assert first == sorted(first)
    assert set(first) <= set(cohort.candidate_appids(catalogue))


def test_audit_sample_smaller_than_the_request_is_returned_whole():
    catalogue = {str(i): {"owners": "50,000 .. 100,000"} for i in range(1, 11)}
    assert cohort.audit_sample(catalogue, 50) == list(range(1, 11))


def test_umbrella_tags_lose_to_specific_ones_even_with_more_votes():
    # The failure this tier exists to fix: on the audit sample a highest-votes
    # rule put 65% of the cohort into a broad bucket, which is no better than the
    # storefront genres tags were brought in to replace.
    tags = {"Action": 9000, "Casual": 8000, "Roguelike": 1200}
    assert cohort.primary_genre_from_tags(tags) == "Roguelike"


def test_umbrella_tags_are_still_used_when_nothing_specific_exists():
    assert cohort.primary_genre_from_tags({"Action": 9000, "Casual": 8000}) == "Action"


def test_every_umbrella_tag_is_part_of_the_vocabulary():
    assert config.BROAD_GENRE_TAGS <= config.GENRE_TAGS


def test_software_is_excluded_from_a_games_comparison():
    records = {
        "1": record(1, "1,000,000 .. 2,000,000", genre="Utilities", tags={"Action": 100}),
        "2": record(2, "1,000,000 .. 2,000,000", genre="Action", tags={"Action": 100}),
    }
    games, excluded = cohort.build_cohort(records)

    assert [g.appid for g in games] == [2]
    assert excluded["not a game (software)"] == 1


def test_cohort_cache_round_trips_and_parses_raw_only_once(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROCESSED_DATA_DIR", tmp_path)
    records = {
        "1": record(1, "1,000,000 .. 2,000,000", is_free=True, tags=DOTA_TAGS),
        "2": record(2, "500,000 .. 1,000,000", is_free=False, tags=ELDEN_RING_TAGS),
    }
    calls = []

    def loader():
        calls.append(1)
        return records

    first = cohort.load_cohort(loader)
    second = cohort.load_cohort(loader)

    assert len(calls) == 1, "the second load must come from cache, not re-parse raw"
    assert [g.appid for g in first] == [g.appid for g in second]
    # The fields the analysis actually uses must survive the round trip intact.
    assert [(g.pricing, g.primary_genre, g.price, g.year, g.ccu) for g in first] == \
           [(g.pricing, g.primary_genre, g.price, g.year, g.ccu) for g in second]
    assert first[0].owners == second[0].owners


def test_refresh_rebuilds_from_raw(tmp_path, monkeypatch):
    # A stale cohort is a worse failure than a slow one, because it is silent.
    monkeypatch.setattr(config, "PROCESSED_DATA_DIR", tmp_path)
    records = {"1": record(1, "1,000,000 .. 2,000,000", tags=DOTA_TAGS)}
    calls = []

    def loader():
        calls.append(1)
        return records

    cohort.load_cohort(loader)
    cohort.load_cohort(loader, refresh=True)

    assert len(calls) == 2
