import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  BaselineSeries,
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
import { useResolvedTheme, type ResolvedTheme } from "@/lib/theme";

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

/** A shaded price ZONE — m30's origin zone and imbalance. Two prices, because that is what it is. */
export interface PriceBand {
  low: number;
  high: number;
  label: string;
  kind: string;
}

/**
 * The drawing palette. OLED is the dark palette with a delta applied on top, never a third branch:
 * light and dark come out of the same expression they always did, so the two shipped themes cannot
 * drift while the third is tuned.
 *
 * What the delta touches is only what pure black actually changes. Every SIGNAL colour is kept —
 * candle up/down, the indicator/signal pair, OI, CVD, the overlay cycle, and the neutral the markers,
 * `plan` lines and shaded bands share — because saturated ink gains contrast on #000 rather than
 * losing it, and re-tinting it per theme would mean m21's stop line is a different colour depending
 * on the reader's preference. What does change is the CHROME: the grid and axis borders carry a blue
 * cast (gray-800/700) that reads as a colour rather than a rule once the background is neutral black,
 * and the crosshair, which is a library default in light and dark, is too dim against it.
 */
const OLED_INK = {
  background: "#000000",
  // Neutral, and at the same visibility the blue-tinted grid had against gray-950 — a grid that gains
  // contrast with the background is a grid that competes with the candles. Shared with SharedLedger's
  // `--color-chart-grid`; the axis border is its `border-strong`, since here that line is also the
  // RSI/MACD/CVD guide and has to stay readable as a rule rather than as decoration.
  grid: "#262626",
  border: "#454545",
  // Explicit ONLY here. Light and dark leave the library's crosshair defaults alone (which is why the
  // chart options below spread this in rather than passing undefined), so neither can shift.
  crosshair: "#5a5a5a",
} as const;

export const palette = (theme: ResolvedTheme) => {
  const dark = theme !== "light";
  const base = {
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
    cvd: "#0d9488",
    marker: dark ? "#e5e7eb" : "#111827",
    // A shaded zone follows the `plan` colour precedent: the SAME high-contrast neutral the markers use,
    // deliberately not red/green. An origin zone can be demand or supply and an imbalance can point either
    // way, so a green band would import exactly the "bullish order block" semantics m30-l1 refuses. The
    // fill is that neutral at low alpha — enough to read as an area, not enough to tint the candles.
    band: dark ? "#e5e7eb" : "#111827",
    bandFill: dark ? "rgba(229,231,235,0.10)" : "rgba(17,24,39,0.08)",
    // Distinct thin-line colors for price-pane overlays (e.g. moving averages), cycled by order.
    overlays: dark ? ["#60a5fa", "#c084fc", "#22d3ee", "#facc15"] : ["#2563eb", "#9333ea", "#0891b2", "#ca8a04"],
    // No crosshair override: the library's own default, in both shipped themes.
    crosshair: undefined as string | undefined,
  };
  return theme === "oled" ? { ...base, ...OLED_INK } : base;
};

/** Horizontal-level color keyed by semantic kind (support/resistance/fib/plan/…). */
export function levelColor(c: ReturnType<typeof palette>, kind: string): string {
  if (kind === "support") return c.up;
  if (kind === "resistance") return c.down;
  if (kind === "fib") return c.signal;
  // A `plan` line — entry, stop, target, a stop-limit's trigger and limit — is a price the TRADER chose,
  // not one the market has respected, so it reads as the annotation layer: the same high-contrast neutral
  // the markers use. Deliberately not red/green, which would make a stop line look like a resistance.
  if (kind === "plan") return c.marker;
  return c.text;
}

