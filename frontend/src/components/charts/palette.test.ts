import { describe, expect, it, vi } from "vitest";

// CandleChart pulls in lightweight-charts at module scope; nothing here builds a chart, so the
// library is stubbed away rather than loaded.
vi.mock("lightweight-charts", () => ({
  BaselineSeries: {}, CandlestickSeries: {}, ColorType: { Solid: "solid" }, CrosshairMode: { Normal: 0 },
  HistogramSeries: {}, LineSeries: {}, TickMarkType: { Year: 0, Month: 1 },
  createChart: () => ({}), createSeriesMarkers: () => {},
}));

const { levelColor, palette } = await import("./CandleChart");

/**
 * The colours the figures are drawn with, pinned so the shipped themes cannot shift while a third is
 * tuned. Nothing else in the suite would notice: a chart in slightly wrong colours still draws.
 */

const LIGHT = {
  background: "transparent",
  text: "#6b7280",
  grid: "#eef2f7",
  border: "#e5e7eb",
  up: "#16a34a",
  down: "#dc2626",
  upVol: "rgba(22,163,74,0.3)",
  downVol: "rgba(220,38,38,0.3)",
  indicator: "#6366f1",
  signal: "#f59e0b",
  oi: "#0891b2",
  cvd: "#0d9488",
  marker: "#111827",
  band: "#111827",
  bandFill: "rgba(17,24,39,0.08)",
  // m32's compression row. Two neutrals, never the up/down pair: a squeeze says expansion is coming
  // and not which way, so a green flag would be the lesson's own error painted onto its figure.
  squeezeOn: "#111827",
  squeezeOff: "#9ca3af",
  overlays: ["#2563eb", "#9333ea", "#0891b2", "#ca8a04"],
  crosshair: undefined,
};

const DARK = {
  ...LIGHT,
  text: "#9ca3af",
  grid: "#1f2937",
  border: "#374151",
  upVol: "rgba(22,163,74,0.4)",
  downVol: "rgba(220,38,38,0.4)",
  marker: "#e5e7eb",
  band: "#e5e7eb",
  bandFill: "rgba(229,231,235,0.10)",
  squeezeOn: "#e5e7eb",
  squeezeOff: "#4b5563",
  overlays: ["#60a5fa", "#c084fc", "#22d3ee", "#facc15"],
};

describe("the chart palette", () => {
  it("draws light exactly as it always has", () => {
    expect(palette("light")).toEqual(LIGHT);
  });

  it("draws dark exactly as it always has", () => {
    expect(palette("dark")).toEqual(DARK);
  });

  // The delta, stated as a whitelist rather than a set of expected values: the test fails both when a
  // key that should have moved didn't, and when one that shouldn't have moved did.
  it("changes only the background and the chrome for OLED", () => {
    const oled = palette("oled");
    const moved = Object.keys(DARK).filter(
      (k) => JSON.stringify(oled[k as keyof typeof oled]) !== JSON.stringify(DARK[k as keyof typeof DARK]),
    );
    expect(moved.sort()).toEqual(["background", "border", "crosshair", "grid"]);
    expect(oled.background).toBe("#000000");
  });

  // Light and dark must reach the chart with no crosshair opinion at all, or the library's default —
  // which is what they render today — gets replaced by whatever we would have had to invent.
  it.each(["light", "dark"] as const)("leaves the %s crosshair to the library", (theme) => {
    expect(palette(theme).crosshair).toBeUndefined();
  });

  it("gives OLED a crosshair it can actually see", () => {
    expect(palette("oled").crosshair).toBe("#5a5a5a");
  });

  // Shared with SharedLedger's OLED `--color-chart-grid` / `--color-border-strong`. Pinned because the
  // two apps are read side by side and a drifted seam is visible there long before it is here.
  it("draws its chrome in the ecosystem's OLED greys", () => {
    expect(palette("oled").grid).toBe("#262626");
    expect(palette("oled").border).toBe("#454545");
  });
});

describe("level colours on pure black", () => {
  // `plan` is the kind the brief singles out, and the one at risk: it is not red or green by design
  // (m21/m24 — a stop line must not look like a resistance), so it borrows the marker neutral, and
  // that neutral is the one colour a pure-black theme is tempted to push to full white.
  it("keeps the plan line on the marker neutral, not white", () => {
    const oled = palette("oled");
    expect(levelColor(oled, "plan")).toBe(oled.marker);
    expect(oled.marker).toBe("#e5e7eb");
  });

  it.each([
    ["support", "up"],
    ["resistance", "down"],
    ["fib", "signal"],
    ["shelf", "text"],
  ] as const)("keeps %s reading as the dark theme's %s", (kind, key) => {
    const oled = palette("oled");
    expect(levelColor(oled, kind)).toBe(DARK[key]);
    expect(oled[key]).toBe(DARK[key]);
  });
});
