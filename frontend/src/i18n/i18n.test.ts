import { describe, expect, it } from "vitest";
import en from "./en.json";
import es from "./es.json";

function keyPaths(obj: unknown, prefix = ""): string[] {
  if (obj === null || typeof obj !== "object") return [prefix];
  return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
    keyPaths(v, prefix ? `${prefix}.${k}` : k),
  );
}

// Keep in sync with the ExerciseType union in src/api/course.ts.
const EXERCISE_TYPES = ["quiz", "calculation", "synthetic_chart", "fixture_chart", "pattern_chart"];

// Every choice string a chart exercise can present to the learner must be localized (the badge/label
// bug shipped `exerciseType.pattern_chart` and `divergence.accumulation` raw). Divergence labels live
// under `divergence.*`; all pattern-injector labels under `chartLabel.*`.
const DIVERGENCE_LABELS = ["none", "bullish_regular", "bearish_regular", "bullish_hidden", "bearish_hidden"];
const CHART_LABELS = [
  "genuine_breakout", "false_break", "no_break", "accumulation", "distribution", "none",
  "uptrend", "downtrend", "range", "overbought", "oversold", "neutral",
  "signal_cross", "zero_cross", "whipsaw",
  "retrace_382", "retrace_500", "retrace_618", "confirmed_breakout", "unconfirmed_breakout",
  "rising_oi", "falling_oi", "flat_oi",
  "cvd_bullish_divergence", "cvd_bearish_divergence", "cvd_confirms",
  "rejection_at_level", "overrun_at_level", "open_space", "indecision",
  "zone_respected", "zone_failed", "no_zone",
  "imbalance_unfilled", "imbalance_filled", "no_imbalance",
];

// Figure/chart ANNOTATION labels are also student-facing and must be localized, never rendered as the
// raw backend enum (the `bearish_e…` / `support` leak). Marker labels live under `chartMarker.*`
// (candle-reaction forms, the fakeout "test" marker, and the m08/m17/m06/m21/m24 figure markers); level
// titles under `level.*`. Keep in sync with the injectors' Annotation/Level labels. Pass-through keys
// (swing "1"/"2", Wyckoff phases "A"–"E", Fibonacci ratios, and the market-structure acronyms HH / HL /
// CHoCH, which read the same in both languages) are display-ready and intentionally absent.
const CHART_MARKERS = [
  "hammer", "shooting_star", "bullish_engulfing", "bearish_engulfing", "morning_star", "evening_star",
  "harami", "tweezers_bottom", "tweezers_top", "doji", "small_range", "test",
  "rejection", "sweep", "liquidation", "gap", "unfilled",
  // m30: the origin-zone sequence and the imbalance. "BOS" is deliberately absent — like HH / HL /
  // CHoCH it is an acronym that reads the same in both languages, so it passes through.
  "origin", "retest", "failed_break", "imbalance", "revisit", "traded_through",
];
// A level's title comes from its own LABEL first (falling back to its kind), so this list is of labels:
// the support/resistance pair where the two coincide, plus every named line the figure injectors draw —
// the `plan` lines of m21/m24 among them, whose whole purpose is to be read by name.
const LEVEL_LABELS = [
  "support", "resistance", "shelf", "confluence", "entry", "stop", "target", "trigger", "limit",
];
// A shaded ZONE is titled the same way — own label first, falling back to its kind — in its own
// namespace, because a band is a different render primitive from a horizontal line (m30).
const BAND_LABELS = ["origin", "imbalance"];
// The figure-only injectors' own labels (`uptrend_ladder`, `long_setup`, …) are deliberately NOT under
// `chartLabel.*`: that namespace is the set of choices an exercise can present, and no exercise may use
// those injectors — they show their own resolution. A backend test enforces it.

const catalogs = { en, es } as Record<string, Record<string, Record<string, string>>>;

describe("UI translations", () => {
  it("EN and ES expose the exact same key set", () => {
    expect(keyPaths(es).sort()).toEqual(keyPaths(en).sort());
  });

  // The reading-time string is the one place a number reaches the reader through interpolation alone:
  // a catalog entry without the `{{minutes}}` placeholder still renders, silently, as a time with no
  // time in it ("~ min"). Both catalogs are checked, in both directions.
  it.each(Object.keys(catalogs))("%s renders the reading-time estimate with its number", (lang) => {
    const course = catalogs[lang].course;
    for (const [key, placeholders] of [
      ["readingTime", ["{{minutes}}"]],
      ["readingTimeHours", ["{{hours}}"]],
      ["readingTimeHoursMinutes", ["{{hours}}", "{{minutes}}"]],
    ] as const) {
      expect(course?.[key], `course.${key} missing in ${lang}`).toBeTruthy();
      for (const placeholder of placeholders) expect(course[key]).toContain(placeholder);
    }
  });

  it.each(Object.keys(catalogs))("%s labels every exercise type", (lang) => {
    for (const type of EXERCISE_TYPES) {
      expect(catalogs[lang].exerciseType?.[type], `exerciseType.${type} missing in ${lang}`).toBeTruthy();
    }
  });

  it.each(Object.keys(catalogs))("%s localizes every chart choice label", (lang) => {
    for (const label of DIVERGENCE_LABELS) {
      expect(catalogs[lang].divergence?.[label], `divergence.${label} missing in ${lang}`).toBeTruthy();
    }
    for (const label of CHART_LABELS) {
      expect(catalogs[lang].chartLabel?.[label], `chartLabel.${label} missing in ${lang}`).toBeTruthy();
    }
  });

  it.each(Object.keys(catalogs))("%s localizes every figure/chart annotation label", (lang) => {
    for (const key of CHART_MARKERS) {
      expect(catalogs[lang].chartMarker?.[key], `chartMarker.${key} missing in ${lang}`).toBeTruthy();
    }
    for (const label of LEVEL_LABELS) {
      expect(catalogs[lang].level?.[label], `level.${label} missing in ${lang}`).toBeTruthy();
    }
    for (const label of BAND_LABELS) {
      expect(catalogs[lang].band?.[label], `band.${label} missing in ${lang}`).toBeTruthy();
    }
  });
});