export function CandleChart({
  series,
  rsi,
  macd,
  oi,
  cvd,
  indicator,
  markers = [],
  overlays,
  levels,
  bands,
  height = 420,
  rightOffset = 4,
  theme,
  onReady,
}: {
  series: ChartSeries;
  rsi?: number[];
  macd?: MacdData;
  oi?: number[];
  cvd?: number[];
  indicator: "rsi" | "macd" | "oi" | "cvd" | "none";
  markers?: SwingMarker[];
  overlays?: Record<string, number[]>;
  levels?: PriceLevel[];
  // Shaded zones. Ground truth on the backend, so an exercise chart only ever receives these AFTER
  // grading — drawing the zone on the question would be the answer (m30).
  bands?: PriceBand[];
  height?: number;
  // Empty bars of margin on the right so a marker planted near the last candle isn't clipped by the
  // boundary. Figures (patterns at the very edge) pass more; exercise charts keep the small default.
  rightOffset?: number;
  // Pin the palette instead of following the UI theme. Only the PDF export passes it: print is light.
  theme?: ResolvedTheme;
  // The created chart, for the PDF export's screenshot. Like `series` and `markers` it is an effect
  // dependency, so an unstable identity rebuilds the chart — fine for a capture, not for a live view.
  onReady?: (chart: IChartApi) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const resolvedTheme = useResolvedTheme(theme);
  const { i18n, t } = useTranslation();
  const locale = i18n.resolvedLanguage === "es" ? "es-ES" : "en-GB";
  // Annotation text is student-facing: marker labels and level titles come from the i18n catalog
  // (localized display names), never the raw backend enum. Unknown keys (swing "1"/"2", Wyckoff
  // phases "A"–"E") fall through to the raw string, which is already display-ready.
  const markerText = (raw: string): string => (raw ? t(`chartMarker.${raw}`, { defaultValue: raw }) : "");
  // A level's title comes from its OWN label first, falling back to its kind, then the raw string.
  // Keying on `kind` alone made every level of a kind render the same title — three Fibonacci lines
  // would all read alike, and a two-bound range could not be told apart. For the support/resistance
  // pair label and kind coincide, so this is identical for them.
  const levelText = (lvl: PriceLevel): string =>
    t(`level.${lvl.label}`, { defaultValue: t(`level.${lvl.kind}`, { defaultValue: lvl.label }) });
  // Same own-label-first rule as levels, in the `band.*` namespace.
  const bandText = (band: PriceBand): string =>
    t(`band.${band.label}`, { defaultValue: t(`band.${band.kind}`, { defaultValue: band.label }) });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const c = palette(resolvedTheme);
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
        // Right edge is NOT fixed so the right-margin (rightOffset) below is honored — otherwise a
        // marker on the last candle gets clipped by the boundary.
        fixRightEdge: false,
        // Daily bars; month-boundary ticks show the localized month name (unambiguous — never
        // mistakable for MM/DD), day ticks show DD/MM. No truncated edge labels.
        tickMarkFormatter: formatTick,
      },
      // The colours are spread in only when the palette names them, so light and dark keep the
      // library's own crosshair exactly as before rather than being handed an explicit `undefined`.
      crosshair: {
        mode: CrosshairMode.Normal,
        ...(c.crosshair
          ? { vertLine: { color: c.crosshair }, horzLine: { color: c.crosshair } }
          : {}),
      },
    });

    // Shaded price zones (m30's origin zone / imbalance), added FIRST so the candles draw on top of the
    // tint rather than under it — lightweight-charts z-orders series by creation order.
    //
    // A band is a BaselineSeries pinned at its lower edge with every bar valued at its upper edge, which
    // fills the region between the two, plus one flat line for the lower edge (the baseline itself is not
    // drawn). Deliberately NOT two `createPriceLine` calls: the price-pane line count is an invariant
    // (`levels.test.tsx` — exactly one line per planted level, no phantom line a learner reads as a
    // mystery level), and a zone rendered as two dashed lines would both break that count and look like
    // two independent levels. `topFillColor1 === topFillColor2` keeps the fill flat: a gradient would
    // imply "stronger near the top", which is not a claim a zone makes.
    if (bands) {
      for (const band of bands) {
        const upper = chart.addSeries(
          BaselineSeries,
          {
            baseValue: { type: "price", price: band.low },
            topFillColor1: c.bandFill,
            topFillColor2: c.bandFill,
            bottomFillColor1: "rgba(0,0,0,0)",
            bottomFillColor2: "rgba(0,0,0,0)",
            topLineColor: c.band,
            bottomLineColor: c.band,
            lineWidth: 1,
            priceLineVisible: false,
            crosshairMarkerVisible: false,
            lastValueVisible: true,
            title: bandText(band),
          },
          0,
        );
        upper.setData(series.close.map((_, i) => ({ time: t(i), value: band.high })));
        const lower = chart.addSeries(
          LineSeries,
          {
            color: c.band,
            lineWidth: 1,
            priceLineVisible: false,
            crosshairMarkerVisible: false,
            lastValueVisible: false, // the zone is named once, on its upper edge
          },
          0,
        );
        lower.setData(series.close.map((_, i) => ({ time: t(i), value: band.low })));
      }
    }

    // Pane 0: candles. Pane 1: volume. Pane 2: oscillator. Each pane has its own price scale,
    // so labels never collide across panes (round-2 fix).
    const candles = chart.addSeries(
      CandlestickSeries,
      {
        upColor: c.up,
        downColor: c.down,
        borderVisible: false,
        wickUpColor: c.up,
        wickDownColor: c.down,
        // The library's default last-value price line is a DASHED horizontal line at the last close
        // with a price on the axis and no title — indistinguishable from a drawn support/resistance.
        // On a chart whose whole question is "where is the level?" that phantom line is read as a
        // second, unlabeled level (it is why m08 exercises appeared to draw two lines). The only
        // horizontal lines on the price pane must be the ones an injector planted, so it is off.
        priceLineVisible: false,
      },
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
          title: levelText(lvl),
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
      const macdLine = chart.addSeries(LineSeries, { color: c.indicator, lineWidth: 2, priceLineVisible: false }, 2);
      macdLine.setData(macd.line.map((v, i) => ({ time: t(i), value: v })));
      chart.addSeries(LineSeries, { color: c.signal, lineWidth: 1, priceLineVisible: false }, 2).setData(
        macd.signal.map((v, i) => ({ time: t(i), value: v })),
      );
      // Zero is the line the pane is read against: above it the fast EMA leads the slow one, below it
      // trails. A cross OF it is a regime change, not the momentum wobble a signal-line cross is (m11),
      // so it needs to be visible — a guide line, like the RSI's 30/70, with no axis label.
      macdLine.createPriceLine({ price: 0, color: c.border, lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: "" });
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
    } else if (indicator === "cvd" && cvd) {
      // Cumulative volume delta: an auto-scaled line like OI, but read against ZERO — the series is
      // net taker flow accumulated since the window opened, so which side of zero it sits on (and
      // where it turns) is the reading. Hence the guide line OI does not need.
      const line = chart.addSeries(
        LineSeries,
        { color: c.cvd, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, title: "CVD" },
        2,
      );
      line.setData(cvd.map((v, i) => ({ time: t(i), value: v })));
      line.createPriceLine({ price: 0, color: c.border, lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: "" });
    }

    if (markers.length > 0) {
      const sm: SeriesMarker<UTCTimestamp>[] = markers.map((m): SeriesMarker<UTCTimestamp> => {
        const text = markerText(m.label);
        if (m.kind === "high") {
          return { time: t(m.index), position: "aboveBar", color: c.marker, shape: "arrowDown", text };
        }
        if (m.kind === "low") {
          return { time: t(m.index), position: "belowBar", color: c.marker, shape: "arrowUp", text };
        }
        return { time: t(m.index), position: "inBar", color: c.marker, shape: "circle", text };
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
    // Show every candle plus `rightOffset` empty bars of margin on the right (room for edge markers).
    chart.timeScale().setVisibleLogicalRange({ from: -0.5, to: series.close.length - 0.5 + rightOffset });

    onReady?.(chart);

    return () => chart.remove();
  }, [series, rsi, macd, oi, cvd, indicator, markers, overlays, levels, bands, resolvedTheme, locale, rightOffset, t, onReady]);

  return <div ref={containerRef} style={{ height }} className="w-full" />;
}
