import { Component, type ReactNode } from "react";
import { createRoot, type Root as ReactRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import type { IChartApi } from "lightweight-charts";
import i18n from "@/i18n";
import { getFigure, type FigureData, type FigurePanel } from "@/api/course";
import { CandleAnatomy } from "@/components/charts/CandleAnatomy";
import { CandleChart, type SwingMarker } from "@/components/charts/CandleChart";
import type { CapturedFigure } from "@/lib/pdf/document";

/**
 * Figure capture for the PDF: each figure drawn off-screen by the app's OWN chart components, so there
 * is no second renderer to drift, then screenshotted as a PNG.
 *
 * Every failure throws, naming the figure — the prose around it quotes the numbers it draws.
 */

/** Stage size in CSS px, kept small so lightweight-charts' fixed 12 px axis labels stay ~8 pt. */
export const STAGE_WIDTH = 760;
export const STAGE_HEIGHT = 300;
export const PRINT_SCALE = 2;

export interface CaptureProgress {
  done: number;
  total: number;
}

function toMarkers(annotations: FigurePanel["annotations"]): SwingMarker[] {
  return annotations.map((a) => ({
    index: a.index,
    label: a.label,
    kind: a.kind === "high" ? "high" : a.kind === "low" ? "low" : "neutral",
  }));
}

/** The print twin of `LessonFigure`'s map of hand-drawn figures. */
const SVG_FIGURES: Record<string, () => ReactNode> = {
  "candle-anatomy": () => <CandleAnatomy theme="light" />,
};

export function nextFrame(): Promise<void> {
  return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
}

/** Catches a figure's render error, so the export reports it rather than an indistinguishable timeout. */
export class CaptureBoundary extends Component<{ onError: (error: Error) => void; children: ReactNode }> {
  componentDidCatch(error: Error): void {
    this.props.onError(error);
  }
  render(): ReactNode {
    return this.props.children;
  }
}

/** React runs `useEffect` after paint, so "the chart exists" is polled, not known from the render call. */
export async function waitFor(ready: () => boolean, failure: () => Error | null, what: string): Promise<void> {
  for (let attempt = 0; attempt < 180; attempt++) {
    if (ready()) return;
    const error = failure();
    if (error) throw new Error(`${what} failed to render: ${error.message}`, { cause: error });
    await nextFrame();
  }
  throw new Error(`${what} did not render in time`);
}

/** Off-screen but still laid out: `display: none` would give the chart zero width to measure. */
export function makeStage(width: number, height: number): HTMLDivElement {
  const stage = document.createElement("div");
  stage.setAttribute("aria-hidden", "true");
  Object.assign(stage.style, {
    position: "fixed",
    top: "0px",
    left: "-20000px",
    width: `${width}px`,
    height: `${height}px`,
    background: "#ffffff",
    colorScheme: "light",
  } satisfies Partial<CSSStyleDeclaration>);
  document.body.appendChild(stage);
  return stage;
}

export interface Mounted {
  root: ReactRoot;
  failure: () => Error | null;
}

/** i18n only — figures are handed an explicit `theme`, so they must not need the app's ThemeProvider. */
export async function mount(stage: HTMLElement, node: ReactNode): Promise<Mounted> {
  const thrown: { error: Error | null } = { error: null };
  const root = createRoot(stage);
  root.render(
    <CaptureBoundary
      onError={(error) => {
        thrown.error = error;
      }}
    >
      <I18nextProvider i18n={i18n}>{node}</I18nextProvider>
    </CaptureBoundary>,
  );
  await nextFrame();
  return { root, failure: () => thrown.error };
}

/** Height of each panel when a chart is drawn with its multi-timeframe companion (m20-l2). */
export const PAIRED_STAGE_HEIGHT = 210;

/** A degenerate bitmap makes the typesetter SPIN rather than complain, so reject it while it has a name. */
const MIN_BITMAP_PX = 64;

export function toPng(canvas: HTMLCanvasElement, what: string): string {
  if (canvas.width < MIN_BITMAP_PX || canvas.height < MIN_BITMAP_PX) {
    throw new Error(`${what}: bitmap is ${canvas.width}×${canvas.height}, too small to print`);
  }
  const url = canvas.toDataURL("image/png");
  if (!url.startsWith("data:image/png;base64,")) {
    throw new Error(`${what}: canvas produced no PNG`);
  }
  return url;
}

/** Draw one chart off-screen and hand back its bitmap. `what` names it in every failure. */
export async function captureChart(node: (onReady: (c: IChartApi) => void) => ReactNode, what: string, height: number): Promise<HTMLCanvasElement> {
  const stage = makeStage(STAGE_WIDTH, height);
  let mounted: Mounted | null = null;
  try {
    const ready: { chart: IChartApi | null } = { chart: null };
    mounted = await mount(
      stage,
      node((chart) => {
        ready.chart = chart;
      }),
    );
    await waitFor(() => ready.chart !== null, mounted.failure, what);
    await nextFrame(); // one more, so the panes have laid out before we ask for a bitmap
    return ready.chart!.takeScreenshot();
  } finally {
    mounted?.root.unmount();
    stage.remove();
  }
}

/**
 * Stack two captured panels into one bitmap (m20-l2's paired frames).
 *
 * One image rather than two, so nothing downstream has to learn about pairs: a figure keeps one entry
 * per panel and `ExerciseChartLookup` keeps returning one image per exercise — which is what keeps the
 * printed exercise / answer-key bijection a bijection.
 */
export function stackCanvases(top: HTMLCanvasElement, bottom: HTMLCanvasElement, what: string): string {
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(top.width, bottom.width);
  canvas.height = top.height + bottom.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error(`${what}: no 2d context to stack the panels on`);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(top, 0, 0);
  ctx.drawImage(bottom, 0, top.height);
  return toPng(canvas, what);
}

async function capturePanel(panel: FigurePanel, figureId: string): Promise<string> {
  const what = `figure ${figureId}`;
  const paired = panel.context !== undefined;
  const height = paired ? PAIRED_STAGE_HEIGHT : STAGE_HEIGHT;
  const main = await captureChart(
    (onReady) => (
      <CandleChart
        series={panel.series}
        rsi={panel.rsi}
        macd={panel.macd}
        oi={panel.oi}
        cvd={panel.cvd}
        momentum={panel.momentum ? { values: panel.momentum, state: panel.momentum_state } : undefined}
        overlays={panel.overlays}
        levels={panel.levels}
        diagonals={panel.diagonals}
        bands={panel.bands}
        indicator={panel.indicator}
        markers={toMarkers(panel.annotations)}
        height={height}
        rightOffset={10}
        theme="light"
        onReady={onReady}
      />
    ),
    what,
    height,
  );
  if (!panel.context) return toPng(main, what);
  const companion = await captureChart(
    (onReady) => (
      <CandleChart
        series={panel.context!.series}
        indicator="none"
        height={height}
        rightOffset={10}
        theme="light"
        onReady={onReady}
      />
    ),
    `${what} (context panel)`,
    height,
  );
  return panel.context.position === "above"
    ? stackCanvases(companion, main, what)
    : stackCanvases(main, companion, what);
}

/** Paint properties to inline: Tailwind class colours do not survive serialization away from the sheet. */
const INLINED_SVG_PROPS = [
  "fill",
  "stroke",
  "stroke-width",
  "stroke-dasharray",
  "stroke-linecap",
  "font-family",
  "font-size",
  "font-weight",
  "text-anchor",
  "opacity",
] as const;

function inlineStyles(source: Element, target: Element): void {
  const computed = window.getComputedStyle(source);
  for (const prop of INLINED_SVG_PROPS) {
    const value = computed.getPropertyValue(prop);
    if (value) target.setAttribute(prop, value);
  }
  const targetChildren = Array.from(target.children);
  Array.from(source.children).forEach((child, i) => {
    const twin = targetChildren[i];
    if (twin) inlineStyles(child, twin);
  });
}

async function captureSvg(name: string, figureId: string): Promise<string> {
  const render = SVG_FIGURES[name];
  if (!render) throw new Error(`figure ${figureId}: no print renderer for svg "${name}"`);
  const stage = makeStage(STAGE_WIDTH, STAGE_HEIGHT);
  let mounted: Mounted | null = null;
  try {
    mounted = await mount(stage, render());
    await waitFor(() => stage.querySelector("svg") !== null, mounted.failure, `figure ${figureId}`);
    const svg = stage.querySelector("svg");
    if (!svg) throw new Error(`figure ${figureId}: svg did not render`);
    const clone = svg.cloneNode(true) as SVGSVGElement;
    inlineStyles(svg, clone);
    const box = svg.getBoundingClientRect();
    const width = Math.round(box.width) || STAGE_WIDTH;
    const height = Math.round(box.height) || STAGE_HEIGHT;
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.setAttribute("width", String(width));
    clone.setAttribute("height", String(height));
    clone.removeAttribute("class");
    const markup = new XMLSerializer().serializeToString(clone);
    const image = new Image();
    image.width = width;
    image.height = height;
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error(`figure ${figureId}: svg bitmap failed to decode`));
      image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`;
    });
    const canvas = document.createElement("canvas");
    canvas.width = width * PRINT_SCALE;
    canvas.height = height * PRINT_SCALE;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error(`figure ${figureId}: no 2d context for the svg bitmap`);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    return toPng(canvas, `figure ${figureId}`);
  } finally {
    mounted?.root.unmount();
    stage.remove();
  }
}

async function captureOne(data: FigureData): Promise<CapturedFigure> {
  if (data.kind === "svg") {
    if (!data.svg) throw new Error(`figure ${data.id}: svg figure names no drawing`);
    return { id: data.id, caption: data.caption, panels: [await captureSvg(data.svg, data.id)] };
  }
  if (!data.panels?.length) throw new Error(`figure ${data.id}: chart figure has no panels`);
  const panels: string[] = [];
  for (const panel of data.panels) panels.push(await capturePanel(panel, data.id));
  return { id: data.id, caption: data.caption, panels };
}

/** Pin the pixel ratio while drawing, so the export's resolution is the same on every display. */
export function withPrintPixelRatio<T>(run: () => Promise<T>): Promise<T> {
  const original = Object.getOwnPropertyDescriptor(window, "devicePixelRatio");
  try {
    Object.defineProperty(window, "devicePixelRatio", { value: PRINT_SCALE, configurable: true });
  } catch {
    // A browser that refuses the override just yields its own resolution — still a valid PDF.
  }
  const restore = () => {
    if (original) Object.defineProperty(window, "devicePixelRatio", original);
    else Reflect.deleteProperty(window, "devicePixelRatio");
  };
  return run().then(
    (value) => {
      restore();
      return value;
    },
    (error) => {
      restore();
      throw error;
    },
  );
}

/** Draw every figure the export needs, keyed by id. Ids repeat across lessons; each is drawn once. */
export async function captureFigures(
  figureIds: string[],
  onProgress?: (progress: CaptureProgress) => void,
): Promise<Map<string, CapturedFigure>> {
  const unique = [...new Set(figureIds)];
  const captured = new Map<string, CapturedFigure>();
  return withPrintPixelRatio(async () => {
    for (const [index, id] of unique.entries()) {
      onProgress?.({ done: index, total: unique.length });
      let data: FigureData;
      try {
        data = await getFigure(id);
      } catch (cause) {
        throw new Error(`figure ${id} could not be loaded`, { cause });
      }
      captured.set(id, await captureOne(data));
    }
    onProgress?.({ done: unique.length, total: unique.length });
    return captured;
  });
}
