"""The cache and resume behaviour the spec's Phase 2 test list asks for:

  - the pull cache returns identical data on re-run (and makes no second request)

Plus the pacing and failure handling that make an hours-long pull survivable.
"""
from __future__ import annotations

import json

import pytest
import requests

from src import config, steamspy_fetch


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Every test writes into its own tmp dir - never the real data/raw archive."""
    monkeypatch.setattr(config, "RAW_DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "STEAMSPY_ALL_DIR", tmp_path / "steamspy_all")
    monkeypatch.setattr(config, "STEAMSPY_APP_DIR", tmp_path / "steamspy_app")
    monkeypatch.setattr(config, "STORE_APP_DIR", tmp_path / "store_app")
    monkeypatch.setattr(config, "RESUME_FILE", tmp_path / "resume.json")
    # The real delays are 1s, 1.5s and 60s. Tests assert on call counts, not on
    # wall-clock pacing, so paying them would just make the suite slow.
    monkeypatch.setattr(config, "STEAMSPY_ALL_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(config, "STEAMSPY_APP_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(config, "STORE_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(steamspy_fetch, "_PACER", steamspy_fetch._Pacer())
    yield


class CountingTransport:
    """Stands in for _http_get and counts how many live requests were made."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, url, params, session=None):
        self.calls.append(params)
        key = params.get("page", params.get("appid", params.get("appids")))
        return self.responses[key]


def page(n_apps, first_appid=1):
    return {
        str(first_appid + i): {"appid": first_appid + i, "name": f"Game {first_appid + i}",
                               "owners": "50,000 .. 100,000"}
        for i in range(n_apps)
    }


# --- the cache test the spec names ------------------------------------------


def test_cached_page_returns_identical_data_and_makes_no_second_request(monkeypatch):
    transport = CountingTransport({0: page(3)})
    monkeypatch.setattr(steamspy_fetch, "_http_get", transport)

    first = steamspy_fetch.fetch_catalogue_page(0)
    second = steamspy_fetch.fetch_catalogue_page(0)

    assert first == second
    assert len(transport.calls) == 1, "second call should have been served from disk"


def test_cached_app_and_store_lookups_are_byte_identical_on_re_run(monkeypatch):
    transport = CountingTransport({
        570: {"appid": 570, "name": "Dota 2", "owners": "100,000,000 .. 200,000,000"},
        "570": {"570": {"success": True, "data": {"is_free": True}}},
    })
    monkeypatch.setattr(steamspy_fetch, "_http_get", transport)

    spy_first, store_first = steamspy_fetch.fetch_app(570), steamspy_fetch.fetch_store(570)
    spy_second, store_second = steamspy_fetch.fetch_app(570), steamspy_fetch.fetch_store(570)

    assert spy_first == spy_second
    assert store_first == store_second
    assert len(transport.calls) == 2


def test_failed_store_lookups_are_cached_too(monkeypatch):
    # Delisted apps fail forever. Re-fetching them every run is 1.5s each, wasted.
    transport = CountingTransport({9: {}})
    monkeypatch.setattr(steamspy_fetch, "_http_get", transport)

    assert steamspy_fetch.fetch_store(9) == {"success": False}
    assert steamspy_fetch.fetch_store(9) == {"success": False}
    assert len(transport.calls) == 1


# --- paging and resume ------------------------------------------------------


def test_paging_stops_on_a_short_page(monkeypatch):
    monkeypatch.setattr(config, "STEAMSPY_PAGE_SIZE", 3)
    transport = CountingTransport({0: page(3), 1: page(3, 4), 2: page(1, 7)})
    monkeypatch.setattr(steamspy_fetch, "_http_get", transport)

    catalogue = steamspy_fetch.fetch_catalogue()

    assert len(catalogue) == 7
    assert len(transport.calls) == 3, "should not have asked for a fourth page"
    assert steamspy_fetch.load_resume()["catalogue_complete"] is True


def test_an_interrupted_pull_resumes_instead_of_restarting(monkeypatch):
    monkeypatch.setattr(config, "STEAMSPY_PAGE_SIZE", 3)

    class Failing(CountingTransport):
        def __call__(self, url, params, session=None):
            if params.get("page") == 2:
                raise steamspy_fetch.SteamAPIError("connection dropped")
            return super().__call__(url, params, session)

    responses = {0: page(3), 1: page(3, 4), 2: page(1, 7)}
    monkeypatch.setattr(steamspy_fetch, "_http_get", Failing(responses))

    with pytest.raises(steamspy_fetch.SteamAPIError):
        steamspy_fetch.fetch_catalogue()

    assert steamspy_fetch.load_resume()["catalogue_pages_done"] == [0, 1]

    # Second run: pages 0 and 1 come off disk, only page 2 is fetched live.
    resumed = CountingTransport(responses)
    monkeypatch.setattr(steamspy_fetch, "_http_get", resumed)
    catalogue = steamspy_fetch.fetch_catalogue()

    assert len(catalogue) == 7
    assert [c["page"] for c in resumed.calls] == [2]


