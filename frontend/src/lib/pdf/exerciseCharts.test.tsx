import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { IChartApi } from "lightweight-charts";
import type { PrintExercise, PrintExercises } from "@/api/course";
import { useResolvedTheme, type ResolvedTheme } from "@/lib/theme";

/**
 * Capturing the charts that ARE the question.
 *
 * The assertion that matters is the negative one — no markers, no shaded zones — and its failure mode is
 * silent: a chart with the answer drawn on it still looks like a perfectly good chart.
 */

interface Rendered {
  theme?: string;
  markers?: unknown;
  bands?: unknown;
  indicator?: string;
  height?: number;
  rightOffset?: number;
  pixelRatioWhenDrawn: number;
}

const rendered: Rendered[] = [];
let bitmap = { width: 1520, height: 600 };
let failOnRender: Error | null = null;

vi.mock("@/components/charts/CandleChart", () => ({
  CandleChart: (props: Record<string, unknown> & { onReady?: (chart: IChartApi) => void }) => {
    if (failOnRender) throw failOnRender;
    const theme = useResolvedTheme(props.theme as ResolvedTheme | undefined);
    useTranslation();
    useEffect(() => {
      rendered.push({
        theme,
        markers: props.markers,
        bands: props.bands,
        indicator: props.indicator as string,
        height: props.height as number,
        rightOffset: props.rightOffset as number,
        pixelRatioWhenDrawn: window.devicePixelRatio,
      });
      props.onReady?.({
        takeScreenshot: () =>
          ({
            width: bitmap.width,
            height: bitmap.height,
            toDataURL: () => "data:image/png;base64,CHART",
          }) as unknown as HTMLCanvasElement,
      } as unknown as IChartApi);
    });
    return null;
  },
}));

const { captureExerciseCharts, chartExercises } = await import("@/lib/pdf/exerciseCharts");

function exercise(id: string, isChart = true): PrintExercise {
  return {
    id,
    number: "1.1",
    type: "pattern_chart",
    isChart,
    seed: 7,
    prompt: "Judge the break.",
    payload: {
      series: { time: [1, 2], open: [1, 1], high: [2, 2], low: [0, 0], close: [1, 1], volume: [10, 10] },
      rsi: [50, 55],
      indicator: "rsi",
      choices: ["no_break"],
    },
    answer: { kind: "chart", label: "no_break", anchors: [], zones: [] },
  };
}

beforeEach(() => {
  rendered.length = 0;
  bitmap = { width: 1520, height: 600 };
  failOnRender = null;
  document.body.innerHTML = "";
});

describe("capturing an exercise chart", () => {
  it("draws it light, at print resolution, with the answer left off", async () => {
    const captured = await captureExerciseCharts([exercise("m08-ex-1")]);
    expect(captured.get("m08-ex-1")).toBe("data:image/png;base64,CHART");
    expect(rendered[0].theme).toBe("light");
    expect(rendered[0].pixelRatioWhenDrawn).toBe(2);
    expect(rendered[0].indicator).toBe("rsi");
    // The whole point: no swings, no zones. The question is not allowed to answer itself.
    expect(rendered[0].markers).toBeUndefined();
    expect(rendered[0].bands).toBeUndefined();
  });

  it("counts progress against the charts it will draw", async () => {
    const seen: { done: number; total: number }[] = [];
    await captureExerciseCharts([exercise("a"), exercise("b")], (p) => seen.push(p));
    expect(seen).toEqual([
      { done: 0, total: 2 },
      { done: 1, total: 2 },
      { done: 2, total: 2 },
    ]);
  });

  it("stops, naming the exercise, when the chart will not render", async () => {
    failOnRender = new Error("useTheme must be used within a ThemeProvider");
    await expect(captureExerciseCharts([exercise("m09-ex-2")])).rejects.toThrowError(
      /exercise m09-ex-2 failed to render: useTheme must be used within a ThemeProvider/,
    );
    expect(document.body.children).toHaveLength(0);
  });

  it("refuses a bitmap too small to print", async () => {
    bitmap = { width: 1, height: 1 };
    await expect(captureExerciseCharts([exercise("m10-ex-3")])).rejects.toThrowError(
      /exercise m10-ex-3: bitmap is 1×1, too small to print/,
    );
    expect(document.body.children).toHaveLength(0);
  });

  it("hands the page back exactly as it found it", async () => {
    const pixelRatio = window.devicePixelRatio;
    await captureExerciseCharts([exercise("x"), exercise("y")]);
    expect(window.devicePixelRatio).toBe(pixelRatio);
    expect(document.body.children).toHaveLength(0);
  });
});

describe("which exercises need a chart", () => {
  it("is every chart-bearing one, in print order, and nothing else", () => {
    const print: PrintExercises = {
      locale: "en",
      lessons: [
        { lessonId: "l1", moduleId: "m", exercises: [exercise("a"), exercise("b", false)] },
        { lessonId: "l2", moduleId: "m", exercises: [exercise("c")] },
      ],
      excluded: [],
    };
    expect(chartExercises(print).map((e) => e.id)).toEqual(["a", "c"]);
  });
});
