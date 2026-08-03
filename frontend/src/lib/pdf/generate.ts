import type { TDocumentDefinitions } from "pdfmake/interfaces";
import { getCourseExport, type CourseExport } from "@/api/course";
import { buildCourseDocument, type CapturedFigure, type PdfLabels } from "@/lib/pdf/document";
import { captureFigures } from "@/lib/pdf/figures";
import { figureIds } from "@/lib/pdf/markdown";
import { loadPdfMake } from "@/lib/pdf/runtime";

/**
 * Generate the course PDF in the locale being browsed: pull the theory export, draw every figure
 * off-screen, typeset. Each phase is reported so the button can say what is taking the time. Any failure
 * propagates — a partial course is not a smaller PDF, it is a wrong one.
 */

export type GeneratePhase = "export" | "figures" | "typeset";

export interface GenerateProgress {
  phase: GeneratePhase;
  /** Figures drawn so far, during the `figures` phase. */
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
  /** Seams, so the orchestration is testable without a canvas or a server. */
  fetchExport?: (locale: string) => Promise<CourseExport>;
  captureAll?: (
    ids: string[],
    onProgress?: (p: { done: number; total: number }) => void,
  ) => Promise<Map<string, CapturedFigure>>;
  /** Tests supply a pdfmake whose font comes off disk; the typesetting is the real thing either way. */
  renderPdf?: (definition: TDocumentDefinitions) => Promise<Blob>;
}

function isoDay(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Course slug + locale + date, so a folder of exports sorts by course and reads by language and day. */
export function pdfFilename(courseId: string, locale: string, date: Date): string {
  return `tradeschool-${courseId}-${locale}-${isoDay(date)}.pdf`;
}

export async function generateCoursePdf(o: GenerateCoursePdfOptions): Promise<GeneratedPdf> {
  const fetchExport = o.fetchExport ?? getCourseExport;
  const captureAll = o.captureAll ?? captureFigures;

  o.onProgress?.({ phase: "export", done: 0, total: 0 });
  const exported = await fetchExport(o.locale);

  const ids = exported.blocks.flatMap((block) =>
    block.modules.flatMap((module) => module.lessons.flatMap((lesson) => figureIds(lesson.markdown))),
  );
  o.onProgress?.({ phase: "figures", done: 0, total: new Set(ids).size });
  const figures = await captureAll(ids, ({ done, total }) =>
    o.onProgress?.({ phase: "figures", done, total }),
  );

  o.onProgress?.({ phase: "typeset", done: 0, total: 0 });
  const definition = buildCourseDocument({
    courseTitle: o.courseTitle,
    courseDescription: o.courseDescription,
    export: exported,
    figures,
    labels: o.labels,
  });

  const renderPdf =
    o.renderPdf ??
    (async (doc: TDocumentDefinitions) => (await loadPdfMake()).createPdf(doc).getBlob());
  return {
    blob: await renderPdf(definition),
    filename: pdfFilename(o.courseId, o.locale, o.date),
  };
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
