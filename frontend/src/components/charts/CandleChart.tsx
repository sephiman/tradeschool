import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  TickMarkType,
  type IChartApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useTheme } from "@/lib/theme";

/** Always European: day/month for day ticks, localized month name for month ticks (never MM/DD). */
function formatTick(time: Time, tickMarkType: TickMarkType, locale: string): string {
  const secs = typeof time === "number" ? time : 0;
  const d = new Date(secs * 1000);
  if (Number.isNaN(d.getTime())) return "";
  if (tickMarkType === TickMarkType.Year) return String(d.getUTCFullYear());
  if (tickMarkType === TickMarkType.Month) {
    return d.toLocaleDateString(locale || "en-GB", { month: "short", timeZone: "UTC" });
  }
  const day = String(d.getUTCDate()).padStart(2, "0");
  const month = String(d.getUTCMonth() + 1).padStart(2, "0");
  return `${day}/${month}`;
}

export interface ChartSeries {
  time: number[];
  open: number[];
  high: number[];
  low: number[];
  close: number[];
  volume: number[];
}

export interface MacdData {
  line: number[];
  signal: number[];
  hist: number[];
}

export interface SwingMarker {
  index: number;
  label: string;
  kind: "high" | "low" | "neutral";
}

export interface PriceLevel {
  price: number;
  label: string;
  kind: string;
}

const palette = (dark: boolean) => ({
  background: "transparent",
  text: dark ? "#9ca3af" : "#6b7280",
  grid: dark ? "#1f2937" : "#eef2f7",
  border: dark ? "#374151" : "#e5e7eb",
  up: "#16a34a",
  down: "#dc2626",
  upVol: dark ? "rgba(22,163,74,0.4)" : "rgba(22,163,74,0.3)",
  downVol: dark ? "rgba(220,38,38,0.4)" : "rgba(220,38,38,0.3)",
  indicator: "#6366f1",
  signal: "#f59e0b",
  oi: "#0891b2",
  marker: dark ? "#e5e7eb" : "#111827",
  // Distinct thin-line colors for price-pane overlays (e.g. moving averages), cycled by order.
  overlays: dark ? ["#60a5fa", "#c084fc", "#22d3ee", "#facc15"] : ["#2563eb", "#9333ea", "#0891b2", "#ca8a04"],
});

/** Horizontal-level color keyed by semantic kind (support/resistance/fib/…). */
function levelColor(c: ReturnType<typeof palette>, kind: string): string {
  if (kind === "support") return c.up;
  if (kind === "resistance") return c.down;
  if (kind === "fib") return c.signal;
  return c.text;
}

