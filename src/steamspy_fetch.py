"""Pull the SteamSpy catalogue and enrich it from the Steam storefront.

Three entry points:

  recon(appid)        - cheap. One SteamSpy call and one storefront call for a single
                        app. Use it to check field shapes before committing to a
                        catalogue pull that takes hours.

  fetch_catalogue()   - the `all` pages. Every page is written to disk untransformed
                        and a resume file records which pages completed, so an
                        interrupted pull continues where it stopped instead of
                        restarting at 60 seconds per page.

  enrich(appids)      - per-app SteamSpy detail plus storefront appdetails (price,
                        genres, release date, is_free). Cached per app; re-running
                        after an interrupt only fetches what is missing.

Run: python -m src.steamspy_fetch recon 570
     python -m src.steamspy_fetch catalogue
     python -m src.steamspy_fetch enrich
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from src import console
from src import config


class SteamAPIError(RuntimeError):
    pass


class _Pacer:
    """Sleeps only as much as is still owed since the last live request.

    Sleeping after every request pays the full delay even when the next call is a
    cache hit, which on a 60s/page endpoint turns a fully cached re-run from
    seconds into an hour.
    """

    def __init__(self) -> None:
        self._last: dict[str, float] = {}

    def wait(self, key: str, interval: float) -> None:
        previous = self._last.get(key)
        if previous is not None:
            owed = interval - (time.monotonic() - previous)
            if owed > 0:
                time.sleep(owed)
        self._last[key] = time.monotonic()


_PACER = _Pacer()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file and move it into place. An interrupt mid-write would
    # otherwise leave a truncated cache file that reads as valid on the next run.
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def _http_get(url: str, params: dict, session: requests.Session | None = None) -> dict:
    """GET with retry on the failures worth retrying (429, 5xx, timeouts)."""
    caller = session or requests
    last_error: Exception | None = None

    for attempt in range(config.MAX_RETRIES):
        try:
            response = caller.get(url, params=params, timeout=config.REQUEST_TIMEOUT_SECONDS)
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
        else:
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    # Both endpoints serve an HTML error page with a 200 when the
                    # request is malformed or the app is unknown.
                    raise SteamAPIError(f"{url}: 200 but body was not JSON") from exc
            if response.status_code not in (429, 500, 502, 503, 504):
                raise SteamAPIError(f"{url}: HTTP {response.status_code}")
            last_error = SteamAPIError(f"HTTP {response.status_code}")

        if attempt < config.MAX_RETRIES - 1:
            time.sleep(config.BACKOFF_BASE_SECONDS * (2**attempt))

    raise SteamAPIError(f"{url}: gave up after {config.MAX_RETRIES} attempts") from last_error


# --- resume state -----------------------------------------------------------


def load_resume() -> dict:
    if config.RESUME_FILE.exists():
        return json.loads(config.RESUME_FILE.read_text(encoding="utf-8"))
    return {"catalogue_pages_done": [], "catalogue_complete": False, "enriched": []}


def save_resume(state: dict) -> None:
    _write_json(config.RESUME_FILE, state)


# --- SteamSpy ---------------------------------------------------------------


def fetch_catalogue_page(page: int, session: requests.Session | None = None) -> dict:
    """One `all` page, keyed by appid. Cached on disk; a hit makes no request."""
    path = config.STEAMSPY_ALL_DIR / f"page_{page:03d}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    _PACER.wait("steamspy_all", config.STEAMSPY_ALL_DELAY_SECONDS)
    payload = _http_get(config.STEAMSPY_URL, {"request": "all", "page": page}, session)
    _write_json(path, payload)
    return payload


def fetch_catalogue(max_pages: int | None = None, session: requests.Session | None = None) -> dict:
    """Page through the whole catalogue. Returns {appid: row} across all pages.

    Termination: SteamSpy returns a short page (often an empty one) at the end.
    Both are treated as the end, because a short-but-nonempty final page is the
    common case and waiting for a truly empty one costs another 60 seconds.
    """
    limit = max_pages if max_pages is not None else config.MAX_ALL_PAGES
    state = load_resume()
    catalogue: dict[str, dict] = {}

    for page in range(limit):
        payload = fetch_catalogue_page(page, session)
        catalogue.update(payload)

        if page not in state["catalogue_pages_done"]:
            state["catalogue_pages_done"].append(page)
            save_resume(state)

        print(f"page {page}: {len(payload)} apps (running total {len(catalogue)})", flush=True)

        if len(payload) < config.STEAMSPY_PAGE_SIZE:
            state["catalogue_complete"] = True
            save_resume(state)
            break

        # `all` is sorted by owners descending, so once an entire page sits below
        # the owner floor, no later page can contain a candidate. Verified on the
        # live catalogue: page 17 is entirely the 20,000..50,000 band and page 33
        # entirely 0..20,000. Without this the pull spends an hour at 60s/page
        # fetching apps that are excluded on arrival.
        from src import cohort

        if not cohort.candidate_appids(payload):
            state["catalogue_complete"] = True
            save_resume(state)
            print(f"page {page} is entirely below the owner floor - stopping", flush=True)
            break
    else:
        print(f"stopped at the {limit}-page hard stop - catalogue may be incomplete", flush=True)

    return catalogue


def fetch_app(appid: int, session: requests.Session | None = None) -> dict:
    """SteamSpy detail for one app: owners, playtime medians, ccu, price, tags."""
    path = config.STEAMSPY_APP_DIR / f"{appid}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    _PACER.wait("steamspy_app", config.STEAMSPY_APP_DELAY_SECONDS)
    payload = _http_get(config.STEAMSPY_URL, {"request": "appdetails", "appid": appid}, session)
    _write_json(path, payload)
    return payload


# --- Steam storefront -------------------------------------------------------


def fetch_store(appid: int, session: requests.Session | None = None) -> dict:
    """Storefront appdetails: is_free, genres, release date, AUD price.

    A failed lookup is cached too. Delisted and region-locked apps return
    success=false every time, and without caching that, each re-run pays 1.5s per
    dead app again. How many of these there are is itself a data-quality number
    for the write-up, so the failures are kept rather than dropped.
    """
    path = config.STORE_APP_DIR / f"{appid}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    _PACER.wait("store", config.STORE_DELAY_SECONDS)
    payload = _http_get(
        config.STORE_APPDETAILS_URL,
        {"appids": appid, "cc": config.STORE_COUNTRY, "l": config.STORE_LANGUAGE},
        session,
    )
    # The response is keyed by appid as a string. Unwrap it so callers don't have
    # to know that, but keep the success/data shape intact.
    entry = payload.get(str(appid), {"success": False})
    _write_json(path, entry)
    return entry


def _drain(fetcher, appids: list[int], label: str) -> dict[int, dict]:
    """Run one endpoint over every appid, on its own session and its own pacer.

    Errors are counted, not raised. Over tens of thousands of apps a single bad
    response should not end a pull measured in hours, and nothing is cached for a
    failed fetch, so the next run simply retries it.
    """
    out: dict[int, dict] = {}
    errors = 0

    with requests.Session() as session:
        for index, appid in enumerate(appids, start=1):
            try:
                out[appid] = fetcher(appid, session)
            except SteamAPIError:
                errors += 1
            if index % 500 == 0:
                print(f"  {label}: {index:,}/{len(appids):,} ({errors} errors)", flush=True)

    print(f"  {label}: done, {len(out):,} fetched, {errors} errors", flush=True)
    return out


def enrich(appids: list[int], session: requests.Session | None = None) -> dict[int, dict]:
    """SteamSpy detail + storefront detail for each app, resumable.

    The two endpoints are different hosts with independent rate limits - SteamSpy
    at 1 request/second, the storefront at roughly 1 per 1.5s - so serialising
    them makes every app cost the sum, 2.5s, when it only needs to cost the
    slower of the two. Run as two pipelines they overlap, and the pull takes
    1.5s per app instead: on 26,017 apps that is about 11 hours rather than 18.
    Each pipeline keeps its own session and its own pacer key, so neither
    endpoint's documented limit is exceeded.

    Resumability is the disk cache, not the resume file: both fetchers check the
    cache first, so re-running after an interrupt only fetches what is missing.
    """
    spy: dict[int, dict] = {}
    store: dict[int, dict] = {}

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(_drain, fetch_app, appids, "steamspy"): "spy",
            pool.submit(_drain, fetch_store, appids, "store"): "store",
        }
        for future in futures:
            if futures[future] == "spy":
                spy = future.result()
            else:
                store = future.result()

    state = load_resume()
    state["enriched"] = sorted(set(state.get("enriched", [])) | set(spy) | set(store))
    save_resume(state)

    return {
        appid: {"steamspy": spy.get(appid, {}), "store": store.get(appid, {"success": False})}
        for appid in appids
    }


def recon(appid: int) -> dict:
    """One app, both sources. For sanity-checking field shapes."""
    with requests.Session() as session:
        return {"steamspy": fetch_app(appid, session), "store": fetch_store(appid, session)}


def main(argv: list[str]) -> int:
    console.use_utf8()
    if not argv:
        print(__doc__)
        return 1

    command = argv[0]
    if command == "recon":
        print(json.dumps(recon(int(argv[1])), indent=2)[:4000])
        return 0

    with requests.Session() as session:
        if command == "catalogue":
            catalogue = fetch_catalogue(session=session)
            print(f"catalogue: {len(catalogue)} apps")
        elif command == "enrich":
            from src import cohort

            candidates = cohort.candidate_appids(fetch_catalogue(session=session))
            print(f"{len(candidates)} candidates to enrich")
            enrich(candidates, session)
        else:
            print(f"unknown command: {command}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
