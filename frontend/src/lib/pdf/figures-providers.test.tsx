import { beforeEach, describe, expect, it, vi } from "vitest";
import type { FigureData } from "@/api/course";

/**
 * The REAL `CandleChart` in the capture harness: standing it in is why nobody noticed it called
 * `useTheme`, which throws without the `ThemeProvider` the capture root omits. Only the library is
 * mocked here, which also puts "figures print light" under test at the palette handed to `createChart`.
 */

const created: { layout?: { textColor?: string; background?: { color?: string } } }[] = [];
let screenshots = 0;

function seriesHandle() {
  return { setData: vi.fn(), createPriceLine: vi.fn(), applyOptions: vi.fn() };
}

vi.mock("lightweight-charts", () => ({
  CandlestickSeries: "candles",
  HistogramSeries: "histogram",
  LineSeries: "line",
  BaselineSeries: "baseline",
  ColorType: { Solid: "solid" },
  CrosshairMode: { Normal: 0 },
  TickMarkType: { Year: 0, Month: 1, DayOfMonth: 2 },
  createSeriesMarkers: vi.fn(),
  createChart: (_el: HTMLElement, options: { layout?: { textColor?: string } }) => {
    created.push(options);
    return {
      addSeries: () => seriesHandle(),
      panes: () => [{ setStretchFactor: vi.fn() }, { setStretchFactor: vi.fn() }],
      timeScale: () => ({ setVisibleLogicalRange: vi.fn() }),
      takeScreenshot: () => {
        screenshots++;
        return {
          width: 1520,
          height: 600,
          toDataURL: () => "data:image/png;base64,REAL-COMPONENT",
        } as unknown as HTMLCanvasElement;
      },
      remove: vi.fn(),
    };
  },
}));

const getFigure = vi.fn<(id: string) => Promise<FigureData>>();
vi.mock("@/api/course", () => ({ getFigure: (id: string) => getFigure(id) }));

const { captureFigures } = await import("@/lib/pdf/figures");

beforeEach(() => {
  created.length = 0;
  screenshots = 0;
  getFigure.mockReset();
  document.body.innerHTML = "";
});

describe("the real chart component inside the capture harness", () => {
  beforeEach(() => {
    getFigure.mockResolvedValue({
      id: "fig-real",
      kind: "chart",
      caption: "A real figure",
      panels: [
        {
          series: { time: [1, 2], open: [1, 1], high: [2, 2], low: [0, 0], close: [1, 1], volume: [1, 1] },
          levels: [{ price: 1.5, label: "resistance", kind: "resistance" }],
          indicator: "none",
          annotations: [{ index: 1, kind: "high", label: "sweep" }],
        },
      ],
    });
  });

  it("renders with only the harness's providers — no ThemeProvider, no router, no query client", async () => {
    const captured = await captureFigures(["fig-real"]);
    expect(captured.get("fig-real")?.panels).toEqual(["data:image/png;base64,REAL-COMPONENT"]);
    expect(screenshots).toBe(1);
  });

  it("hands the library the LIGHT palette, whatever the reader is browsing in", async () => {
    await captureFigures(["fig-real"]);
    // `palette(false)`: the light branch of the component's own colours, not a prop echoed back.
    expect(created[0].layout?.textColor).toBe("#6b7280");
  });
});
