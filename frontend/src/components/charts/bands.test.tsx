import { act, type ReactElement } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The shaded-zone primitive (m30's origin zone and imbalance).
 *
 * A band is the one annotation in this course that is *withheld* rather than drawn: the exercise asks the
 * learner to find the zone, so shading it on the question would be handing over the answer. The backend
 * side of that is enforced in `test_chart_bands.py`; what this file locks is everything the renderer owes:
 *
 * 1. a band renders as a FILL between its two planted prices, not as two more dashed price lines — the
 *    price-pane line count is an invariant (`levels.test.tsx`), and two dashed lines would read as two
 *    independent mystery levels, which is the exact defect that suite exists to prevent;
 * 2. it is drawn UNDER the candles, or the tint sits on top of the price action it describes;
 * 3. its colour is the neutral annotation colour, never the up/down pair — an origin zone can be demand
 *    or supply, so a green band would assert a direction the lesson explicitly refuses to;
 * 4. it carries its own localized name, so two bands never collapse into one title.
 *
 * The library renders to canvas, so as in `levels.test.tsx` it is mocked: what matters is the options the
 * component asks for, which is what a mock can assert and a jsdom render cannot.
 */

const addSeries = vi.fn();
const createPriceLine = vi.fn();
const setData = vi.fn();

function seriesHandle() {
  return { setData, createPriceLine, applyOptions: vi.fn() };
}

vi.mock("lightweight-charts", () => ({
  BaselineSeries: "baseline",
  CandlestickSeries: "candles",
  HistogramSeries: "histogram",
  LineSeries: "line",
  ColorType: { Solid: "solid" },
  CrosshairMode: { Normal: 0 },
  TickMarkType: { Year: 0, Month: 1, DayOfMonth: 2 },
  createSeriesMarkers: vi.fn(),
  createChart: () => ({
    addSeries: (...args: unknown[]) => {
      addSeries(...args);
      return seriesHandle();
    },
    panes: () => [{ setStretchFactor: vi.fn() }, { setStretchFactor: vi.fn() }],
    timeScale: () => ({ setVisibleLogicalRange: vi.fn() }),
    remove: vi.fn(),
  }),
}));

vi.mock("@/lib/theme", () => ({ useTheme: () => ({ resolvedTheme: "dark" }) }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    i18n: { resolvedLanguage: "es" },
    t: (key: string, opts?: { defaultValue?: string }) =>
      key === "band.origin"
        ? "Zona de origen"
        : key === "band.imbalance"
          ? "Desequilibrio"
          : (opts?.defaultValue ?? key),
  }),
}));

const { CandleChart } = await import("./CandleChart");

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function mount(node: ReactElement): void {
  const host = document.createElement("div");
  document.body.appendChild(host);
  act(() => {
    createRoot(host).render(node);
  });
}

const series = {
  time: [1, 2, 3, 4],
  open: [10, 11, 12, 13],
  high: [11, 12, 13, 14],
  low: [9, 10, 11, 12],
  close: [11, 12, 13, 13.5],
  volume: [1, 1, 1, 1],
};

const originBand = { low: 10.5, high: 11.5, label: "origin", kind: "origin" };

type BaselineOptions = {
  baseValue?: { type: string; price: number };
  topFillColor1?: string;
  topFillColor2?: string;
  topLineColor?: string;
  title?: string;
  priceLineVisible?: boolean;
};

function baselineCalls(): BaselineOptions[] {
  return addSeries.mock.calls.filter((c) => c[0] === "baseline").map((c) => c[1] as BaselineOptions);
}

describe("shaded price bands", () => {
  beforeEach(() => {
    addSeries.mockClear();
    createPriceLine.mockClear();
    setData.mockClear();
  });

  it("draws nothing extra when no band is passed", () => {
    mount(<CandleChart series={series} indicator="none" />);
    expect(baselineCalls()).toHaveLength(0);
  });

  it("fills the region between the band's two planted prices", () => {
    mount(<CandleChart series={series} indicator="none" bands={[originBand]} />);
    const [band] = baselineCalls();
    expect(band, "a band must render a baseline series").toBeTruthy();
    // Pinned at the LOW, valued at the HIGH: the fill is exactly the zone and nothing either side of it.
    expect(band.baseValue).toEqual({ type: "price", price: 10.5 });
    // The band is created before every other series (see the z-order test below), so its two edges are
    // the first two setData calls: the fill's upper edge, then the flat line closing it at the bottom.
    const upper = setData.mock.calls[0][0] as { value: number }[];
    const lower = setData.mock.calls[1][0] as { value: number }[];
    expect(new Set(upper.map((d) => d.value))).toEqual(new Set([11.5]));
    expect(new Set(lower.map((d) => d.value))).toEqual(new Set([10.5]));
    expect(upper).toHaveLength(series.close.length);
    // A flat tint, not a gradient: a gradient would imply the zone means more near one edge.
    expect(band.topFillColor1).toBe(band.topFillColor2);
  });

  it("never renders a band as extra price lines on the price pane", () => {
    mount(
      <CandleChart
        series={series}
        indicator="none"
        levels={[{ price: 13.9, label: "resistance", kind: "resistance" }]}
        bands={[originBand]}
      />,
    );
    // Exactly the ONE planted level. A zone drawn as two dashed lines would read as two more levels —
    // and would silently break the invariant `levels.test.tsx` locks.
    expect(createPriceLine).toHaveBeenCalledTimes(1);
    expect(createPriceLine.mock.calls[0][0]).toMatchObject({ price: 13.9 });
  });

  it("draws the band under the candles, so the tint never sits on top of the price action", () => {
    mount(<CandleChart series={series} indicator="none" bands={[originBand]} />);
    const kinds = addSeries.mock.calls.map((c) => c[0]);
    expect(kinds.indexOf("baseline")).toBeGreaterThanOrEqual(0);
    expect(kinds.indexOf("baseline")).toBeLessThan(kinds.indexOf("candles"));
  });

  it("uses the neutral annotation colour, not the up/down pair", () => {
    mount(<CandleChart series={series} indicator="none" bands={[originBand]} />);
    const [band] = baselineCalls();
    // The candles' own colours are the semantic pair; a zone must share neither.
    const candles = addSeries.mock.calls.find((c) => c[0] === "candles")?.[1] as {
      upColor: string;
      downColor: string;
    };
    expect(band.topLineColor).not.toBe(candles.upColor);
    expect(band.topLineColor).not.toBe(candles.downColor);
    expect(band.priceLineVisible).toBe(false);
  });

  it("titles each band from its own label, so two bands never collapse into one name", () => {
    mount(
      <CandleChart
        series={series}
        indicator="none"
        bands={[originBand, { low: 12.0, high: 12.8, label: "imbalance", kind: "imbalance" }]}
      />,
    );
    expect(baselineCalls().map((b) => b.title)).toEqual(["Zona de origen", "Desequilibrio"]);
  });
});
