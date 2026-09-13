// Builds the written report for the F2P vs Paid study.
//   node app/build_report.js
// Every figure here comes from the run; nothing is illustrative.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, LevelFormat,
} = require("docx");

const ACCENT = "1F3A5F";
const MUTED = "555555";
const TABLE_W = 9070; // DXA, fits A4 with default margins

const p = (text, opts = {}) =>
  new Paragraph({
    spacing: { after: opts.after === undefined ? 140 : opts.after },
    alignment: opts.align,
    children: [new TextRun({ text, size: opts.size || 21, color: opts.color, italics: opts.italics, bold: opts.bold })],
  });

const h = (text, level) =>
  new Paragraph({ heading: level, spacing: { before: 260, after: 130 }, children: [new TextRun({ text, color: ACCENT })] });

const bullet = (text) =>
  new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 90 }, children: [new TextRun({ text, size: 21 })] });

function cell(text, { bold = false, header = false, width } = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: header ? { type: ShadingType.CLEAR, fill: "EEF2F7" } : undefined,
    margins: { top: 70, bottom: 70, left: 110, right: 110 },
    children: [new Paragraph({ children: [new TextRun({ text, bold: bold || header, size: 20 })] })],
  });
}

function table(headers, rows, widths) {
  return new Table({
    columnWidths: widths,
    width: { size: TABLE_W, type: WidthType.DXA },
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((t, i) => cell(t, { header: true, width: widths[i] })) }),
      ...rows.map((r) => new TableRow({ children: r.map((t, i) => cell(String(t), { width: widths[i], bold: i === 0 })) })),
    ],
  });
}

