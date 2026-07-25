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
];

// Figure/chart ANNOTATION labels are also student-facing and must be localized, never rendered as the
// raw backend enum (the `bearish_e…` / `support` leak). Marker labels live under `chartMarker.*`
// (candle-reaction forms + the fakeout "test" marker); level titles under `level.*`. Keep in sync
// with the injectors' Annotation/Level labels. Pass-through keys (swing "1"/"2", Wyckoff phases
// "A"–"E", Fibonacci ratios) are display-ready and intentionally absent.
const CHART_MARKERS = [
  "hammer", "shooting_star", "bullish_engulfing", "bearish_engulfing", "morning_star", "evening_star",
  "harami", "tweezers_bottom", "tweezers_top", "doji", "small_range", "test",
];
const LEVEL_KINDS = ["support", "resistance"];

const catalogs = { en, es } as Record<string, Record<string, Record<string, string>>>;

describe("UI translations", () => {
  it("EN and ES expose the exact same key set", () => {
    expect(keyPaths(es).sort()).toEqual(keyPaths(en).sort());
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
    for (const kind of LEVEL_KINDS) {
      expect(catalogs[lang].level?.[kind], `level.${kind} missing in ${lang}`).toBeTruthy();
    }
  });
});
