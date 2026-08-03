import type { Style, StyleDictionary } from "pdfmake/interfaces";

/** Print geometry, palette and type scale: A4 in PDF points, deliberately light and chrome-free — the
 *  app's proportions carried onto paper, with no dark surfaces, cards or badges. */

export const PAGE = {
  size: "A4" as const,
  width: 595.28, // A4; only the width is needed, to measure the text column
  /** left, top, right, bottom — the bottom leaves room for the running footer. */
  margins: [56, 54, 56, 62] as [number, number, number, number],
} as const;

export function contentWidth(): number {
  return PAGE.width - PAGE.margins[0] - PAGE.margins[2];
}

/** Width of one image when `perRow` panels share a row — two-up, like the app's `sm:` grid. */
export function panelWidth(perRow: number): number {
  const gap = 10;
  return (contentWidth() - gap * (perRow - 1)) / perRow;
}

export const PRINT = {
  ink: "#1f2937",
  heading: "#111827",
  primary: "#4f46e5",
  muted: "#6b7280",
  rule: "#e5e7eb",
  marker: "#9ca3af",
  link: "#4f46e5",
  codeFill: "#f3f4f6",
  codeText: "#111827",
  notes: {
    info: { fill: "#eef2ff", border: "#6366f1" },
    warning: { fill: "#fffbeb", border: "#f59e0b" },
    tip: { fill: "#ecfdf5", border: "#10b981" },
  } as Record<string, { fill: string; border: string }>,
} as const;

/** The embedded print face. See `assets/fonts/liberation-sans/README.md` for why it is embedded. */
export const PRINT_FONT = "LiberationSans";

export const DEFAULT_STYLE: Style = {
  font: PRINT_FONT,
  fontSize: 10.5,
  lineHeight: 1.35,
  color: PRINT.ink,
};

export const PRINT_STYLES: StyleDictionary = {
  courseTitle: { fontSize: 30, bold: true, color: PRINT.heading, lineHeight: 1.1 },
  courseDescription: { fontSize: 12.5, color: PRINT.muted, lineHeight: 1.4, margin: [0, 18, 0, 0] },
  coverMeta: { fontSize: 9.5, color: PRINT.muted, margin: [0, 28, 0, 0] },
  tocTitle: { fontSize: 20, bold: true, color: PRINT.heading, margin: [0, 0, 0, 14] },
  tocBlock: { fontSize: 11.5, bold: true, color: PRINT.heading, margin: [0, 10, 0, 2] },
  tocModule: { fontSize: 10, color: PRINT.ink, margin: [0, 4, 0, 0] },
  tocLesson: { fontSize: 9.5, color: PRINT.muted, margin: [0, 2, 0, 0] },
  blockTitle: { fontSize: 21, bold: true, color: PRINT.primary, margin: [0, 0, 0, 14] },
  moduleTitle: { fontSize: 14.5, bold: true, color: PRINT.heading, margin: [0, 0, 0, 4] },
  moduleSummary: { fontSize: 10, italics: true, color: PRINT.muted, margin: [0, 0, 0, 16] },
  lessonTitle: { fontSize: 17.5, bold: true, color: PRINT.heading, margin: [0, 0, 0, 10] },
  h2: { fontSize: 13, bold: true, color: PRINT.heading, margin: [0, 14, 0, 5] },
  h3: { fontSize: 11.5, bold: true, color: PRINT.heading, margin: [0, 10, 0, 4] },
  h4: { fontSize: 10.5, bold: true, color: PRINT.heading, margin: [0, 8, 0, 3] },
  p: { margin: [0, 0, 0, 7] },
  list: { margin: [10, 0, 0, 8] },
  note: { fontSize: 10 },
  quote: { italics: true, color: PRINT.muted },
  codeBlock: { fontSize: 9.5, color: PRINT.codeText, background: PRINT.codeFill, margin: [0, 4, 0, 8] },
  caption: { fontSize: 9, color: PRINT.muted, margin: [0, 5, 0, 0], lineHeight: 1.3 },
  footer: { fontSize: 8, color: PRINT.muted },
};
