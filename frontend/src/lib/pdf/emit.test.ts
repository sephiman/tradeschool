// @vitest-environment node
// Not an assertion suite: an opt-in emitter that writes a real PDF to disk for human review.
// Skipped unless EMIT_PDF names an output path, so the normal run is unaffected.
import { writeFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { TDocumentDefinitions } from "pdfmake/interfaces";
import { PRINT_FONTS } from "@/lib/pdf/document";
import { generateCoursePdf } from "@/lib/pdf/generate";
import {
  courseExportFromContent,
  printFontPaths,
  readManifest,
  stubFigures,
  type Locale,
} from "@/test/courseContent";
import { testPng } from "@/test/png";
import { printExercisesFromContent, stubExerciseCharts } from "@/test/printExercises";
import { testPdfLabels } from "@/test/printLabels";

const OUT = process.env.EMIT_PDF;
const LOCALE = (process.env.EMIT_PDF_LOCALE ?? "es") as Locale;

describe.runIf(OUT)("emit a PDF for review", () => {
  it(
    "writes the whole course",
    async () => {
      const pdfmake = (await import("pdfmake")).default;
      const paths = printFontPaths();
      const family = PRINT_FONTS[Object.keys(PRINT_FONTS)[0] as keyof typeof PRINT_FONTS];
      pdfmake.addFonts({
        [Object.keys(PRINT_FONTS)[0]]: Object.fromEntries(
          Object.entries(family).map(([variant, file]) => [variant, paths[file]]),
        ),
      });

      const course = readManifest().course;
      const exercises = printExercisesFromContent(LOCALE);
      const generated = await generateCoursePdf({
        locale: LOCALE,
        courseId: course.id,
        courseTitle: course.title[LOCALE],
        courseSubtitle: course.subtitle[LOCALE],
        courseDescription: course.description[LOCALE],
        labels: testPdfLabels(LOCALE),
        date: new Date(2026, 7, 8),
        fetchExport: async (lang) => courseExportFromContent(lang as Locale),
        fetchExercises: async () => exercises,
        // Figures and exercise charts need a canvas, so these are the same stand-in bitmaps the
        // render suite uses: the prose, the glossary and the pagination are the real ones.
        captureAll: async (ids) => stubFigures(ids),
        captureCharts: async () => stubExerciseCharts(exercises, testPng(1520, 600)),
        renderPdf: async (definition: TDocumentDefinitions) =>
          new Blob([new Uint8Array(await pdfmake.createPdf(definition).getBuffer())], {
            type: "application/pdf",
          }),
      });

      writeFileSync(OUT as string, new Uint8Array(await generated.blob.arrayBuffer()));
      expect(generated.blob.size).toBeGreaterThan(50_000);
    },
    600_000,
  );
});
