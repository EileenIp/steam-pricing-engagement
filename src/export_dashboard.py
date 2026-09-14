"""Snapshot the analysis into one JSON file for the dashboard.

The dashboard renders numbers; it does not compute them. Everything here comes
from the same functions the report and the case study were written from, so the
page cannot drift from the analysis by quietly recalculating something its own
way.

Run: python -m src.export_dashboard
"""
from __future__ import annotations

import json
from datetime import date

from src import analysis, cohort, config, console, playtime


def _comparison(c) -> dict:
    return {
        "label": c.label,
        "nF2p": c.n_f2p,
        "nPaid": c.n_paid,
        "medianF2p": c.median_f2p,
        "medianPaid": c.median_paid,
        "delta": c.delta,
        "p": c.p_value,
        "tiedAtZero": c.tied_at_zero,
        "usable": c.usable,
    }


def build() -> dict:
    games = cohort.load_cohort(lambda: (_ for _ in ()).throw(
        RuntimeError("cohort cache missing - run: python -m src.analysis full --refresh")))

    sample, _ = playtime.stratified_sample(games)
    samples = {g.appid: playtime.sample_playtime(g.appid) for g in sample}

    attrition = {"f2p": [0, 0], "paid": [0, 0]}
    for game in sample:
        attrition[game.pricing][0 if samples[game.appid].usable else 1] += 1

    out: dict = {
        "generated": date.today().isoformat(),
        "cohort": {
            "games": len(games),
            "f2p": sum(1 for g in games if g.pricing == "f2p"),
            "paid": sum(1 for g in games if g.pricing == "paid"),
            "sampled": len(sample),
            "usable": sum(1 for s in samples.values() if s.usable),
        },
        "attrition": {
            k: {"usable": v[0], "dropped": v[1], "rate": v[1] / (v[0] + v[1])}
            for k, v in attrition.items()
        },
        "metrics": {},
    }

    for name, accessor in (
        ("playtime", analysis.metric_accessor("playtime", samples)),
        ("ccu_per_owner", analysis.metric_accessor("ccu_per_owner")),
    ):
        bounds = {}
        for bound in config.OWNER_BOUNDS:
            naive = analysis.naive(games, accessor, bound)
            genres = analysis.within_genre(games, accessor, bound)
            pooled, cells = analysis.genre_adjusted_delta(genres)
            bounds[bound] = {
                "naive": _comparison(naive),
                "adjustedDelta": pooled,
                "usableGenres": cells,
                "byGenre": [_comparison(g) for g in genres if g.usable],
                "priceBands": [
                    {"band": b, "n": n, "median": m}
                    for b, n, m in analysis.price_bands(games, accessor, bound)
                ],
            }
        out["metrics"][name] = bounds

    return out


def main(argv: list[str]) -> int:
    console.use_utf8()
    data = build()
    path = config.PROJECT_ROOT / "dashboard" / "data.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"wrote {path} ({path.stat().st_size:,} bytes)")
    print(f"  cohort {data['cohort']['games']:,} | "
          f"usable playtime {data['cohort']['usable']:,} | "
          f"genres {data['metrics']['playtime']['midpoint']['usableGenres']}")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
