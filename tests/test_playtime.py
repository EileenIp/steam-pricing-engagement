"""The review-derived playtime metric: paging, dedupe, thresholds, sampling."""
from __future__ import annotations

import pytest

from src import config, cohort, playtime, steamspy_fetch


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REVIEW_CACHE_DIR", tmp_path / "reviews")
    monkeypatch.setattr(config, "REVIEW_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(steamspy_fetch, "_PACER", steamspy_fetch._Pacer())
    monkeypatch.setattr(playtime, "_PACER", steamspy_fetch._PACER)
    yield


def review(steamid, minutes):
    return {"author": {"steamid": str(steamid), "playtime_forever": minutes}}


class FakeReviews:
    """Stands in for _http_get, serving pre-canned cursor-paged responses."""

    def __init__(self, pages):
        self.pages = pages  # cursor -> payload
        self.calls = []

    def __call__(self, url, params, session=None):
        self.calls.append(params["cursor"])
        return self.pages[params["cursor"]]


def install(monkeypatch, pages):
    fake = FakeReviews(pages)
    monkeypatch.setattr(playtime, "_http_get", fake)
    return fake


def test_pages_until_the_target_sample_is_reached(monkeypatch):
    monkeypatch.setattr(config, "TARGET_REVIEWS_PER_GAME", 4)
    fake = install(monkeypatch, {
        "*": {"reviews": [review(1, 100), review(2, 200)], "cursor": "c2"},
        "c2": {"reviews": [review(3, 300), review(4, 400)], "cursor": "c3"},
        "c3": {"reviews": [review(5, 500)], "cursor": "c4"},
    })

    playtimes = playtime.collect_playtimes(1)

    assert len(playtimes) == 4
    assert fake.calls == ["*", "c2"], "should stop once the target is met"


def test_duplicate_reviewers_across_pages_are_counted_once(monkeypatch):
    monkeypatch.setattr(config, "TARGET_REVIEWS_PER_GAME", 100)
    install(monkeypatch, {
        "*": {"reviews": [review(1, 100), review(2, 200)], "cursor": "c2"},
        "c2": {"reviews": [review(2, 200), review(3, 300)], "cursor": "c2"},
    })

    playtimes = playtime.collect_playtimes(1)

    assert playtimes == {"1": 100, "2": 200, "3": 300}


def test_a_repeating_cursor_terminates(monkeypatch):
    # Steam returns the same cursor forever at the end of some listings.
    monkeypatch.setattr(config, "TARGET_REVIEWS_PER_GAME", 100)
    fake = install(monkeypatch, {"*": {"reviews": [review(1, 100)], "cursor": "*"}})

    playtime.collect_playtimes(1)

    assert fake.calls == ["*"]


def test_page_budget_is_capped(monkeypatch):
    monkeypatch.setattr(config, "TARGET_REVIEWS_PER_GAME", 10_000)
    monkeypatch.setattr(config, "MAX_REVIEW_PAGES_PER_GAME", 3)
    pages = {f"c{n}": {"reviews": [review(n, 100)], "cursor": f"c{n + 1}"} for n in range(10)}
    pages["*"] = {"reviews": [review(99, 100)], "cursor": "c0"}
    fake = install(monkeypatch, pages)

    playtime.collect_playtimes(1)

    assert len(fake.calls) == 3


def test_cached_pages_make_no_second_request(monkeypatch):
    fake = install(monkeypatch, {"*": {"reviews": [review(1, 100)], "cursor": "*"}})

    first = playtime.fetch_review_page(1)
    second = playtime.fetch_review_page(1)

    assert first == second
    assert len(fake.calls) == 1


def test_too_few_reviewers_yields_no_median_rather_than_a_bad_one(monkeypatch):
    monkeypatch.setattr(config, "MIN_REVIEWERS_FOR_MEDIAN", 30)
    monkeypatch.setattr(config, "TARGET_REVIEWS_PER_GAME", 200)
    install(monkeypatch, {"*": {"reviews": [review(i, i * 10) for i in range(1, 6)], "cursor": "*"}})

    result = playtime.sample_playtime(1)

    assert result.reviewers == 5
    assert result.median_minutes is None
    assert result.usable is False


def test_zero_playtime_reviewers_are_kept_in_the_median(monkeypatch):
    monkeypatch.setattr(config, "MIN_REVIEWERS_FOR_MEDIAN", 3)
    monkeypatch.setattr(config, "TARGET_REVIEWS_PER_GAME", 200)
    install(monkeypatch, {
        "*": {"reviews": [review(1, 0), review(2, 0), review(3, 100), review(4, 200)], "cursor": "*"},
    })

    result = playtime.sample_playtime(1)

    assert result.reviewers == 4
    assert result.zero_playtime == 2
    # Median of [0, 0, 100, 200] is 50. Dropping the zeros would give 150.
    assert result.median_minutes == 50


# --- stratified sampling ----------------------------------------------------


def game(appid, pricing, genre):
    return cohort.Game(
        appid=appid,
        name=f"Game {appid}",
        owners=cohort.parse_owner_range("50,000 .. 100,000"),
        median_forever=0,
        ccu=10,
        pricing=pricing,
        price=0.0 if pricing == "f2p" else 29.99,
        year=2020,
        genres=(genre,),
        # The stratum comes from tags, not from the storefront genre, so a
        # fixture without tags would put every game in one Unclassified cell.
        tags=((genre, 100),),
    )


def population():
    games = [game(i, "paid", "Action") for i in range(1, 51)]
    games += [game(100 + i, "f2p", "Action") for i in range(1, 31)]
    games += [game(200 + i, "f2p", "Racing") for i in range(1, 4)]  # deliberately thin
    return games


def test_sampling_caps_each_cell_and_keeps_thin_cells_whole(monkeypatch):
    monkeypatch.setattr(config, "GAMES_PER_STRATUM", 10)
    sample, sizes = playtime.stratified_sample(population())

    by_cell = {}
    for g in sample:
        by_cell[(g.pricing, g.primary_genre)] = by_cell.get((g.pricing, g.primary_genre), 0) + 1

    assert by_cell[("paid", "Action")] == 10
    assert by_cell[("f2p", "Action")] == 10
    assert by_cell[("f2p", "Racing")] == 3, "a thin cell is taken whole, not padded"
    assert sizes[("paid", "Action")] == 50


def test_sampling_is_deterministic(monkeypatch):
    monkeypatch.setattr(config, "GAMES_PER_STRATUM", 10)
    first, _ = playtime.stratified_sample(population())
    second, _ = playtime.stratified_sample(population())

    assert [g.appid for g in first] == [g.appid for g in second]


def test_thin_cells_are_reported(monkeypatch):
    monkeypatch.setattr(config, "GAMES_PER_STRATUM", 10)
    monkeypatch.setattr(config, "MIN_GAMES_PER_STRATUM", 8)
    _, sizes = playtime.stratified_sample(population())

    assert playtime.thin_cells(sizes) == [("f2p", "Racing")]
