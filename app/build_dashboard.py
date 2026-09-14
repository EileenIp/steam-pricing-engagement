"""Build the self-contained dashboard from dashboard/data.json.

The data is embedded rather than fetched, so the single HTML file works opened
straight off disk as well as served. That matters because this repo has no Pages
site enabled, and a dashboard nobody can open is not a deliverable.

Run: python -m src.export_dashboard && python app/build_dashboard.py
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "dashboard" / "data.json"
OUT = ROOT / "dashboard" / "index.html"

TEMPLATE = """<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>F2P vs Paid — Pricing and Engagement on Steam</title>
<style>
  :root {
    --bg: #161826; --panel: #1E2133; --line: #2C3047;
    --ink: #E9E9ED; --muted: #9AA3B8; --accent: #A78BFA;
    --paid: #A78BFA; --free: #5B6480;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--ink);
         font: 15px/1.6 -apple-system, "Segoe UI", system-ui, sans-serif; }
  .wrap { max-width: 1060px; margin: 0 auto; padding: 40px 22px 80px; }
  .eyebrow { color: var(--accent); letter-spacing: .12em; text-transform: uppercase;
             font-size: 12px; font-weight: 600; }
  h1 { font-size: 30px; margin: 6px 0 8px; line-height: 1.2; }
  .lede { color: var(--muted); max-width: 70ch; margin: 0 0 26px; }
  h2 { font-size: 19px; margin: 36px 0 6px; }
  .note { color: var(--muted); font-size: 13.5px; max-width: 78ch; }
  .panel { background: var(--panel); border: 1px solid var(--line);
           border-radius: 10px; padding: 20px 22px; margin-top: 14px; }
  .controls { display: flex; gap: 22px; flex-wrap: wrap; align-items: center; margin-top: 18px; }
  .control-label { font-size: 12px; color: var(--muted); text-transform: uppercase;
                   letter-spacing: .08em; margin-right: 8px; }
  button { background: transparent; border: 1px solid var(--line); color: var(--muted);
           padding: 6px 13px; border-radius: 999px; cursor: pointer; font: inherit; font-size: 13.5px; }
  button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: #17182A; font-weight: 600; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; margin-top: 14px; }
  .stat .v { font-size: 26px; font-weight: 700; }
  .stat .l { color: var(--muted); font-size: 13px; }
  .hero { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
  @media (max-width: 680px) { .hero { grid-template-columns: 1fr; } }
  .hero .v { font-size: 40px; font-weight: 700; }
  .hero .sub { color: var(--muted); font-size: 13.5px; }
  .moved { margin-top: 14px; font-weight: 600; }
  table { border-collapse: collapse; width: 100%; margin-top: 10px; font-size: 14px; }
  th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font-weight: 600; font-size: 12.5px; text-transform: uppercase;
       letter-spacing: .05em; cursor: pointer; user-select: none; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  .bar { position: relative; height: 15px; background: #252940; border-radius: 3px; min-width: 120px; }
  .bar i { position: absolute; top: 0; bottom: 0; border-radius: 3px; }
  .bar .zero { position: absolute; top: -2px; bottom: -2px; width: 1px; background: var(--muted); opacity: .55; }
  .scroll { overflow-x: auto; }
  footer { margin-top: 44px; color: var(--muted); font-size: 13px; }
  a { color: var(--accent); }
</style>
</head>
<body>
<div class="wrap">
  <div class="eyebrow">Case study dashboard</div>
  <h1>F2P vs Paid: pricing and engagement on Steam</h1>
  <p class="lede">Does going free-to-play actually buy engagement? “Free games have more owners” is a
  tautology — free things get downloaded. This compares how long players actually stay, and whether
  any gap survives comparing like genre with like.</p>

  <div class="controls">
    <span><span class="control-label">Metric</span>
      <button data-metric="playtime" aria-pressed="true">Median playtime</button>
      <button data-metric="ccu_per_owner" aria-pressed="false">CCU per owner</button>
    </span>
    <span><span class="control-label">Owner bound</span>
      <button data-bound="lower" aria-pressed="false">Lower</button>
      <button data-bound="midpoint" aria-pressed="true">Midpoint</button>
      <button data-bound="upper" aria-pressed="false">Upper</button>
    </span>
  </div>

  <h2>The correction that was meant to explain the gap</h2>
  <p class="note">Cliff's delta. Negative means paid games are played longer. −1 would mean every paid
  game outplays every free one; 0 means no separation.</p>
  <div class="panel hero">
    <div><div class="v" id="naive" style="color:var(--free)"></div>
      <div class="sub">naive — all games pooled</div></div>
    <div><div class="v" id="adjusted" style="color:var(--paid)"></div>
      <div class="sub" id="adjusted-sub">genre-adjusted</div></div>
    <div style="grid-column:1/-1" class="moved" id="moved"></div>
  </div>

  <div class="stats" id="stats"></div>
  <p class="note" id="ties" style="margin-top:12px"></p>

  <h2>Within genre</h2>
  <p class="note">Only genres holding at least eight games of each pricing model. Click a column to sort.</p>
  <div class="panel scroll">
    <table id="genres">
      <thead><tr>
        <th data-sort="label">Genre</th>
        <th class="num" data-sort="nF2p">Free</th>
        <th class="num" data-sort="nPaid">Paid</th>
        <th class="num" data-sort="medianF2p">Median free</th>
        <th class="num" data-sort="medianPaid">Median paid</th>
        <th data-sort="delta">Delta (− = paid higher)</th>
      </tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <h2>By price band</h2>
  <p class="note">Paid games only. Price is standing in for production budget, scope and buyer intent —
  none of which this data measures, so this is not a claim that price causes engagement.</p>
  <div class="panel scroll"><table id="bands">
    <thead><tr><th>Band (AUD)</th><th class="num">Games</th><th class="num">Median</th><th>&nbsp;</th></tr></thead>
    <tbody></tbody>
  </table></div>

  <h2>What would weaken this</h2>
  <div class="panel">
    <p class="note" id="uncertainty"></p>
    <p class="note" style="margin-top:12px"><strong>The owner-range uncertainty turned out not to
    matter.</strong> Ownership is reported as a band, never a number, so every result is recomputed at
    the lower bound, the midpoint and the upper bound — switch the control above and watch. The figures
    move by about 0.001, because the comparisons are rank-based and widening the bands barely reorders
    anything. The plan called for an uncertainty ribbon here; it would have been a flat line pretending
    to be information, so the real uncertainty is shown instead.</p>
  </div>

  <footer>
    Generated <span id="generated"></span> ·
    <a href="https://github.com/EileenIp/steam-pricing-engagement">source and method</a> ·
    Playtime is a median over reviewers, not owners — reviewers play more.<span id="exact"></span>
  </footer>
</div>

<script id="payload" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById("payload").textContent);
let metric = "playtime", bound = "midpoint";
let sortKey = "delta", sortDir = 1;

// Round half to even, matching Python's format spec. Math.round rounds half up,
// which made the dashboard read 125 where the report, deck and case study all
// say 124 - the true median is 124.5. One minute is trivial; four deliverables
// disagreeing with each other is not.
function roundHalfEven(v) {
  const f = Math.floor(v);
  const diff = v - f;
  if (diff > 0.5) return f + 1;
  if (diff < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}
const fmt = (v) => v === null || v === undefined ? "—"
  : metric === "playtime" ? roundHalfEven(v).toLocaleString()
  : v === 0 ? "0" : v.toExponential(2);
const sign = (v) => (v > 0 ? "+" : "\\u2212") + Math.abs(v).toFixed(3);

function deltaBar(d) {
  const w = Math.min(Math.abs(d), 1) * 50;
  const left = d < 0 ? 50 - w : 50;
  const colour = d < 0 ? "var(--paid)" : "var(--free)";
  return `<div class="bar"><span class="zero" style="left:50%"></span>
    <i style="left:${left}%;width:${w}%;background:${colour}"></i></div>`;
}

function render() {
  const m = DATA.metrics[metric][bound];
  const c = DATA.cohort;

  document.getElementById("naive").textContent = sign(m.naive.delta);
  document.getElementById("adjusted").textContent = m.adjustedDelta === null ? "—" : sign(m.adjustedDelta);
  document.getElementById("adjusted-sub").textContent =
    `genre-adjusted — ${m.usableGenres} genres`;

  // A metric that is mostly ties shows medians of 0, which reads as broken rather
  // than as the finding it is. Say so on the face of the page.
  const ties = m.naive.tiedAtZero;
  document.getElementById("ties").textContent = ties >= 0.2
    ? `${Math.round(ties * 100)}% of this metric's values are exactly zero, so the medians read 0 and the rank test is mostly ties. That is why playtime carries the headline and this is only a cross-check.`
    : "";

  const moved = m.adjustedDelta - m.naive.delta;
  document.getElementById("moved").textContent = moved < 0
    ? `Adjusting for genre moved the result ${Math.abs(moved).toFixed(3)} further from zero. The correction was meant to shrink the gap; it widened it.`
    : `Adjusting for genre moved the result ${Math.abs(moved).toFixed(3)} toward zero.`;

  document.getElementById("stats").innerHTML = [
    [fmt(m.naive.medianF2p), "median, free games"],
    [fmt(m.naive.medianPaid), "median, paid games"],
    [m.naive.nF2p.toLocaleString() + " / " + m.naive.nPaid.toLocaleString(), "games compared (free / paid)"],
    [c.games.toLocaleString(), "games in the cohort"],
  ].map(([v, l]) => `<div class="stat panel"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");

  const rows = [...m.byGenre].sort((a, b) => {
    const x = a[sortKey], y = b[sortKey];
    return (typeof x === "string" ? x.localeCompare(y) : x - y) * sortDir;
  });
  document.querySelector("#genres tbody").innerHTML = rows.map((g) => `<tr>
    <td>${g.label}</td><td class="num">${g.nF2p}</td><td class="num">${g.nPaid}</td>
    <td class="num">${fmt(g.medianF2p)}</td><td class="num">${fmt(g.medianPaid)}</td>
    <td>${deltaBar(g.delta)}</td></tr>`).join("");

  const maxBand = Math.max(...m.priceBands.map((b) => b.median || 0)) || 1;
  document.querySelector("#bands tbody").innerHTML = m.priceBands.map((b) => `<tr>
    <td>${b.band}</td><td class="num">${b.n.toLocaleString()}</td><td class="num">${fmt(b.median)}</td>
    <td><div class="bar"><i style="left:0;width:${((b.median || 0) / maxBand) * 100}%;background:var(--paid)"></i></div></td>
    </tr>`).join("");

  const a = DATA.attrition;
  document.getElementById("uncertainty").innerHTML =
    `<strong>Attrition is uneven.</strong> ${(c.sampled - c.usable).toLocaleString()} of the
     ${c.sampled.toLocaleString()} sampled games had too few reviewers for a median and were dropped
     rather than given one on thin evidence — ${(a.paid.rate * 100).toFixed(1)}% of paid games against
     ${(a.f2p.rate * 100).toFixed(1)}% of free ones. The paid sample therefore lost more of its small
     titles, and small titles plausibly play shorter, so the gap above is more likely overstated than
     understated.`;

  document.getElementById("generated").textContent = DATA.generated;

  // Medians are shown rounded; the unrounded pair is stated so the whole-minute
  // figures quoted in the report and case study can be checked against it.
  document.getElementById("exact").textContent = metric === "playtime"
    ? ` · Exact medians: ${m.naive.medianF2p} free, ${m.naive.medianPaid} paid (minutes).`
    : "";
}

for (const b of document.querySelectorAll("[data-metric]")) {
  b.onclick = () => {
    metric = b.dataset.metric;
    document.querySelectorAll("[data-metric]").forEach((x) =>
      x.setAttribute("aria-pressed", String(x === b)));
    render();
  };
}
for (const b of document.querySelectorAll("[data-bound]")) {
  b.onclick = () => {
    bound = b.dataset.bound;
    document.querySelectorAll("[data-bound]").forEach((x) =>
      x.setAttribute("aria-pressed", String(x === b)));
    render();
  };
}
for (const th of document.querySelectorAll("#genres th[data-sort]")) {
  th.onclick = () => {
    const key = th.dataset.sort;
    sortDir = key === sortKey ? -sortDir : 1;
    sortKey = key;
    render();
  };
}
render();
</script>
</body>
</html>
"""


def main() -> int:
    data = DATA.read_text(encoding="utf-8")
    # The payload sits in a JSON script block, so only "</" needs escaping to
    # keep the browser's parser from ending the element early.
    html = TEMPLATE.replace("__DATA__", data.replace("</", "<\\/"))
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
