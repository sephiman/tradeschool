import type { PriceBand, SwingMarker } from "@/components/charts/CandleChart";

/** Build the two swing markers from a graded chart answer ({divergence, swing1, swing2}). */
export function divergenceMarkers(groundTruth: unknown): SwingMarker[] {
  const g = groundTruth as { divergence?: string; swing1?: number | null; swing2?: number | null };
  if (!g?.divergence || g.divergence === "none") return [];
  const kind: "high" | "low" = g.divergence.startsWith("bearish") ? "high" : "low";
  const out: SwingMarker[] = [];
  if (typeof g.swing1 === "number") out.push({ index: g.swing1, label: "1", kind });
  if (typeof g.swing2 === "number") out.push({ index: g.swing2, label: "2", kind });
  return out;
}

interface PatternAnnotation {
  index: number;
  kind: string;
  label: string;
}

/** Map a pattern_chart ground truth to CandleChart bands (m30's origin zone / imbalance).
 *
 * Bands live in the GRADED answer and nowhere else: the pre-answer payload has no `bands` key at all,
 * because shading the zone on the question would be handing over the answer. So this is the only path by
 * which an exercise chart ever draws one — after answering, on the same chart, which is where the zone is
 * finally worth seeing. Absent for every label that plants no zone (`no_zone`, `no_imbalance`). */
export function patternBands(groundTruth: unknown): PriceBand[] {
  const g = groundTruth as { bands?: PriceBand[] };
  if (!Array.isArray(g?.bands)) return [];
  return g.bands.filter((b) => b && typeof b.low === "number" && typeof b.high === "number");
}

/** Map a pattern_chart ground truth ({label, annotations, levels}) to CandleChart markers.
 * annotations[].index is in visible-window coordinates; kind "high"/"low" arrow above/below,
 * anything else renders as a neutral marker. */
export function patternMarkers(groundTruth: unknown): SwingMarker[] {
  const g = groundTruth as { annotations?: PatternAnnotation[] };
  if (!Array.isArray(g?.annotations)) return [];
  return g.annotations
    .filter((a) => a && typeof a.index === "number")
    .map((a) => ({
      index: a.index,
      label: typeof a.label === "string" ? a.label : "",
      kind: a.kind === "high" ? "high" : a.kind === "low" ? "low" : "neutral",
    }));
}