export function CandleChart({
  series,
  rsi,
  macd,
  oi,
  indicator,
  markers = [],
  overlays,
  levels,
  height = 420,
}: {
  series: ChartSeries;
  rsi?: number[];
  macd?: MacdData;
  oi?: number[];
  indicator: "rsi" | "macd" | "oi" | "none";
  markers?: SwingMarker[];
  overlays?: Record<string, number[]>;
  levels?: PriceLevel[];
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { resolvedTheme } = useTheme();
  const { i18n } = useTranslation();
  const locale = i18n.resolvedLanguage === "es" ? "es-ES" : "en-GB";

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const c = palette(resolvedTheme === "dark");
    const t = (i: number) => series.time[i] as UTCTimestamp;

    const chart: IChartApi = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: c.background },
        textColor: c.text,
        attributionLogo: false,
        // Right price scale is auto-sized so the widest label (price, volume, RSI) never overlaps.
      },
      // Force European date rendering (day-first, or localized month names) everywhere.
      localization: { locale, dateFormat: "dd/MM/yyyy" },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.border, minimumWidth: 64 },
      timeScale: {
        borderColor: c.border,
        timeVisible: false,
        secondsVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
        // Daily bars; month-boundary ticks show the localized month name (unambiguous — never
        // mistakable for MM/DD), day ticks show DD/MM. No truncated edge labels.
        tickMarkFormatter: formatTick,
      },
      crosshair: { mode: CrosshairMode.Normal },
    });

    // Pane 0: candles. Pane 1: volume. Pane 2: oscillator. Each pane has its own price scale,
    // so labels never collide across panes (round-2 fix).
    const candles = chart.addSeries(
      CandlestickSeries,
      { upColor: c.up, downColor: c.down, borderVisible: false, wickUpColor: c.up, wickDownColor: c.down },
      0,
    );
    candles.setData(
      series.close.map((_, i) => ({
        time: t(i),
        open: series.open[i],
        high: series.high[i],
        low: series.low[i],
        close: series.close[i],
      })),
    );

    // Price-pane overlays (e.g. ema50/ema200): thin lines, cycled distinct colors, small title.
    // Values align 1:1 with the visible series; non-finite entries render as gaps (whitespace).
    if (overlays) {
      Object.keys(overlays).forEach((name, idx) => {
        const values = overlays[name];
        const line = chart.addSeries(
          LineSeries,
          {
            color: c.overlays[idx % c.overlays.length],
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: true,
            title: name,
          },
          0,
        );
        line.setData(values.map((v, i) => (Number.isFinite(v) ? { time: t(i), value: v } : { time: t(i) })));
      });
    }

    // Horizontal reference levels on the price pane: dashed price lines with an axis label.
    if (levels) {
      for (const lvl of levels) {
        candles.createPriceLine({
          price: lvl.price,
          color: levelColor(c, lvl.kind),
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: lvl.label,
        });
      }
    }

    const volume = chart.addSeries(
      HistogramSeries,
      { priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false },
      1,
    );
    volume.setData(
      series.volume.map((v, i) => ({ time: t(i), value: v, color: series.close[i] >= series.open[i] ? c.upVol : c.downVol })),
    );

    if (indicator === "macd" && macd) {
      chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, 2).setData(
        macd.hist.map((v, i) => ({ time: t(i), value: v, color: v >= 0 ? c.upVol : c.downVol })),
      );
      chart.addSeries(LineSeries, { color: c.indicator, lineWidth: 2, priceLineVisible: false }, 2).setData(
        macd.line.map((v, i) => ({ time: t(i), value: v })),
      );
      chart.addSeries(LineSeries, { color: c.signal, lineWidth: 1, priceLineVisible: false }, 2).setData(
        macd.signal.map((v, i) => ({ time: t(i), value: v })),
      );
    } else if (indicator === "rsi" && rsi) {
      const line = chart.addSeries(
        LineSeries,
        {
          color: c.indicator,
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: false,
          autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }),
        },
        2,
      );
      line.setData(rsi.map((v, i) => ({ time: t(i), value: v })));
      // Guide lines only; no axis labels (the pane's own scale already shows the values).
      for (const level of [30, 70]) {
        line.createPriceLine({ price: level, color: c.border, lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: "" });
      }
    } else if (indicator === "oi" && oi) {
      // Open interest: a single auto-scaled line (no fixed range, no 30/70 guides), titled "OI".
      const line = chart.addSeries(
        LineSeries,
        { color: c.oi, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, title: "OI" },
        2,
      );
      line.setData(oi.map((v, i) => ({ time: t(i), value: v })));
    }

    if (markers.length > 0) {
      const sm: SeriesMarker<UTCTimestamp>[] = markers.map((m): SeriesMarker<UTCTimestamp> => {
        if (m.kind === "high") {
          return { time: t(m.index), position: "aboveBar", color: c.marker, shape: "arrowDown", text: m.label };
        }
        if (m.kind === "low") {
          return { time: t(m.index), position: "belowBar", color: c.marker, shape: "arrowUp", text: m.label };
        }
        return { time: t(m.index), position: "inBar", color: c.marker, shape: "circle", text: m.label };
      });
      createSeriesMarkers(candles, sm);
    }

    // Price gets the lion's share; volume a thin strip; the oscillator (when present) a readable band.
    const panes = chart.panes();
    if (panes.length >= 3) {
      panes[0].setStretchFactor(6);
      panes[1].setStretchFactor(1.4);
      panes[2].setStretchFactor(2.6);
    } else if (panes.length >= 2) {
      panes[0].setStretchFactor(6);
      panes[1].setStretchFactor(1.4);
    }
    chart.timeScale().fitContent();

    return () => chart.remove();
  }, [series, rsi, macd, oi, indicator, markers, overlays, levels, resolvedTheme, locale]);

  return <div ref={containerRef} style={{ height }} className="w-full" />;
}
