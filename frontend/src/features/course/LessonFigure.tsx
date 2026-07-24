import { type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getFigure, type FigurePanel } from "@/api/course";
import { CandleAnatomy } from "@/components/charts/CandleAnatomy";
import { CandleChart, type SwingMarker } from "@/components/charts/CandleChart";
import { Spinner } from "@/components/ui/primitives";

// Hand-drawn SVG figures, keyed by the spec's `svg` name.
const SVG_FIGURES: Record<string, () => ReactNode> = {
  "candle-anatomy": () => <CandleAnatomy />,
};

function toMarkers(annotations: FigurePanel["annotations"]): SwingMarker[] {
  return annotations.map((a) => ({
    index: a.index,
    label: a.label,
    kind: a.kind === "high" ? "high" : a.kind === "low" ? "low" : "neutral",
  }));
}

/** A didactic figure embedded in a lesson via `::figure{id=...}`. Deterministic (frozen seed) and
 * non-interactive; shows the pattern's resolution. Responsive: fills the container width, and
 * multi-panel comparisons stack vertically on phones (single column) and go side-by-side from `sm`. */
export function LessonFigure({ id }: { id: string }) {
  const { i18n } = useTranslation();
  const { data } = useQuery({ queryKey: ["figure", id, i18n.resolvedLanguage], queryFn: () => getFigure(id) });

  if (!data) {
    return (
      <div className="my-6 flex justify-center py-8 text-gray-400">
        <Spinner />
      </div>
    );
  }

  const svg = data.kind === "svg" && data.svg ? SVG_FIGURES[data.svg] : undefined;

  return (
    <figure className="my-6">
      {svg && <div className="my-2">{svg()}</div>}
      {data.kind === "chart" && data.panels && (
        <div className={data.panels.length > 1 ? "grid grid-cols-1 gap-3 sm:grid-cols-2" : ""}>
          {data.panels.map((p, i) => (
            <CandleChart
              key={i}
              series={p.series}
              rsi={p.rsi}
              macd={p.macd}
              oi={p.oi}
              overlays={p.overlays}
              levels={p.levels}
              indicator={p.indicator}
              markers={toMarkers(p.annotations)}
              height={300}
              rightOffset={10}
            />
          ))}
        </div>
      )}
      <figcaption className="mt-2 text-sm text-gray-500 dark:text-gray-400">{data.caption}</figcaption>
    </figure>
  );
}
