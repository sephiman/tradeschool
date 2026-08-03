import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { IChartApi } from "lightweight-charts";
import type { FigureData, FigurePanel } from "@/api/course";
import { useResolvedTheme, type ResolvedTheme } from "@/lib/theme";

/**
 * The capture mechanics: mounting each panel off-screen, waiting for the chart rather than guessing,
 * screenshotting at print resolution, refusing a bitmap too small to be a figure, and leaving no trace in
 * the page. The renderer is stood in for (jsdom has no canvas); `figures-providers.test.tsx` mounts the
 * real one.
 */

interface Rendered {
  theme?: string;
  height?: number;
  rightOffset?: number;
  indicator?: string;
  pixelRatioWhenDrawn: number;
  stage?: { width: string; display: string; position: string; left: string; background: string };
}

const rendered: Rendered[] = [];
/** What the fake chart's screenshot pretends to be. */
let bitmap = { width: 1520, height: 600 };
/** Makes the stand-in throw during render, as a component with a missing dependency does. */
let failOnRender: Error | null = null;

/** Calls the same hooks the real component does, so the harness's provider contract is exercised rather
 *  than assumed — a dumb stub is what hid the shipped `useTheme` bug from this suite. */
vi.mock("@/components/charts/CandleChart", () => ({
  CandleChart: (props: Record<string, unknown> & { onReady?: (chart: IChartApi) => void }) => {
    if (failOnRender) throw failOnRender;
    const theme = useResolvedTheme(props.theme as ResolvedTheme | undefined);
    useTranslation();
    useEffect(() => {
      const canvas = {
        width: bitmap.width,
        height: bitmap.height,
        toDataURL: () => `data:image/png;base64,PANEL-${props.indicator as string}`,
      } as unknown as HTMLCanvasElement;
      const stage = document.querySelector('div[aria-hidden="true"]') as HTMLElement | null;
      rendered.push({
        // What the component resolved, not what it was handed.
        theme,
        height: props.height as number,
        rightOffset: props.rightOffset as number,
        indicator: props.indicator as string,
        pixelRatioWhenDrawn: window.devicePixelRatio,
        stage: stage
          ? {
              width: stage.style.width,
              display: stage.style.display,
              position: stage.style.position,
              left: stage.style.left,
              background: stage.style.background,
            }
          : undefined,
      });
      props.onReady?.({ takeScreenshot: () => canvas } as unknown as IChartApi);
    });
    return null;
  },
}));

const getFigure = vi.fn<(id: string) => Promise<FigureData>>();
vi.mock("@/api/course", () => ({ getFigure: (id: string) => getFigure(id) }));

const { captureFigures } = await import("@/lib/pdf/figures");

function panel(indicator: FigurePanel["indicator"]): FigurePanel {
  return {
    series: { time: [1], open: [1], high: [2], low: [0], close: [1], volume: [10] },
    indicator,
    annotations: [{ index: 0, kind: "high", label: "sweep" }],
  };
}

beforeEach(() => {
  rendered.length = 0;
  bitmap = { width: 1520, height: 600 };
  failOnRender = null;
  getFigure.mockReset();
  document.body.innerHTML = "";
});

describe("capturing a chart figure", () => {
  it("draws every panel in order, light, and returns one PNG each with the server's caption", async () => {
    getFigure.mockResolvedValue({
      id: "fig-m10-ema-signatures",
      kind: "chart",
      caption: "Three signatures of the same average",
      panels: [panel("none"), panel("rsi"), panel("macd")],
    });

    const captured = await captureFigures(["fig-m10-ema-signatures"]);

    const figure = captured.get("fig-m10-ema-signatures");
    expect(figure?.caption).toBe("Three signatures of the same average");
    expect(figure?.panels).toEqual([
      "data:image/png;base64,PANEL-none",
      "data:image/png;base64,PANEL-rsi",
      "data:image/png;base64,PANEL-macd",
    ]);
    // Light for every panel, whatever theme the reader is browsing in.
    expect(rendered.map((r) => r.theme)).toEqual(["light", "light", "light"]);
    // …with the figure geometry the lesson page uses.
    expect(rendered.every((r) => r.height === 300 && r.rightOffset === 10)).toBe(true);
  });

  it("draws at print resolution on a real off-screen stage", async () => {
    getFigure.mockResolvedValue({ id: "f", kind: "chart", caption: "c", panels: [panel("none")] });
    await captureFigures(["f"]);
    // Doubled while drawing: a 760px stage yields a 1520px bitmap, ~230 dpi on the page.
    expect(rendered[0].pixelRatioWhenDrawn).toBe(2);
    // Off-screen but still laid out — `display:none` would give the chart zero width to measure.
    expect(rendered[0].stage).toMatchObject({
      width: "760px",
      display: "",
      position: "fixed",
      left: "-20000px",
      background: "rgb(255, 255, 255)",
    });
  });

  it("hands the page back exactly as it found it", async () => {
    const pixelRatio = window.devicePixelRatio;
    getFigure.mockResolvedValue({ id: "f", kind: "chart", caption: "c", panels: [panel("none")] });
    await captureFigures(["f"]);
    expect(window.devicePixelRatio).toBe(pixelRatio);
    expect(document.body.children).toHaveLength(0);
  });

  it("refuses a bitmap too small to be a figure instead of shipping it", async () => {
    // Printed, a tiny bitmap is a smear; handed to the typesetter, it can hang it outright.
    bitmap = { width: 1, height: 1 };
    getFigure.mockResolvedValue({ id: "fig-tiny", kind: "chart", caption: "c", panels: [panel("none")] });
    await expect(captureFigures(["fig-tiny"])).rejects.toThrowError(
      /figure fig-tiny: bitmap is 1×1, too small to print/,
    );
    expect(document.body.children).toHaveLength(0); // and still cleans up
  });

  it("reports why a figure would not render, rather than that it was slow", async () => {
    // The shipped bug's shape. Reporting a timeout sends you to performance, not to the real stack.
    failOnRender = new Error("useTheme must be used within a ThemeProvider");
    getFigure.mockResolvedValue({ id: "fig-broken", kind: "chart", caption: "c", panels: [panel("none")] });
    await expect(captureFigures(["fig-broken"])).rejects.toThrowError(
      /figure fig-broken failed to render: useTheme must be used within a ThemeProvider/,
    );
    expect(document.body.children).toHaveLength(0);
  });

  it("draws a figure used by two lessons once", async () => {
    getFigure.mockResolvedValue({ id: "f", kind: "chart", caption: "c", panels: [panel("none")] });
    const captured = await captureFigures(["f", "f", "f"]);
    expect(getFigure).toHaveBeenCalledTimes(1);
    expect(rendered).toHaveLength(1);
    expect(captured.size).toBe(1);
  });
});
