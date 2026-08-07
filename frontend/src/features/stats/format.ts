import type { ModuleStat } from "@/api/stats";

/**
 * Below this many observations a rate is shown as a fraction, never as a percentage: one observation
 * moves a percentage by `100/n` points, so "67%" over three attempts claims a resolution it lacks.
 *
 * Governs rate ESTIMATES only. Counts over a known total are censuses — 5/35 is exactly 14%.
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

/** Untouched: no lesson marked and no exercise answered. Abandoned attempts never count. */
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
