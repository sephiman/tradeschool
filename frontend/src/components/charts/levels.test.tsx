import { act, type ReactElement } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The price pane must draw EXACTLY the horizontal lines the backend planted — no more.
 *
 * lightweight-charts defaults `priceLineVisible` to true, which puts a dashed horizontal line at the
 * last close with a price on the axis and no title: visually a support/resistance line, and on a chart
 * whose whole question is "did this level break?" a learner reads it as a second, unlabeled level. That
 * phantom line is what made m08 exercises appear to draw two levels, one of them mislabeled. It is off
 * now, and this locks it off — a regression here is invisible in a screenshot review but breaks every
 * level-reading exercise and figure at once.
 *
 * The library is mocked because it renders to canvas: what matters is the options the component asks
 * for, which is exactly what a mock can assert and a jsdom render cannot.
 */

const addSeries = vi.fn();
const createPriceLine = vi.fn();
const setData = vi.fn();

function seriesHandle() {
  return { setData, createPriceLine, applyOptions: vi.fn() };
}

vi.mock("lightweight-charts", () => ({
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
    panes: () => [
      { setStretchFactor: vi.fn() },
      { setStretchFactor: vi.fn() },
    ],
    timeScale: () => ({ setVisibleLogicalRange: vi.fn() }),
    remove: vi.fn(),
  }),
}));

vi.mock("@/lib/theme", () => ({ useTheme: () => ({ resolvedTheme: "dark" }) }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    i18n: { resolvedLanguage: "es" },
    t: (key: string, opts?: { defaultValue?: string }) =>
      key === "level.resistance" ? "Resistencia" : (opts?.defaultValue ?? key),
  }),
}));

const { CandleChart } = await import("./CandleChart");

// The chart builds itself in an effect, so it needs a client render (renderToStaticMarkup, which the
// other tests use, never runs effects). `act` flushes them without pulling in a testing library.
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

describe("price-pane horizontal lines", () => {
  beforeEach(() => {
    addSeries.mockClear();
    createPriceLine.mockClear();
    setData.mockClear();
  });

  it("disables the library's default last-close price line on the candles", () => {
    mount(<CandleChart series={series} indicator="none" />);
    const candles = addSeries.mock.calls.find((c) => c[0] === "candles");
    expect(candles, "a candlestick series must be added").toBeTruthy();
    expect((candles?.[1] as { priceLineVisible?: boolean }).priceLineVisible).toBe(false);
  });

  it("draws one line per planted level and nothing else on the price pane", () => {
    mount(
      <CandleChart
        series={series}
        indicator="none"
        levels={[{ price: 13.9, label: "resistance", kind: "resistance" }]}
      />,
    );
    // Exactly the planted level: no phantom last-value line, no extra guide on the price pane.
    expect(createPriceLine).toHaveBeenCalledTimes(1);
    expect(createPriceLine.mock.calls[0][0]).toMatchObject({ price: 13.9, title: "Resistencia" });
  });

  it("titles each level from its own label, so same-kind levels never collapse into one name", () => {
    mount(
      <CandleChart
        series={series}
        indicator="none"
        levels={[
          { price: 13.0, label: "382", kind: "fib" },
          { price: 12.0, label: "618", kind: "fib" },
        ]}
      />,
    );
    const titles = createPriceLine.mock.calls.map((c) => (c[0] as { title: string }).title);
    expect(titles).toEqual(["382", "618"]);
  });

  it("draws a trade's plan lines by name, in one neutral colour distinct from support/resistance", () => {
    mount(
      <CandleChart
        series={series}
        indicator="none"
        levels={[
          { price: 13.9, label: "resistance", kind: "resistance" },
          { price: 13.2, label: "target", kind: "plan" },
          { price: 12.4, label: "entry", kind: "plan" },
          { price: 11.6, label: "stop", kind: "plan" },
        ]}
      />,
    );
    const calls = createPriceLine.mock.calls.map((c) => c[0] as { title: string; color: string });
    // Each plan line keeps its own title (three same-kind lines must not collapse into one name)...
    expect(calls.map((c) => c.title)).toEqual(["Resistencia", "target", "entry", "stop"]);
    // ...and they share a colour that is NOT the resistance colour: a stop line that renders red reads
    // as a level the market defended rather than as a price the trader chose.
    const [resistance, ...plan] = calls.map((c) => c.color);
    expect(new Set(plan).size).toBe(1);
    expect(plan[0]).not.toBe(resistance);
  });

  it("keeps the RSI pane's 30/70 guides off the price pane", () => {
    mount(<CandleChart series={series} indicator="rsi" rsi={[50, 55, 60, 58]} />);
    // Two guides, both created on the RSI line series — and still no price line for the candles.
    expect(createPriceLine).toHaveBeenCalledTimes(2);
    const prices = createPriceLine.mock.calls.map((c) => (c[0] as { price: number }).price);
    expect(prices).toEqual([30, 70]);
  });
});
