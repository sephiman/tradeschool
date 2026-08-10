import { type ReactNode } from "react";
import { CandleChart, type ChartSeries } from "@/components/charts/CandleChart";

/**
 * A chart with its multi-timeframe companion stacked above or below it (m23-l2).
 *
 * The companion is the SAME price aggregated to a coarser frame, so it carries no oscillator pane, no
 * levels and no markers — there is nothing on it that is not already on the panel it came from.
 *
 * The two panels are drawn at the SAME height, deliberately. One of the exercises asks which of them
 * contains the other, and a smaller "context" panel would answer that off the layout rather than off
 * the candles. They are also left unlabelled for the same reason.
 */
export interface TimeframeContextView {
  series: ChartSeries;
  position: "above" | "below";
}

/** Height each panel gets when a chart is paired, so the pair costs about what one tall chart did. */
export const PAIRED_HEIGHT = 230;

export function FramedChart({
  context,
  children,
}: {
  context: TimeframeContextView | undefined;
  children: ReactNode;
}) {
  if (!context) return <>{children}</>;
  const companion = (
    <CandleChart series={context.series} indicator="none" height={PAIRED_HEIGHT} rightOffset={8} />
  );
  return (
    <div className="space-y-1">
      {context.position === "above" && companion}
      {children}
      {context.position === "below" && companion}
    </div>
  );
}
