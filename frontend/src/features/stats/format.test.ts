import { describe, expect, it } from "vitest";
import type { ModuleStat } from "@/api/stats";
import { MIN_N_FOR_PERCENT, partitionModules, rate, rateShort } from "@/features/stats/format";

function moduleStat(over: Partial<ModuleStat>): ModuleStat {
  return {
    id: "m01",
    title: "Module",
    blockId: "block-a",
    lessonsTotal: 1,
    lessonsCompleted: 0,
    exercisesTotal: 4,
    exercisesPassed: 0,
    answered: 0,
    correct: 0,
    accuracy: null,
    firstAttemptAccuracy: null,
    firstSeen: 0,
    firstCorrect: 0,
    exercisesFailed: 0,
    toReview: [],
    ...over,
  };
}

describe("small-sample rendering", () => {
  it("shows a fraction below the threshold and a percentage at or above it", () => {
    expect(rate(2, 3)).toEqual({ kind: "fraction", num: 2, den: 3 });
    expect(rate(9, MIN_N_FOR_PERCENT - 1)).toMatchObject({ kind: "fraction" });
    expect(rate(9, MIN_N_FOR_PERCENT)).toEqual({ kind: "percent", percent: 90, den: 10 });
  });

  it("never renders a rate over an empty sample", () => {
    expect(rate(0, 0)).toEqual({ kind: "none" });
    expect(rateShort(0, 0)).toBe("—");
  });

  it("renders the brief's example as a fraction, not 67%", () => {
    expect(rateShort(2, 3)).toBe("2/3");
    expect(rateShort(15, 18)).toBe("83%");
  });

  it("keeps 0 and 1 honest at n=1 — '0/1', never '0%'", () => {
    expect(rateShort(0, 1)).toBe("0/1");
    expect(rateShort(1, 1)).toBe("1/1");
  });
});

describe("untouched modules", () => {
  it("folds only modules with no marked lesson and no answered attempt", () => {
    const modules = [
      moduleStat({ id: "m01", answered: 14 }),
      moduleStat({ id: "m02" }),
      moduleStat({ id: "m03", lessonsCompleted: 1 }),
      moduleStat({ id: "m04" }),
    ];
    const { touched, untouched } = partitionModules(modules);
    expect(touched.map((m) => m.id)).toEqual(["m01", "m03"]);
    expect(untouched.map((m) => m.id)).toEqual(["m02", "m04"]);
  });

  it("treats an opened-but-never-answered module as untouched, like every other metric here", () => {
    // `answered` counts answered attempts only, so abandoning an exercise leaves no trace.
    expect(partitionModules([moduleStat({ id: "m05" })]).untouched).toHaveLength(1);
  });
});
