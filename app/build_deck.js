// Builds the stakeholder deck for the F2P vs Paid study.
//   node app/build_deck.js
// One idea per slide, no equations. Every figure comes from the run.
const path = require("path");
const PptxGenJS = require("pptxgenjs");

const INK = "1B2733";
const ACCENT = "1F3A5F";
const MUTED = "6B7785";
const FREE = "9AA7B4";
const PAID = "1F3A5F";

const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_16x9";
pptx.author = "Eileen Ip";
pptx.title = "F2P vs Paid: Pricing and Engagement on Steam";

function slide(title, kicker) {
  const s = pptx.addSlide();
  if (title) {
    s.addText(title, { x: 0.6, y: 0.45, w: 8.8, h: 0.7, fontSize: 28, bold: true, color: ACCENT, fontFace: "Calibri" });
  }
  if (kicker) {
    s.addText(kicker, { x: 0.6, y: 1.15, w: 8.8, h: 0.45, fontSize: 14, color: MUTED, fontFace: "Calibri", italic: true });
  }
  return s;
}

function bullets(s, items, y = 1.9) {
  s.addText(
    items.map((t) => ({ text: t, options: { bullet: { characterCode: "2022" }, breakLine: true } })),
    { x: 0.75, y, w: 8.5, h: 3.0, fontSize: 16, color: INK, fontFace: "Calibri", lineSpacingMultiple: 1.35, valign: "top" },
  );
}

// 1 — title
const title = pptx.addSlide();
title.addText("F2P vs Paid", { x: 0.7, y: 1.7, w: 8.6, h: 0.9, fontSize: 44, bold: true, color: ACCENT, fontFace: "Calibri" });
title.addText("Does going free-to-play actually buy engagement on Steam?", {
  x: 0.7, y: 2.6, w: 8.6, h: 0.6, fontSize: 20, color: INK, fontFace: "Calibri",
});
title.addText("Eileen Ip  ·  September 2026  ·  20,761 games", {
  x: 0.7, y: 3.3, w: 8.6, h: 0.4, fontSize: 13, color: MUTED, fontFace: "Calibri",
});

// 2 — the question
const s2 = slide("The decision this informs", "A studio picking a launch model; a publisher weighing a conversion");
bullets(s2, [
  "Going free-to-play is meant to buy engagement, not just downloads.",
  "“Free games have more owners” is a tautology — free things get downloaded.",
  "The real question: do players who take a free game stay in it as long as players who paid?",
  "And does the answer hold once you stop comparing a free MOBA against a paid visual novel?",
]);

// 3 — the answer
const s3 = slide("The answer: no", "Median playtime per player, 2,797 games with a usable sample");
s3.addText("124", { x: 1.1, y: 2.1, w: 2.6, h: 1.1, fontSize: 60, bold: true, color: FREE, align: "center", fontFace: "Calibri" });
s3.addText("minutes — free", { x: 1.1, y: 3.2, w: 2.6, h: 0.4, fontSize: 15, color: MUTED, align: "center", fontFace: "Calibri" });
s3.addText("530", { x: 5.3, y: 2.1, w: 2.6, h: 1.1, fontSize: 60, bold: true, color: PAID, align: "center", fontFace: "Calibri" });
s3.addText("minutes — paid", { x: 5.3, y: 3.2, w: 2.6, h: 0.4, fontSize: 15, color: MUTED, align: "center", fontFace: "Calibri" });
s3.addText("Paid games are played more than four times as long.", {
  x: 0.75, y: 4.1, w: 8.5, h: 0.5, fontSize: 17, color: INK, fontFace: "Calibri",
});

