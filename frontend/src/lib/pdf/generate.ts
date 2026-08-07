import type { TDocumentDefinitions } from "pdfmake/interfaces";
import {
  getCourseExport,
  getPrintExercises,
  type CourseExport,
  type PrintExercises,
} from "@/api/course";
import { buildCourseDocument, type CapturedFigure, type PdfLabels } from "@/lib/pdf/document";
import { captureExerciseCharts, chartExercises } from "@/lib/pdf/exerciseCharts";
import type { OversizedBlock } from "@/lib/pdf/pagination";
import { captureFigures } from "@/lib/pdf/figures";
import { figureIds } from "@/lib/pdf/markdown";
import { loadPdfMake } from "@/lib/pdf/runtime";

/**
 * Generate the course PDF in the locale being browsed: export + exercises, capture figures and charts
 * off-screen, typeset. Each phase reports progress. Any failure propagates — a partial course is not a
 * smaller PDF, it is a wrong one.
 */

export type GeneratePhase = "export" | "exercises" | "figures" | "charts" | "typeset";

export interface GenerateProgress {
  phase: GeneratePhase;
  /** Work done so far in the counted phases (`figures`, `charts`). */
  done: number;
  total: number;
}

export interface GeneratedPdf {
  blob: Blob;
  filename: string;
}

export interface GenerateCoursePdfOptions {
  locale: string;
  /** For the cover and the filename — the course page already has all three. */
  courseId: string;
  courseTitle: string;
  courseDescription: string;
  labels: PdfLabels;
  /** Injected, never read from the clock in here. */
  date: Date;
  onProgress?: (progress: GenerateProgress) => void;
  /** Reports what could not be printed. Defaults to the console; an exclusion is never silent. */
  onExcluded?: (excluded: PrintExercises["excluded"]) => void;
  /** Reports boxes too tall for any page, which therefore had to break. Defaults to the console. */
  onOversizedBlocks?: (blocks: OversizedBlock[]) => void;
  /** Seams, so the orchestration is testable without a canvas or a server. */
  fetchExport?: (locale: string) => Promise<CourseExport>;
  fetchExercises?: (locale: string) => Promise<PrintExercises>;
  captureAll?: (
    ids: string[],
    onProgress?: (p: { done: number; total: number }) => void,
  ) => Promise<Map<string, CapturedFigure>>;
  captureCharts?: (
    exercises: PrintExercises["lessons"][number]["exercises"],
    onProgress?: (p: { done: number; total: number }) => void,
  ) => Promise<Map<string, string>>;
  /** Tests supply a pdfmake whose font comes off disk; the typesetting is the real thing either way. */
  renderPdf?: (definition: TDocumentDefinitions) => Promise<Blob>;
}

function isoDay(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Course slug + locale + date, so a folder of exports sorts and reads sensibly. */
export function pdfFilename(courseId: string, locale: string, date: Date): string {
  return `tradeschool-${courseId}-${locale}-${isoDay(date)}.pdf`;
}

/** Names the boxes taller than a page. Not a failure — the book is still complete. */
function reportOversized(blocks: OversizedBlock[]): void {
  for (const block of blocks) {
    console.warn(
      `PDF export: ${block.id} (page ${block.page}) is taller than a page and had to break across ` +
        `one. Shorten it, or split it in two.`,
    );
  }
}

/** The default report for what could not be printed: named, one line each, never a silent drop. */
function reportExcluded(excluded: PrintExercises["excluded"]): void {
  for (const item of excluded) {
    console.warn(
      `PDF export: exercise ${item.id} (${item.number}, ${item.type}) in ${item.lessonId} ` +
        `is not in the printed book — ${item.reason}`,
    );
  }
}

export async function generateCoursePdf(o: GenerateCoursePdfOptions): Promise<GeneratedPdf> {
  const fetchExport = o.fetchExport ?? getCourseExport;
  const fetchExercises = o.fetchExercises ?? getPrintExercises;
  const captureAll = o.captureAll ?? captureFigures;
  const captureCharts = o.captureCharts ?? captureExerciseCharts;

  o.onProgress?.({ phase: "export", done: 0, total: 0 });
  const exported = await fetchExport(o.locale);

  o.onProgress?.({ phase: "exercises", done: 0, total: 0 });
  const exercises = await fetchExercises(o.locale);
  (o.onExcluded ?? reportExcluded)(exercises.excluded);

  const ids = exported.blocks.flatMap((block) =>
    block.modules.flatMap((module) => module.lessons.flatMap((lesson) => figureIds(lesson.markdown))),
  );
  o.onProgress?.({ phase: "figures", done: 0, total: new Set(ids).size });
  const figures = await captureAll(ids, ({ done, total }) =>
    o.onProgress?.({ phase: "figures", done, total }),
  );

  const charts = chartExercises(exercises);
  o.onProgress?.({ phase: "charts", done: 0, total: charts.length });
  const exerciseCharts = await captureCharts(charts, ({ done, total }) =>
    o.onProgress?.({ phase: "charts", done, total }),
  );

  o.onProgress?.({ phase: "typeset", done: 0, total: 0 });
  // Filled while the typesetter paginates, so it is only complete once the document is rendered.
  const oversized: OversizedBlock[] = [];
  const definition = buildCourseDocument({
    courseTitle: o.courseTitle,
    courseDescription: o.courseDescription,
    export: exported,
    figures,
    exercises,
    exerciseCharts,
    onOversizedBlock: (block) => oversized.push(block),
    labels: o.labels,
  });

  const renderPdf =
    o.renderPdf ??
    (async (doc: TDocumentDefinitions) => (await loadPdfMake()).createPdf(doc).getBlob());

  // Rendered twice, and the first one is thrown away. The footer names the section a page belongs to,
  // and which page a block starts on is only known once the document has been laid out — so the first
  // render is what resolves that mapping. The second is cheap: every page break is decided by then, so
  // pdfmake lays out once instead of once per inserted break (~54s then ~2s for the Spanish book).
  await renderPdf(definition);
  const blob = await renderPdf(definition);
  if (oversized.length > 0) (o.onOversizedBlocks ?? reportOversized)(oversized);
  return { blob, filename: pdfFilename(o.courseId, o.locale, o.date) };
}

/** Hand the finished document to the browser under its own name. */
export function downloadPdf({ blob, filename }: GeneratedPdf): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
