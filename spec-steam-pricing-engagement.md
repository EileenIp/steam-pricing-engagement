# Project spec — F2P vs Paid: Pricing & Engagement on Steam

**For:** Eileen Ip · portfolio project (new build, starts from zero)
**Theme:** Gaming
**Status:** not started. Corrected 2026-09-12 — the earlier "dashboard already built on sample data" claim was wrong; no sample build exists anywhere. This spec covers the whole build: the data pull and the analysis depth that makes it defensible.

---

## The business question

> Does going free-to-play actually buy engagement, and at what price points do paid games hold their players?

The trap this project must avoid: "F2P games have more owners" is not a finding, it's a tautology — free things get downloaded. The real question is whether F2P *engagement* (playtime per owner, retained concurrent players) justifies the model, and whether that holds across genres or is an artifact of which genres go F2P.

**Who cares:** a studio choosing a launch pricing model; a publisher deciding whether to take an ageing paid title F2P.

---

## Phase 0 — Data pull

**Build:**

- Source: SteamSpy API (`https://steamspy.com/api.php`). Respect the documented rate limits — 1 request/second for single-app calls, 60 seconds between `all` pages. Build the puller with caching to disk so a re-run never re-fetches, and a resume file so an interrupted pull continues instead of restarting. Budget: the full catalogue is tens of thousands of apps; pull the `all` pages first, then enrich the analysis subset app-by-app.
- Enrich with the Steam storefront API (`appdetails`) for current price, genres, release date, and F2P flag on the analysis subset.
- Persist raw JSON before any transformation.

**Known data honesty problems — handle these, don't hide them:**

1. **Owner counts are ranges, not numbers** (e.g. "1,000,000 .. 2,000,000") — Steam privacy changes ended exact counts. Everything downstream must treat ownership as an interval.
2. **Playtime medians/averages come only from profiles that are public** — a selection bias worth one honest sentence in the README.
3. Free weekend spikes and bundle giveaways inflate owners without engagement.

**Decision:** how to represent owner ranges in analysis — interval midpoint with a sensitivity check at both bounds is the defensible default; the choice goes in `NOTES.md`. This is a guaranteed interview question because it's visible in every chart.

**Checkpoint 0.**

## Phase 1 — Scope the comparison set

**Decisions, before code:**

- Which games count? Everything since 2015? Only games above some owner floor (tiny games add noise, but excluding them biases toward winners — survivorship)? State the inclusion rule and its bias in one sentence each.
- The engagement metric. Candidates: median playtime (2 weeks), median playtime (forever), average playtime, CCU per (midpoint) owner. Pick one headline metric and one robustness check. Median beats mean here — playtime is savagely skewed — but say so yourself.

**Build:** implement the filter in `config.py`, report how many games survive, broken down F2P vs paid.

**Checkpoint 1.**

## Phase 2 — The analysis that earns the project

**Build:**

- Naive comparison first (F2P vs paid on the headline metric) — then show why it's misleading.
- **Genre confounding is the core analytical move.** F2P concentrates in specific genres (MMO, MOBA, extraction shooters); paid dominates others. Compare within genre, or stratify, and show how the naive gap changes. This is the "why, not just what" layer.
- Price-band analysis for paid games: engagement across bands (e.g. <10, 10–30, 30–60, 60+ AUD), within genre. Where does engagement per dollar peak?
- Release-year cohorts: is the F2P engagement edge (if any) growing or shrinking?
- Statistical honesty: report effect sizes with the owner-range sensitivity bounds, not just point estimates. Mann-Whitney over t-tests given the skew — or justify otherwise.

**Decision:** the interpretation. If the within-genre analysis kills the naive result, that *is* the finding — "the F2P engagement advantage is mostly a genre effect" is a better portfolio story than a confirmation.

**Tests (pytest):** owner-range parsing round-trips correctly; no game appears in both F2P and paid sets; sensitivity bounds bracket the midpoint result; the pull cache returns identical data on re-run.

**Checkpoint 2.**

## Phase 3 — Build the dashboard

**Build:** build the dashboard on the real data. It needs: the naive-vs-genre-adjusted comparison side by side (this is the hero — show the correction happening), price-band view, and an uncertainty ribbon from the owner-range bounds. Keep it self-contained HTML on GitHub Pages, consistent with the portfolio site.

## Phase 4 — Deliverables

Same four-output pattern as the churn spec Phase 7: HTML dashboard (done in Phase 3), short stakeholder deck, 3–4 page report, and a website case study in the portfolio's established structure. Plain language on every surface; method detail behind a toggle or in the appendix.

**To write:** the "what didn't work", limitations (owner ranges, public-profile bias, no revenue data — engagement ≠ monetisation), and the recommendation paragraph.

---

## Readiness gate notes (Appendix-B style, pre-answered)

- **Visualisation-only?** No — the genre-confounding correction and sensitivity analysis are the depth layers. If those get cut for time, the project regresses to a chart gallery; don't ship it that way.
- **Overused data?** SteamSpy analyses exist but mostly do the naive comparison. The within-genre correction + interval-aware uncertainty is the differentiator. Protect it.
- **Business context?** Cleared — pricing-model choice is a real studio decision with real money attached.
- **Tutorial clone?** Low risk; the pull, the interval handling and the genre correction are all custom.

## Screening audit

Run the churn spec's Appendix C scorecard before shipping. The rows most at risk here: **Depth of analysis** (if genre correction is shallow) and **Handling ambiguity** (if owner ranges get silently midpointed with no sensitivity check).

## Definition of done

- [ ] Real SteamSpy + storefront data, cached, re-runnable
- [ ] Owner ranges handled as intervals with sensitivity bounds shown
- [ ] Naive vs genre-adjusted comparison, side by side
- [ ] `pytest` green
- [ ] Four deliverables; case study on the site with real numbers only
- [ ] `NOTES.md` decision log; "what didn't work" written by Eileen
- [ ] Rehearsed answers: why median, why these bounds, why genre stratification, what revenue data would change