// 4 — the correction
const s4 = slide("The obvious objection, tested", "Free games might just cluster in genres played less");
s4.addText([
  { text: "So I compared within genre", options: { bold: true } },
  { text: ", across the 58 genres holding enough of both models.", options: {} },
], { x: 0.75, y: 1.85, w: 8.5, h: 0.4, fontSize: 16, color: INK, fontFace: "Calibri" });
// Deliberately not a bar chart. The two values differ by 0.025, and any
// auto-scaled axis renders that as a dramatic difference — which would be a
// misleading picture of a result whose whole point is that almost nothing moved.
s4.addText("−0.457", { x: 1.1, y: 2.45, w: 2.6, h: 0.8, fontSize: 40, bold: true, color: MUTED, align: "center", fontFace: "Calibri" });
s4.addText("naive", { x: 1.1, y: 3.25, w: 2.6, h: 0.35, fontSize: 14, color: MUTED, align: "center", fontFace: "Calibri" });
s4.addText("−0.482", { x: 5.3, y: 2.45, w: 2.6, h: 0.8, fontSize: 40, bold: true, color: PAID, align: "center", fontFace: "Calibri" });
s4.addText("genre-adjusted", { x: 5.3, y: 3.25, w: 2.6, h: 0.35, fontSize: 14, color: MUTED, align: "center", fontFace: "Calibri" });
s4.addText("The correction was meant to shrink the gap. It moved it 0.025 the other way.", {
  x: 0.75, y: 3.95, w: 8.5, h: 0.4, fontSize: 16, bold: true, color: ACCENT, fontFace: "Calibri",
});
s4.addText("Free games are played less inside their own genres too.", {
  x: 0.75, y: 4.4, w: 8.5, h: 0.4, fontSize: 14, color: INK, fontFace: "Calibri",
});

// 5 — where F2P wins
const s5 = slide("Where free-to-play does win", "Median minutes, by genre");
s5.addTable([
  [{ text: "Genre", options: { bold: true } }, { text: "Free", options: { bold: true } }, { text: "Paid", options: { bold: true } }],
  ["Clicker", "530", "218"],
  ["Idler", "2,723", "1,764"],
  ["MMORPG", "1,216", "2,810"],
  ["Visual Novel", "83", "587"],
  ["Racing", "27", "189"],
], {
  x: 0.9, y: 1.95, w: 6.4, colW: [3.0, 1.7, 1.7], fontSize: 14, fontFace: "Calibri",
  color: INK, border: { type: "solid", color: "DDE3EA", pt: 1 }, rowH: 0.32,
});
s5.addText("Free wins only in genres built for long passive sessions — and loses MMORPG, where it should be strongest.", {
  x: 0.75, y: 4.25, w: 8.5, h: 0.6, fontSize: 15, color: INK, fontFace: "Calibri",
});

// 6 — price
const s6 = slide("Price predicts engagement better than the model", "Paid games only, median minutes by AUD band");
s6.addChart(pptx.ChartType.bar, [{
  name: "Median minutes",
  // The value sits in the category label: pptxgenjs's showValue did not render
  // data labels here, and a chart whose magnitudes cannot be read is decoration.
  labels: ["under 10  ·  233", "10–30  ·  630", "30–60  ·  1,420", "60+  ·  2,484"],
  values: [233, 630, 1420, 2484],
}], {
  x: 1.0, y: 1.9, w: 8.0, h: 2.4, barDir: "bar", chartColors: [PAID],
  showValue: true, dataLabelColor: "FFFFFF", dataLabelFontSize: 11,
  catAxisLabelFontSize: 12, valAxisHidden: true, showLegend: false,
});
s6.addText("More than tenfold, end to end. Price is standing in for budget and scope — this is not a claim that price causes engagement.", {
  x: 0.75, y: 4.4, w: 8.5, h: 0.6, fontSize: 14, color: MUTED, fontFace: "Calibri",
});

// 7 — what didn't work
const s7 = slide("What didn't work", "The headline metric died mid-project");
bullets(s7, [
  "The plan used SteamSpy's median playtime. It still serves the field — as zeroes, for all 1,000 apps checked.",
  "Steam's privacy changes removed the sample behind it; the schema stayed.",
  "Rebuilt on per-player playtime from Steam review payloads, which are populated.",
  "Cost: a smaller sample, and reviewers play more than owners do. Both stated, not absorbed.",
]);

// 8 — limitations
const s8 = slide("What would weaken this", "The honest caveats, in order of size");
bullets(s8, [
  "Reviewers are not owners — every playtime figure is biased upward.",
  "Attrition is uneven: 22.5% of paid games dropped for thin review counts against 16.5% of free ones, which likely overstates the gap.",
  "Current prices, not launch prices — a converted title reads as free today.",
  "No revenue data. A game played half as long may still earn more per player.",
]);

// 9 — recommendation
const s9 = slide("What I would do with this", null);
bullets(s9, [
  "Treat a free-to-play launch as a distribution decision, not an engagement one.",
  "Check the genre's session structure before assuming the model transfers.",
  "Pair this with revenue per player before making a pricing call — engagement is half the question, and the half this data cannot answer.",
], 1.7);

const out = path.join(__dirname, "..", "deliverables", "f2p-vs-paid-engagement-deck.pptx");
pptx.writeFile({ fileName: out }).then(() => console.log("wrote", out));