def test_the_page_hard_stop_holds(monkeypatch):
    monkeypatch.setattr(config, "STEAMSPY_PAGE_SIZE", 3)
    monkeypatch.setattr(config, "MAX_ALL_PAGES", 4)
    # A page that never shortens - the shape that would otherwise loop forever.
    transport = CountingTransport({n: page(3, 1 + 3 * n) for n in range(10)})
    monkeypatch.setattr(steamspy_fetch, "_http_get", transport)

    steamspy_fetch.fetch_catalogue()

    assert len(transport.calls) == 4
    assert steamspy_fetch.load_resume()["catalogue_complete"] is False


def test_a_partial_write_is_never_left_behind(monkeypatch):
    path = config.STEAMSPY_ALL_DIR / "page_000.json"
    steamspy_fetch._write_json(path, {"1": {"name": "Game 1"}})

    assert json.loads(path.read_text(encoding="utf-8")) == {"1": {"name": "Game 1"}}
    assert not list(path.parent.glob("*.part"))


# --- retry ------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code, payload=None, text_body=None):
        self.status_code = status_code
        self._payload = payload
        self._text_body = text_body

    def json(self):
        if self._text_body is not None:
            raise ValueError("not JSON")
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(config, "BACKOFF_BASE_SECONDS", 0.0)
    session = FakeSession([FakeResponse(429), requests.Timeout(), FakeResponse(200, {"ok": True})])

    assert steamspy_fetch._http_get("http://x", {}, session) == {"ok": True}
    assert session.calls == 3


def test_does_not_retry_a_404(monkeypatch):
    monkeypatch.setattr(config, "BACKOFF_BASE_SECONDS", 0.0)
    session = FakeSession([FakeResponse(404)])

    with pytest.raises(steamspy_fetch.SteamAPIError):
        steamspy_fetch._http_get("http://x", {}, session)
    assert session.calls == 1


def test_html_error_page_with_a_200_is_an_error_not_data(monkeypatch):
    # Both endpoints do this for unknown appids. Without the check it would be
    # cached as if it were real data.
    monkeypatch.setattr(config, "BACKOFF_BASE_SECONDS", 0.0)
    session = FakeSession([FakeResponse(200, text_body="<html>oops</html>")])

    with pytest.raises(steamspy_fetch.SteamAPIError, match="not JSON"):
        steamspy_fetch._http_get("http://x", {}, session)


def below_floor_page(n_apps, first_appid=1):
    return {
        str(first_appid + i): {"appid": first_appid + i, "owners": "0 .. 20,000"}
        for i in range(n_apps)
    }


def test_paging_stops_once_a_page_is_entirely_below_the_owner_floor(monkeypatch):
    # `all` is sorted by owners descending, so a page with no candidate means no
    # later page has one either. Without this the pull spends an hour at 60s/page
    # fetching apps that are excluded the moment they arrive.
    monkeypatch.setattr(config, "STEAMSPY_PAGE_SIZE", 3)
    transport = CountingTransport({
        0: page(3),
        1: below_floor_page(3, 4),
        2: page(3, 7),
    })
    monkeypatch.setattr(steamspy_fetch, "_http_get", transport)

    steamspy_fetch.fetch_catalogue()

    assert len(transport.calls) == 2, "should not have asked for page 2"
    assert steamspy_fetch.load_resume()["catalogue_complete"] is True


def test_enrich_pairs_both_sources_and_survives_a_bad_app(monkeypatch):
    # One dead app must not end a pull measured in hours.
    def transport(url, params, session=None):
        if "steamspy" in url:
            appid = params["appid"]
            if appid == 2:
                raise steamspy_fetch.SteamAPIError("boom")
            return {"appid": appid, "owners": "50,000 .. 100,000"}
        appid = params["appids"]
        return {str(appid): {"success": True, "data": {"is_free": False}}}

    monkeypatch.setattr(steamspy_fetch, "_http_get", transport)
    records = steamspy_fetch.enrich([1, 2, 3])

    assert set(records) == {1, 2, 3}
    assert records[1]["steamspy"]["owners"] == "50,000 .. 100,000"
    assert records[1]["store"]["success"] is True
    assert records[2]["steamspy"] == {}, "the failed fetch is empty, not fabricated"
    assert records[2]["store"]["success"] is True, "the other endpoint still ran"
    assert steamspy_fetch.load_resume()["enriched"] == [1, 2, 3]


def test_enrich_is_fully_cached_on_a_re_run(monkeypatch):
    calls = []

    def transport(url, params, session=None):
        calls.append(params)
        if "steamspy" in url:
            return {"appid": params["appid"], "owners": "50,000 .. 100,000"}
        return {str(params["appids"]): {"success": True, "data": {}}}

    monkeypatch.setattr(steamspy_fetch, "_http_get", transport)
    first = steamspy_fetch.enrich([1, 2])
    live = len(calls)
    second = steamspy_fetch.enrich([1, 2])

    assert first == second
    assert len(calls) == live, "a re-run should make no live requests"
