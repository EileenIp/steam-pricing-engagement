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
| Genre stratification on SteamSpy tags | Built, tested, live-verified |
| Stratified sampling by (pricing, genre) | Built, tested |
| Naive vs genre-adjusted comparison | Not started |
| Dashboard, deliverables, case study | Not started |

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

## Running it

```bash
pip install -r requirements.txt
python -m src.steamspy_fetch recon 570        # one app, both sources, to eyeball shapes
python -m src.steamspy_fetch catalogue        # the `all` pages — slow, 60s between pages
python -m src.cohort report                   # cohort size F2P vs paid, at all three bounds
python -m src.cohort coverage                 # genre-vocabulary coverage, and what it misses
python -m src.playtime one 1245620            # one game's playtime median from reviews
python -m src.playtime sample                 # the stratified playtime pull
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
