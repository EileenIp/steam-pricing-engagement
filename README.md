# F2P vs Paid: Pricing & Engagement on Steam

> Does going free-to-play actually buy engagement, and at what price points do paid
> games hold their players?

The trap this project exists to avoid: "F2P games have more owners" is not a finding,
it is a tautology — free things get downloaded. The question is whether F2P
*engagement* justifies the model, and whether any gap survives once you compare
within genre instead of across the whole catalogue.

**Status:** Phases 0 and 1 built and tested; Phase 2's metric layer built after the
original metric turned out to have no data behind it. Catalogue pull running. Full
plan: `spec-steam-pricing-engagement.md`.

## Current state

| Piece | State |
|---|---|
| SteamSpy catalogue puller (`all` pages, cache, resume) | Built, tested, live-verified |
| Storefront enrichment (price, genres, release date, is_free) | Built, tested, live-verified |
| Owner-range interval handling + sensitivity bounds | Built, tested |
| Inclusion rule (2015+, 20k owner floor) | Built, tested |
| Headline engagement metric | Rebuilt on review payloads after SteamSpy's fields came back empty |
| Genre stratification on SteamSpy tags | Built, tested, audited on 1,000 games |
| Catalogue pull | Complete — 27,021 apps, 26,017 above the owner floor |
| Stratified sampling by (pricing, genre) | Built, tested |
| Naive vs genre-adjusted comparison | Run on the full cohort, both metrics |
| Rank statistics (Mann-Whitney, Cliff's delta) | Built, tested |
| Playtime pull | Complete — 3,497 games, 0 failures |
| Written report (4pp) | Done — `deliverables/` |
| Stakeholder deck (9 slides) | Done — `deliverables/` |
| Website case study | Written — `deliverables/case-study-entry.json` |
| Dashboard | Done — `dashboard/index.html`, self-contained |

## Decisions so far

Eileen's calls, 2026-09-13:

- **Owner ranges (Checkpoint 0).** Headline figures use the interval midpoint;
  every owner-dependent result is re-run at the lower and upper bound and the
  spread is shown as an uncertainty ribbon. The cohort itself is rebuilt at each
  bound, because the owner floor is applied to an interval — a game straddling
  the floor is in at the upper bound and out at the lower one, and reporting a
  single cohort size would hide that.
- **Inclusion rule (Checkpoint 1a).** Released 2015 or later, owner-interval
  midpoint at or above 20,000. The floor is band-aligned rather than arbitrary:
  SteamSpy's bottom band is literally `0 .. 20,000`, midpoint 10,000, so the rule
  drops exactly that band. Bias, to be stated plainly on the page: survivorship —
  games that flopped are excluded, so the sample tilts toward titles that found
  an audience.
- **Engagement metric (Checkpoint 1b).** Median playtime forever, with CCU per
  owner as the robustness check. **Revised the same day**, after the chosen
  metric was found to have no data behind it — see below.
- **Genre stratification.** On SteamSpy user tags, not Steam storefront genres —
  see below for why the storefront genres were not good enough and what the tags
  needed before they could be used.

## What didn't work: SteamSpy no longer carries playtime

The chosen headline metric has no data behind it. SteamSpy still returns the
fields, but they are zero:

| Field | Present in top-1000 `all` page | Non-zero |
|---|---|---|
| `median_forever` | 1000 | **0** |
| `average_forever` | 1000 | **0** |
| `median_2weeks` | 1000 | **0** |
| `average_2weeks` | 1000 | **0** |
| `ccu` | 1000 | 965 |

Verified 2026-09-13 against the live API, on the top 1,000 apps by owners and on
two spot-checked apps (Dota 2, ELDEN RING). This is not a bug in the puller — the
fields are served, they just carry nothing. The plain reading is that Steam's
profile-privacy changes removed the sample SteamSpy derived playtime from, and the
zeroed fields are a leftover of the old schema.

Every playtime option the spec offered (median forever, median 2 weeks, average)
dies with it. Only `ccu` survives on this source.

**What was done about it.** Playtime now comes from Steam's own review payloads:
`author.playtime_forever`, which is populated (200 reviewers, median 5,761.5
minutes for ELDEN RING, verified live). CCU per owner is kept as a second metric
computed on the whole cohort.

The alternative was to promote CCU per owner to headline, which needs no new pull
at all. It was rejected on a measurement argument: CCU is a concurrency snapshot,
structurally harsh on single-player paid games that have no reason to hold
concurrent players — close enough to the F2P-vs-paid axis that the metric would
be partly deciding the finding before the analysis ran.

What the replacement costs, carried openly rather than absorbed:

- **A median over reviewers is not a median over owners.** People who review have
  played more than people who don't, so every playtime figure here is biased
  upward. It stays comparable *across* games, which is what the question needs,
  but it is not an estimate of what a typical owner played.
- **Recent-reviewer skew.** Pages come back newest-first, so a long-lived game's
  sample is its current reviewers, not its launch cohort. The alternative sort is
  by helpfulness, which re-orders as votes accrue and would make the pull
  unreproducible. Reproducibility won.
- **Sampling.** A review pull per game is seconds and the cohort is thousands of
  games, so playtime runs on a stratified sample by (pricing, primary genre) —
  stratified rather than random because genre confounding is the project's core
  analytical move, and random sampling would leave the smaller genre cells too
  thin to compare within. Cells below the threshold are reported as thin rather
  than quietly analysed.

## Genre stratification runs on tags, not storefront genres

Comparing within genre is the analytical move this project turns on — the naive
F2P-vs-paid gap is expected to be largely a genre effect, and showing that
correction happen is the hero chart. So the resolution of the genre variable
decides how much the correction is worth.

Steam's storefront genres are three broad buckets. ELDEN RING is "Action, RPG";
Dota 2 is "Action, Strategy". The confound this project is about does not live at
that resolution — it lives at MOBA vs Souls-like. SteamSpy's user tags carry it,
so the strata come from tags.

Tags cannot be used raw, and the reason is visible in Dota 2's own tag list:

| Tag | Votes |
|---|---|
| **Free to Play** | **60,040** |
| MOBA | 20,225 |
| Multiplayer | 15,411 |
| Strategy | 14,289 |

Its highest-voted tag is the pricing model, by a factor of three. Taking the top
tag would sort every F2P game into a "Free to Play" stratum and every paid game
elsewhere, so no cell would contain both and the within-genre comparison would
have nothing left to compare — the strata would be a restatement of the variable
under test. Business-model tags are therefore excluded by name.

The second problem is that most high-voted tags are not genres at all —
"Difficult", "Dark Fantasy", "Third Person", "Indie", "Atmospheric". A blocklist
of those would never be finished, so the vocabulary is an explicit allowlist in
`config.py`: a tag is a genre only if it is listed. Every cell assignment is then
inspectable — it can be said exactly why any game landed in any stratum. Live
check: ELDEN RING strata as **Souls-like**, where the storefront said only
"Action".

The allowlist is a judgement call, and an incomplete one until the catalogue
lands. `python -m src.cohort coverage` reports what share of the cohort it
classifies, **split by pricing model** — a coverage gap that falls unevenly on
F2P vs paid thins one side of every comparison, which is a bias rather than
merely a gap — and names the tags the unclassified games would otherwise have
fallen into, ranked by how many games each would rescue. The vocabulary grows
from that, not from guesswork.

Games the vocabulary cannot place stay in the cohort — they still have a pricing
model and an engagement figure — but are never used to support a within-genre
claim. Steam's broad genre is kept on every game alongside the tag stratum, so
the correction can be shown at both resolutions; if the naive gap survives the
three broad buckets but dies under tags, that difference is itself the argument
for why the finer correction was necessary.

## What the genre audit found

The vocabulary was audited against a seeded 1,000-game sample (~42 minutes of
enrichment; the full candidate set is 26,017 apps, which at ~2.5s each is about
18 hours). Three things came out of it, and only the first was the one being
looked for.

**Coverage was never the problem.** The 94-tag vocabulary classified 99.3% of the
sampled cohort. The handful it missed were not missing genres — they were
Utilities, Design & Illustration and VR, i.e. software rather than games. Those
are now excluded on the storefront's own genre labels, and counted: 13 of the
1,000 sampled apps were software. A pricing-and-engagement comparison should not
be averaging in a wallpaper app, whose playtime means something entirely
different.

**Specificity was the problem.** 99.3% coverage was hollow. Ranking eligible tags
by votes put **65% of the cohort into a broad bucket** — Action, Adventure and
Casual alone took 40% — because Steam's umbrella tags out-vote the informative
ones on almost every game. A game tagged `Action 5,000 / Roguelike 3,000` was
being labelled "Action". That is no better than the three storefront buckets tags
were brought in to replace.

The rule is now tiered: a specific tag beats an umbrella tag regardless of votes,
and umbrellas are reached only when a game has nothing more specific. Broad-bucket
share fell from 65% to 18%, and the strata became real ones — Point & Click, FPS,
Visual Novel, Psychological Horror, JRPG, 3D Platformer.

**And that exposed the real constraint.** The two pressures pull against each
other: too broad and the correction is worthless, too specific and the cells
empty out. F2P is only ~16% of the cohort, so once it is spread across 84 strata
the F2P side of most cells is thin. In the 1,000-game sample, exactly **one**
genre has at least 8 games of each pricing model — the within-genre comparison
has almost nothing to stand on at that scale.

This is a sampling limit, not a dead end: 45 genres already contain at least one
game of each model in a 3.8% sample, so the full pull should populate many of
them. But it settles a question that was open — the 18-hour full enrichment is
not optional for the core analytical move. The sample was only ever enough for
vocabulary work.

## What the sample run of the analysis showed

The Phase 2b machinery was built and validated against the 1,000-game audit
sample while the full enrichment ran. It works end to end — naive comparison,
within-genre correction, price bands, release cohorts, all at three owner
bounds — and it produced **no conclusion**, for a reason worth recording.

More than half the cohort has a concurrent-player count of zero: 56% of F2P
games and 51% of paid. CCU per owner is therefore mostly ties, and a rank test
on mostly-ties has very little power. The only genre cell large enough to use at
sample scale is 86% tied at zero, so even that number means nothing. The tie
share is now printed beside every result rather than left to be discovered.

This is a second, independent argument for the metric decision: CCU per owner
was rejected as the headline on a measurement argument (it penalises
single-player paid games structurally), and it turns out to also be degenerate
across most of the catalogue. It remains useful as a cross-check on the games
that *do* hold concurrent players, which is what a cross-check is for.

A formatting bug surfaced at the same time and is worth noting because of how it
looked: every CCU median printed as `0`. The values are around 1e-5, and a single
format string cannot span those and playtime's thousands of minutes. It read
exactly like a broken metric.

## The result

Median playtime, F2P against paid, on 2,797 games with a usable reviewer sample:

| | F2P | paid |
|---|---|---|
| median playtime (minutes) | 124 | 530 |
| n | 1,198 | 1,599 |

Cliff's delta **-0.457** naive, **-0.482** genre-adjusted across 58 genres, and
identical at all three owner bounds.

The spec expected the naive gap to prove mostly a genre effect. It is wrong
twice over. There is no F2P engagement advantage to explain away — paid games
out-play free ones more than four to one — and correcting for genre makes paid's
lead *slightly larger*, not smaller. Whatever drives this, it is not that F2P
concentrates in genres that happen to play short.

The exceptions are the interesting part. F2P wins in exactly the genres built
around long passive sessions, and loses everywhere else:

| genre | F2P | paid | delta |
|---|---|---|---|
| Clicker | 530 | 218 | **+0.353** |
| Idler | 2,723 | 1,764 | +0.007 |
| MMORPG | 1,216 | 2,810 | -0.392 |
| Visual Novel | 83 | 587 | -0.726 |
| Racing | 27 | 189 | -0.827 |

And price, not pricing model, is the stronger signal — the same direction the
CCU cross-check found, which is what a cross-check is for:

| band (AUD) | n | median playtime |
|---|---|---|
| 0–10 | 549 | 233 |
| 10–30 | 807 | 630 |
| 30–60 | 201 | 1,420 |
| 60+ | 42 | 2,484 |

**What would weaken this.** 700 of the 3,497 sampled games (20%) had fewer than
30 reviewers and were dropped rather than given a median on thin evidence. That
attrition is uneven — 22.5% of paid games against 16.5% of F2P — so the paid
sample lost more of its small titles, and small titles plausibly play shorter.
The gap is therefore more likely overstated than understated. On top of that,
every figure is a median over reviewers rather than over owners, and reviewers
play more than owners do.

## Deliverables

- `deliverables/f2p-vs-paid-engagement-report.docx` — the written report, four
  pages, built by `app/build_report.js`.
- `deliverables/f2p-vs-paid-engagement-deck.pptx` — nine slides for a
  non-technical audience, built by `app/build_deck.js`.
- `deliverables/case-study-entry.json` — the portfolio case study, now live on
  the site.
- `dashboard/index.html` — the interactive dashboard. Data is embedded rather
  than fetched, so the single file works opened straight off disk as well as
  served; this repo has no Pages site, and a dashboard nobody can open is not a
  deliverable. Rebuild with `python -m src.export_dashboard && python
  app/build_dashboard.py`.

The dashboard answers the spec's request for an owner-range uncertainty ribbon by
not drawing one. The bounds move every result by about 0.001, so a ribbon would
be a flat line pretending to be information. Instead the bound is a control: flip
it and watch nothing happen, which is the finding. The uncertainty that does
matter — uneven reviewer attrition — is stated on the page.

Both documents were rendered and read before committing, not just generated. That
caught a genuinely misleading chart: the naive and genre-adjusted effect sizes
differ by 0.025, and an auto-scaled bar axis drew them as a dramatic gap. It is
now two numbers side by side, which is what a 5% difference honestly looks like.

## Running it

```bash
pip install -r requirements.txt
python -m src.steamspy_fetch recon 570        # one app, both sources, to eyeball shapes
python -m src.steamspy_fetch catalogue        # the `all` pages — slow, 60s between pages
python -m src.cohort report                   # cohort size F2P vs paid, at all three bounds
python -m src.cohort coverage                 # genre-vocabulary coverage, and what it misses
python -m src.playtime one 1245620            # one game's playtime median from reviews
python -m src.playtime sample                 # the stratified playtime pull
python -m src.analysis sample                 # naive vs genre-adjusted, all bounds
pytest
```

The catalogue pull takes hours by design: SteamSpy's published limits are 60
seconds between `all` pages and 1 request/second for per-app calls, and being
throttled mid-run costs more than the wait. Everything is cached to `data/raw/`
untransformed, so a re-run is free and returns identical data, and a resume file
means an interrupted pull continues instead of restarting.

## Known data-honesty problems

These are handled in code, not hidden, and belong in the write-up:

1. **Owner counts are ranges, not numbers.** Carried as intervals throughout,
   never silently collapsed.
2. **Current state is not launch state.** A paid game that went free-to-play later
   reads as F2P today, because both sources report what is true now. That is also
   precisely the publisher decision this project is about, so it is a stated
   limitation rather than a defect.
3. **Free weekends and bundle giveaways inflate owners without engagement.**
4. **Delisted and region-locked apps** return a permanent failure from the
   storefront. Those failures are cached and counted, so the number that dropped
   out is reportable instead of invisible.
5. **Engagement is not monetisation.** There is no revenue data here at all.