const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360, hanging: 220 } } } }],
    }],
  },
  styles: { default: { document: { run: { font: "Calibri", size: 21 } } } },
  sections: [{
    children: [
      new Paragraph({
        spacing: { after: 60 },
        border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 8 } },
        children: [new TextRun({ text: "F2P vs Paid: Pricing and Engagement on Steam", bold: true, size: 34, color: ACCENT })],
      }),
      p("Does going free-to-play actually buy engagement, and at what price points do paid games hold their players?", { italics: true, color: MUTED, after: 60 }),
      p("Eileen Ip · September 2026 · 20,761 games analysed", { color: MUTED, size: 19, after: 240 }),

      h("The answer", HeadingLevel.HEADING_1),
      p("Going free-to-play does not buy engagement on Steam. Across 20,761 games released since 2015, free games have a median playtime of 124 minutes against 530 minutes for paid games — a gap of more than four to one."),
      p("The obvious objection is that free games cluster in genres that are simply played less: a free MOBA against a paid visual novel is not a fair comparison. So I compared within genre, across the 58 genres that hold at least eight games of each pricing model. That correction was meant to shrink the gap. It widened it, from a Cliff's delta of −0.457 to −0.482."),
      p("The finding is therefore not that the free-to-play engagement advantage is mostly a genre effect. It is that there is no advantage to explain. Free games are played less within their own genres too."),

      h("Why the obvious analysis is worthless", HeadingLevel.HEADING_1),
      p("“Free-to-play games have more owners” is a tautology, not a finding: free things get downloaded. Any study that reports it has measured the price, not the product. The question a studio actually faces is whether players who take a free game stay in it as long as players who paid for one — and whether the answer survives controlling for what kind of game it is."),
      p("Two decisions shaped everything downstream, and both are visible in every number below."),
      bullet("Ownership is a range, not a number. SteamSpy reports bands (“1,000,000 .. 2,000,000”) because Steam's privacy changes ended exact counts. Ownership is carried as an interval throughout, and every owner-dependent result is recomputed at the lower bound, the midpoint and the upper bound."),
      bullet("Genre had to come from user tags, not store genres. Steam's storefront genres are three broad buckets — ELDEN RING is simply “Action, RPG”. The confound this study corrects for lives at the level of MOBA against Souls-like, which only the tags capture."),

      h("The data", HeadingLevel.HEADING_1),
      p("The full SteamSpy catalogue (27,021 apps) enriched app by app from the Steam storefront for AUD price, genres, release date and the free-to-play flag: 26,017 apps, 52,034 requests, 7 failures. Playtime comes from Steam review payloads — per-player figures, sampled at up to 200 reviewers per game across 3,497 games chosen to balance the comparison."),
      table(
        ["Stage", "Count", "Note"],
        [
          ["Catalogue", "27,021 apps", "Paging stops where owners fall below the floor"],
          ["Above owner floor", "26,017", "Released 2015+, owner midpoint above 20,000"],
          ["Comparison set", "20,761 games", "3,062 free / 17,699 paid"],
          ["Excluded", "5,256", "3,052 pre-2015, 1,790 no usable price, 261 software, 153 undated"],
          ["Playtime sample", "3,497 games", "Stratified by genre and pricing model"],
          ["Usable after attrition", "2,797", "700 had fewer than 30 reviewers"],
        ],
        [2200, 1900, 4970],
      ),
      p("", { after: 200 }),

      h("Method", HeadingLevel.HEADING_1),
      p("Playtime is severely skewed — a handful of thousand-hour players drag any mean off the map — so every comparison is rank-based: Mann-Whitney U with tie and continuity corrections, and Cliff's delta as the effect size. Delta reads directly: −1 means every paid game outplays every free one, 0 means no separation."),
      p("The effect size leads and the p-value follows. At this sample size almost anything is statistically significant, so significance says little about magnitude; an effect size next to a visible cell count claims less and means more."),
      p("Within-genre results are pooled by pairwise weight, and only across cells holding at least eight games of each model — a stratified estimate built from cells too thin to read individually would launder the same noise."),

      h("Results", HeadingLevel.HEADING_1),
      table(
        ["Comparison", "Free", "Paid", "Cliff's delta"],
        [
          ["Median playtime (minutes)", "124", "530", "−0.457"],
          ["Genre-adjusted, 58 genres", "—", "—", "−0.482"],
          ["Games compared", "1,198", "1,599", ""],
        ],
        [3400, 1600, 1600, 2470],
      ),
      p("", { after: 160 }),
      p("The three owner bounds agree to within 0.001. The interval assumption is the most visible judgement call in the study, and it does not drive the conclusion — because the comparisons are rank-based, widening or narrowing the bands barely reorders anything."),

      h("Where free-to-play does win", HeadingLevel.HEADING_2),
      p("Free-to-play wins in exactly one genre and ties in a second. Both are built around long, low-intensity sessions, and in both the free model is native rather than a discount."),
      table(
        ["Genre", "Free (min)", "Paid (min)", "Delta"],
        [
          ["Clicker", "530", "218", "+0.353"],
          ["Idler", "2,723", "1,764", "+0.007"],
          ["MMORPG", "1,216", "2,810", "−0.392"],
          ["Visual Novel", "83", "587", "−0.726"],
          ["Racing", "27", "189", "−0.827"],
        ],
        [3400, 1900, 1900, 1870],
      ),
      p("", { after: 160 }),
      p("MMORPG is the informative loss. It is the genre where a free model should have its strongest case — persistent worlds, long tails, monetisation built in — and paid titles still hold more than twice the playtime."),

      h("Price beats the pricing model", HeadingLevel.HEADING_2),
      p("Among paid games, median playtime rises monotonically with price, more than tenfold from the cheapest band to the most expensive."),
      table(
        ["Price band (AUD)", "Games", "Median playtime"],
        [
          ["Under 10", "549", "233 min"],
          ["10–30", "807", "630 min"],
          ["30–60", "201", "1,420 min"],
          ["60+", "42", "2,484 min"],
        ],
        [3000, 2000, 4070],
      ),
      p("", { after: 160 }),
      p("This is the strongest signal in the study, and it is not a claim that price causes engagement. Price is standing in for production budget, scope and buyer intent — none of which this data measures. A separate cross-check on concurrent players per owner, computed across the whole 20,761-game cohort rather than the sample, reproduces the same gradient independently."),

      h("What didn't work", HeadingLevel.HEADING_1),
      p("The headline metric died mid-project. The plan was to use SteamSpy's median playtime, which it still serves — as zeroes. All four playtime fields return zero for every one of the 1,000 apps on the first catalogue page, and for both apps I spot-checked by hand. The plain reading is that Steam's profile-privacy changes removed the sample those figures were derived from, leaving the old schema in place. Every playtime option the plan offered died at once."),
      p("The metric was rebuilt on per-player playtime from Steam review payloads, which are populated. That buys real data at the cost of a smaller sample and a second selection bias, both stated below."),
      p("Two further approaches were tried and rejected before the results above were possible."),
      bullet("Ranking genre tags by vote count. Dota 2's highest-voted tag is “Free to Play” at 60,040 votes, three times the next. That rule would have sorted every free game into a “Free to Play” stratum and left no cell containing both models — the strata would have restated the variable under test. Business-model tags are now excluded by name."),
      bullet("Using the highest-voted eligible tag. Steam's umbrella tags outrank the informative ones on most games, so this put 65% of the cohort into buckets like “Action” or “Casual” — no better than the store genres the tags were meant to replace. Specific tags now beat umbrellas regardless of votes, which brought that to 18%."),

      h("Limitations", HeadingLevel.HEADING_1),
      bullet("A median over reviewers is not a median over owners. People who write reviews have played more than people who don't, so every playtime figure is biased upward. It stays comparable across games, which is what the question needs, but it is not an estimate of what a typical owner played."),
      bullet("Attrition is uneven. 700 of the 3,497 sampled games had fewer than 30 reviewers and were dropped rather than given a median on thin evidence — 22.5% of paid games against 16.5% of free ones. The paid sample therefore lost more of its small titles, and small titles plausibly play shorter, so the gap is more likely overstated than understated."),
      bullet("Current state is not launch state. Both sources report what is true today, so a paid game that went free years ago reads as free. This study cannot say what conversion does to a specific title; that needs a before-and-after on the same game."),
      bullet("Survivorship. The owner floor excludes games that flopped, tilting the sample toward titles that found an audience."),
      bullet("Engagement is not monetisation. There is no revenue data here at all. A free game that plays half as long may still earn more per player."),

      h("What I would do with this", HeadingLevel.HEADING_1),
      bullet("Treat a free-to-play launch as a distribution decision, not an engagement one. It buys reach; this data gives no reason to expect it to buy time played."),
      bullet("Check the genre's session structure before assuming the model transfers. Free-to-play held its own only in loops designed for long passive play."),
      bullet("Pair this with revenue per player before making a pricing call. Engagement is half the question, and the half this data cannot answer."),

      h("Reproducing it", HeadingLevel.HEADING_1),
      p("Every API response is cached to disk untransformed, so a re-run returns identical data and an interrupted pull resumes rather than restarting. 105 tests cover the pull, the cohort construction, the interval handling and the statistics — including the rank test, which is implemented directly rather than imported."),
      p("Source: github.com/EileenIp/steam-pricing-engagement", { color: MUTED, size: 19 }),
    ],
  }],
});

const out = path.join(__dirname, "..", "deliverables", "f2p-vs-paid-engagement-report.docx");
Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(out, buf);
  console.log("wrote", out, buf.length, "bytes");
});
