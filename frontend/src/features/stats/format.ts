import type { ModuleStat } from "@/api/stats";

/**
 * Below this many observations a rate is shown as a fraction, never as a percentage.
 *
 * With `n` observations, one observation moves a percentage by `100/n` points. Below ten that is
 * more than ten points per data point, so a two- or three-digit percentage claims a resolution the
 * data does not have — "67%" over three attempts really means "somewhere between 1/3 and 3/3". At
 * ten each observation is worth exactly ten points and the percentage is honest to its own
 * granularity. Readability agrees on the same cut: `7/10` is scannable, `37/52` is not.
 *
 * This governs *rate estimates* only (accuracy, first-attempt accuracy). It does not govern counts
 * over a known total — lessons marked, exercises passed — which are censuses, not samples: 5/35 is
 * exactly 14%, not an estimate of anything.
 */
export const MIN_N_FOR_PERCENT = 10;

export type Rate =
  | { kind: "none" }
  | { kind: "fraction"; num: number; den: number }
  | { kind: "percent"; percent: number; den: number };

/** Classify a rate by how much its own sample can support. */
export function rate(num: number, den: number): Rate {
  if (den <= 0) return { kind: "none" };
  if (den < MIN_N_FOR_PERCENT) return { kind: "fraction", num, den };
  return { kind: "percent", percent: Math.round((num / den) * 100), den };
}

/** Compact form for a table cell, where the column header carries the unit. */
export function rateShort(num: number, den: number): string {
  const r = rate(num, den);
  if (r.kind === "none") return "—";
  return r.kind === "fraction" ? `${r.num}/${r.den}` : `${r.percent}%`;
}

/**
 * A module is untouched when the learner has neither marked a lesson in it nor answered any of its
 * exercises. Opened-and-abandoned attempts do not count, consistently with every other number on
 * this page — only answered attempts ever do.
 */
export function isUntouched(m: Pick<ModuleStat, "lessonsCompleted" | "answered">): boolean {
  return m.lessonsCompleted === 0 && m.answered === 0;
}

/** Course order is preserved inside both halves; the caller renders `untouched` behind a toggle. */
export function partitionModules(modules: ModuleStat[]): {
  touched: ModuleStat[];
  untouched: ModuleStat[];
} {
  return {
    touched: modules.filter((m) => !isUntouched(m)),
    untouched: modules.filter(isUntouched),
  };
}
