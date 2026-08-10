import { act, type ReactElement } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The two render primitives m15 and m16 added — what the RENDERER owes them.
 *
 * A sloped line (m15) is drawn as a two-point LineSeries rather than as a price line, because a price
 * line is horizontal by construction. The two points are the anchors the backend published, and drawing
 * anything else there — a padded series, a re-derived slope — would put a line on the chart that the
 * respect contract never measured.
 *
 * The zero-centred pane (m16) is a signed histogram plus an optional state row. The row is a FLAG: it
 * has to render as a constant-height strip whose only variable is colour, because a second real
 * histogram would read as a second quantity and a coloured direction would say which way the squeeze
 * points — the one thing m16-l1 spends its closing section refusing to say.
 *
 * The library is mocked: it renders to canvas, so only the requested options are assertable.
 */

const addSeries = vi.fn();
const createPriceLine = vi.fn();
const setData = vi.fn();

/** Every series the chart built, with the options it was built with and the data it was given.
 *
 * The chart adds several histograms to the same pane, and a shared `setData` spy cannot tell them
 * apart — matching on "six points, all one value" found the volume strip instead of the state row. */
interface Built {
  type: string;
  options: Record<string, unknown>;
  data: Record<string, unknown>[];
}
const built: Built[] = [];

function seriesHandle(entry: Built) {
  return {
    setData: (data: Record<string, unknown>[]) => {
      entry.data = data;
      setData(data);
    },
    createPriceLine,
    applyOptions: vi.fn(),
  };
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
      const entry: Built = { type: args[0] as string, options: args[1] as Record<string, unknown>, data: [] };
      built.push(entry);
      return seriesHandle(entry);
    },
    panes: () => [
      { setStretchFactor: vi.fn() },
      { setStretchFactor: vi.fn() },
      { setStretchFactor: vi.fn() },
    ],
    timeScale: () => ({ setVisibleLogicalRange: vi.fn() }),
    remove: vi.fn(),
  }),
}));

vi.mock("@/lib/theme", () => ({
  useResolvedTheme: (override?: "light" | "dark") => override ?? "dark",
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    i18n: { resolvedLanguage: "en" },
    t: (key: string, opts?: { defaultValue?: string }) =>
      key === "diagonal.trendline" ? "Trendline" : (opts?.defaultValue ?? key),
  }),
}));

const { CandleChart, palette } = await import("./CandleChart");

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function mount(node: ReactElement): void {
  const host = document.createElement("div");
  document.body.appendChild(host);
  act(() => {
    createRoot(host).render(node);
  });
}

const series = {
  time: [1, 2, 3, 4, 5, 6],
  open: [10, 11, 12, 13, 14, 15],
  high: [11, 12, 13, 14, 15, 16],
  low: [9, 10, 11, 12, 13, 14],
  close: [11, 12, 13, 13.5, 14.5, 15.5],
  volume: [1, 1, 1, 1, 1, 1],
};

const trendline = {
  start: 1,
  end: 5,
  start_price: 9.5,
  end_price: 13.5,
  label: "trendline",
  kind: "support",
};

function lineSeriesCalls() {
  return addSeries.mock.calls.filter((c) => c[0] === "line");
}

describe("sloped lines on the price pane", () => {
  beforeEach(() => {
    addSeries.mockClear();
    createPriceLine.mockClear();
    setData.mockClear();
  });

  it("draws a diagonal as exactly two points — its own anchors, nothing interpolated", () => {
    mount(<CandleChart series={series} indicator="none" diagonals={[trendline]} />);
    const drawn = setData.mock.calls.map((c) => c[0]);
    const twoPoint = drawn.filter((d: unknown[]) => d.length === 2);
    expect(twoPoint, "the diagonal renders as one two-point series").toHaveLength(1);
    expect(twoPoint[0]).toEqual([
      { time: series.time[1], value: 9.5 },
      { time: series.time[5], value: 13.5 },
    ]);
  });

  it("puts it on the PRICE pane and never as a horizontal price line", () => {
    mount(<CandleChart series={series} indicator="none" diagonals={[trendline]} />);
    const call = lineSeriesCalls()[0];
    expect(call?.[2], "pane 0 — a diagonal is price-pane furniture").toBe(0);
    // A price line is horizontal by construction, so a diagonal drawn as one would be the wrong line.
    expect(createPriceLine).not.toHaveBeenCalled();
  });

  it("colours and titles it like the level it is a moving version of", () => {
    mount(<CandleChart series={series} indicator="none" diagonals={[trendline]} />);
    const options = lineSeriesCalls()[0]?.[1] as { color: string; title: string; lineStyle: number };
    expect(options.color).toBe(palette("dark").up); // support: the same green a flat support gets
    expect(options.title).toBe("Trendline"); // own label first, via `diagonal.*`
    expect(options.lineStyle).toBe(2); // dashed: a line somebody drew, not a price the book holds
  });

  it("draws both edges of a channel, each with its own name", () => {
    mount(
      <CandleChart
        series={series}
        indicator="none"
        diagonals={[
          { ...trendline, label: "channel" },
          { ...trendline, start_price: 11.5, end_price: 15.5, label: "channel_parallel", kind: "resistance" },
        ]}
      />,
    );
    const titles = lineSeriesCalls().map((c) => (c[1] as { title: string }).title);
    expect(titles).toEqual(["channel", "channel_parallel"]);
  });
});

