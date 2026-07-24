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
  "retrace_382", "retrace_500", "retrace_618", "confirmed_breakout", "unconfirmed_breakout",
  "rising_oi", "falling_oi", "flat_oi",
];

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
});
