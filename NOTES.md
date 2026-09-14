# NOTES — decision log

Every judgement call that shaped the result, what the alternatives were, and why
the choice went the way it did. Ordered by when it was made.

**Provenance.** This log was drafted from the build record rather than written
up live, and it says explicitly which decisions were mine and which I delegated.
That distinction matters more than a tidy narrative: a log that claimed I
reasoned through all of it would fall apart under one follow-up question.

---

## 2026-09-13 — Checkpoint 0: owner counts are intervals

**Decision (mine):** carry ownership as an interval. Headline figures use the
interval midpoint; every owner-dependent result is recomputed at the lower and
upper bound.

**Why:** SteamSpy reports ownership as a band — `1,000,000 .. 2,000,000` — because
Steam's privacy changes ended exact counts. The alternatives were to report
everything as a range (most honest, unreadable, and it makes the hero comparison
mushy) or a log-midpoint (better fitted to the skew, but needs a paragraph of
justification and is unfamiliar). Midpoint-with-bounds is the defensible default
and it keeps the uncertainty visible instead of hiding it in a footnote.

**Consequence I did not anticipate:** it turned out not to matter. All three
bounds agree to within 0.001, because the comparisons are rank-based and widening
a band barely reorders anything. The decision that looked like the biggest
interview risk became the easiest thing to defend — and it is why the dashboard
has no uncertainty ribbon.

## 2026-09-13 — Checkpoint 1a: the inclusion rule

**Decision (mine):** released 2015 or later, owner-interval midpoint above 20,000.

**Why 20,000 and not a rounder guess:** SteamSpy's bottom band is literally
`0 .. 20,000`. The floor drops exactly that band and nothing else, so it is
aligned to the data's own granularity rather than cut through the middle of a
band. The alternative — no floor — would have let thousands of near-zero-owner
releases with unstable medians dominate the genre cells.

**The bias, stated because it is real:** survivorship. Games that flopped are
excluded, so the sample tilts toward titles that found an audience. Anything I
say about engagement is about games that got played at all.

**Correction made later:** the comparison was first written as `>=`, which let the
bottom band back in at the upper bound — the exact band the floor exists to drop.
Changed to strict. Now the band that legitimately straddles the floor
(`20,000 .. 50,000`) is the one that moves between bounds, which is what a
sensitivity check is supposed to show.

## 2026-09-13 — Checkpoint 1b: the engagement metric, and its death

**Decision (mine):** median playtime forever as the headline, CCU per owner as
the robustness check. Median over mean because playtime is savagely skewed.

**What went wrong:** the metric had no data behind it. SteamSpy still serves
`median_forever`, `average_forever`, `median_2weeks` and `average_2weeks` — all
four return zero, for every one of the 1,000 apps on the first catalogue page and
for both apps checked by hand. The plain reading is that Steam's profile-privacy
changes removed the sample those figures came from and left the schema behind.
Every option I had chosen between died at once.

**Decision (delegated — I asked for the call to be made):** take playtime from
`author.playtime_forever` on Steam's review endpoint, rather than promote CCU per
owner to headline.

**Why that way, and I want to be able to give this answer:** promoting CCU was
free — the data was already pulled. It was rejected on a measurement argument.
CCU per owner is a concurrency snapshot, structurally harsh on single-player paid
games that have no reason to hold concurrent players, and that sits close enough
to the free-versus-paid axis that the metric would have been partly deciding the
finding before the analysis ran. It was the right call, and the later data proved
it twice over: 54% of the cohort has a CCU of exactly zero, so a rank test on it
is mostly ties.

**What the replacement costs, carried openly:** a median over reviewers is not a
median over owners — people who review have played more, so every playtime figure
is biased upward. It stays comparable *across* games, which is what the question
needs, but it is not an estimate of what a typical owner played.

## 2026-09-13 — Genre stratification runs on tags

**Decision (mine):** stratify on SteamSpy user tags, not Steam storefront genres.

**Why:** the storefront genres are three broad buckets — ELDEN RING is simply
"Action, RPG". The confound this project corrects for lives at the level of MOBA
versus Souls-like. Correcting on the broad buckets would have been a correction
in name only.

**Two guards that turned out to be necessary (delegated):**

1. **Circularity.** Dota 2's highest-voted tag is "Free to Play" at 60,040 votes,
   three times the next. A top-tag rule would have sorted every free game into a
   "Free to Play" stratum, leaving no cell containing both models — the strata
   would have restated the variable under test. Business-model tags are excluded
   by name.
2. **Descriptors.** Most high-voted tags are not genres: "Difficult", "Dark
   Fantasy", "Third Person", "Indie". A blocklist would never be finished, so the
   vocabulary is an explicit allowlist. Every cell assignment is inspectable — I
   can say exactly why any game landed in any stratum.

**Revised after auditing it:** the first version ranked eligible tags by votes and
put 65% of the cohort into umbrella buckets like "Action" or "Casual" — no better
than the storefront genres it replaced. Specific tags now beat umbrellas
regardless of vote count, which brought that to 18%. The audit is the reason I
know that number rather than assuming the vocabulary worked.

## 2026-09-13 — Software excluded from a games comparison

**Decision (delegated):** drop apps whose storefront genre is Utilities, Design &
Illustration and similar. 261 of the cohort.

**Why:** Steam sells software as well as games. A wallpaper app's playtime means
something entirely different, and averaging it into a pricing-and-engagement
comparison across games is just wrong. Found by auditing what the genre
vocabulary failed to classify — the misses were not missing genres, they were
non-games.

## 2026-09-15 — Checkpoint 2: the interpretation

**Status: open. This is the one I have not made yet.**

The numbers are in and they are not what I expected. I predicted the naive
free-versus-paid gap would prove largely a genre effect; instead the gap survives
genre adjustment and widens slightly (-0.457 to -0.482 across 58 genres). Free
games are played less inside their own genres too.

The interpretation currently written into the report, deck and case study is not
mine. Two claims in particular need to be, because they are the ones an
interviewer will push on:

- **The causal hedge on price.** Median playtime climbs more than tenfold from the
  cheapest price band to the most expensive. I do not think price causes
  engagement; I think price is standing in for production budget, scope and buyer
  intent, none of which this data measures. I need to be able to say why I
  believe that rather than reciting it.
- **The recommendation to pair this with revenue.** Engagement is half the
  question. A free game played half as long may still earn more per player, and
  this study cannot tell you. Whether that makes the finding actionable or merely
  suggestive is a judgement I should make explicitly.

## Limitations I decided to state rather than fix

- **Uneven attrition.** 700 of 3,497 sampled games had fewer than 30 reviewers and
  were dropped rather than given a median on thin evidence — 22.5% of paid games
  against 16.5% of free ones. The paid sample lost more of its small titles, and
  small titles plausibly play shorter, so the headline gap is more likely
  overstated than understated. I chose the threshold knowing it would bite
  unevenly; a median over five reviewers is worse than no median.
- **Current state, not launch state.** Both sources report what is true today, so
  a paid game that went free years ago reads as free. This cannot speak to what a
  conversion does to a specific title — that needs a before-and-after on the same
  game.
- **No revenue data at all.** Engagement is not monetisation.