describe("the zero-centred momentum pane", () => {
  beforeEach(() => {
    addSeries.mockClear();
    createPriceLine.mockClear();
    setData.mockClear();
    built.length = 0;
  });

  const momentum = { values: [-2, -1, 0, 1, 2, 3], state: [1, 1, 1, 0, 0, 0] };

  it("colours the histogram by SIGN, so the pane is read against zero", () => {
    mount(<CandleChart series={series} indicator="momentum" momentum={{ values: momentum.values }} />);
    const bars = setData.mock.calls.map((c) => c[0]).find((d: { value: number }[]) => d.length === 6 && d[0].value === -2);
    const colours = (bars as { color: string }[]).map((b) => b.color);
    const c = palette("dark");
    expect(colours).toEqual([c.downVol, c.downVol, c.upVol, c.upVol, c.upVol, c.upVol]);
  });

  it("draws the zero guide the whole reading depends on", () => {
    mount(<CandleChart series={series} indicator="momentum" momentum={{ values: momentum.values }} />);
    expect(createPriceLine).toHaveBeenCalledTimes(1);
    expect(createPriceLine.mock.calls[0][0]).toMatchObject({ price: 0, axisLabelVisible: false });
  });

  it("renders the state row as a flag: one height, two colours, no direction", () => {
    mount(<CandleChart series={series} indicator="momentum" momentum={momentum} />);
    // The state row is the one series built with an explicit `base` — that is what pins it to zero.
    const row = built.find((b) => b.type === "histogram" && "base" in b.options);
    expect(row, "the state row is drawn").toBeTruthy();
    const values = row!.data.map((p) => p.value);
    expect(new Set(values).size, "one height — it is a flag, not a quantity").toBe(1);
    const c = palette("dark");
    expect(row!.data.map((p) => p.color)).toEqual([
      c.squeezeOn, c.squeezeOn, c.squeezeOn, c.squeezeOff, c.squeezeOff, c.squeezeOff,
    ]);
    // Never the up/down pair: a compression flag that were green would claim a direction.
    expect(new Set(row!.data.map((p) => p.color))).not.toContain(c.upVol);
  });

  it("omits the state row entirely when the injector supplies none", () => {
    mount(<CandleChart series={series} indicator="momentum" momentum={{ values: momentum.values }} />);
    // Volume, and the momentum histogram. No third strip.
    expect(built.filter((b) => b.type === "histogram")).toHaveLength(2);
  });
});

describe("paired envelope overlays", () => {
  beforeEach(() => {
    addSeries.mockClear();
    setData.mockClear();
  });

  it("gives an envelope's two edges ONE colour, so four lines read as two bands", () => {
    mount(
      <CandleChart
        series={series}
        indicator="none"
        overlays={{
          bb_upper: [1, 2, 3, 4, 5, 6],
          bb_lower: [1, 2, 3, 4, 5, 6],
          kc_upper: [1, 2, 3, 4, 5, 6],
          kc_lower: [1, 2, 3, 4, 5, 6],
        }}
      />,
    );
    const colours = lineSeriesCalls().map((c) => (c[1] as { color: string }).color);
    expect(colours[0]).toBe(colours[1]); // bb_upper === bb_lower
    expect(colours[2]).toBe(colours[3]); // kc_upper === kc_lower
    expect(colours[0]).not.toBe(colours[2]); // ...and the two envelopes differ
  });

  it("names each envelope once — the lower edge repeats a label the reader already has", () => {
    mount(
      <CandleChart
        series={series}
        indicator="none"
        overlays={{ bb_upper: [1, 2, 3, 4, 5, 6], bb_lower: [1, 2, 3, 4, 5, 6] }}
      />,
    );
    const shown = lineSeriesCalls().map((c) => (c[1] as { lastValueVisible: boolean }).lastValueVisible);
    expect(shown).toEqual([true, false]);
  });

  it("leaves the moving averages exactly as they were: one colour each, in order", () => {
    mount(
      <CandleChart
        series={series}
        indicator="none"
        overlays={{ ema20: [1, 2, 3, 4, 5, 6], ema50: [1, 2, 3, 4, 5, 6] }}
      />,
    );
    const calls = lineSeriesCalls().map((c) => c[1] as { color: string; title: string; lastValueVisible: boolean });
    expect(calls.map((o) => o.title)).toEqual(["ema20", "ema50"]);
    expect(calls[0].color).not.toBe(calls[1].color);
    expect(calls.map((o) => o.lastValueVisible)).toEqual([true, true]);
  });
});
