// @vitest-environment node
// Typesetting is pure bytes in, bytes out: no DOM, and — importantly — node's own Buffer/zlib rather
// than jsdom's realm, where pdfkit's `src instanceof Uint8Array` font check silently fails.
import { describe, expect, it } from "vitest";
import type { TDocumentDefinitions } from "pdfmake/interfaces";
import type { CourseExport } from "@/api/course";
import { PRINT_FONTS, type CapturedFigure } from "@/lib/pdf/document";
import { generateCoursePdf, type GenerateProgress, type GeneratedPdf } from "@/lib/pdf/generate";
import {
  courseExportFromContent,
  figureDirectives,
  manifestExerciseIds,
  manifestLessons,
  printFontPaths,
  readManifest,
  stubFigures,
  LOCALES,
  type Locale,
} from "@/test/courseContent";

/**
 * The whole course, both languages, typeset by pdfmake into a real PDF.
 *
 * Two stand-ins: the figure bitmaps (a canvas needs a browser) and the PDF *writer* — this drives
 * pdfmake's node build, the same layout engine `src/` compiles to for the browser, but writing through
 * node's zlib rather than a polyfill. The document and its pagination are the button's own.
 */

async function nodePdfMake() {
  const pdfmake = (await import("pdfmake")).default;
  pdfmake.addFonts({ [Object.keys(PRINT_FONTS)[0]]: mapFontsToPaths() });
  return pdfmake;
}

/** The four variants the browser resolves out of the vfs, as paths on disk. */
function mapFontsToPaths(): Record<string, string> {
  const paths = printFontPaths();
  const family = PRINT_FONTS[Object.keys(PRINT_FONTS)[0] as keyof typeof PRINT_FONTS];
  return Object.fromEntries(Object.entries(family).map(([variant, file]) => [variant, paths[file]]));
}

/** The page count PDF readers use: the root page tree's `/Count`. */
function pageCount(bytes: Uint8Array): number {
  const text = new TextDecoder("latin1").decode(bytes);
  const counts = [...text.matchAll(/\/Count (\d+)/g)].map((m) => Number(m[1]));
  expect(counts.length, "no page tree in the PDF").toBeGreaterThan(0);
  return Math.max(...counts);
}

interface Run {
  generated: GeneratedPdf;
  progress: GenerateProgress[];
  bytes: Uint8Array;
}

async function generate(locale: Locale, figures?: Map<string, CapturedFigure>): Promise<Run> {
  const course = readManifest().course;
  const progress: GenerateProgress[] = [];
  const pdfmake = await nodePdfMake();
  const generated = await generateCoursePdf({
    locale,
    courseId: course.id,
    courseTitle: course.title[locale],
    courseDescription: course.description[locale],
    labels: {
      contents: "Contents",
      generated: "generated 2026-08-03",
      page: (current, total) => `${current} / ${total}`,
    },
    date: new Date(2026, 7, 3),
    onProgress: (p) => progress.push(p),
    fetchExport: async (lang) => courseExportFromContent(lang as Locale),
    captureAll: async (ids, onProgress) => {
      onProgress?.({ done: new Set(ids).size, total: new Set(ids).size });
      return figures ?? stubFigures(ids);
    },
    renderPdf: async (definition: TDocumentDefinitions) =>
      new Blob([new Uint8Array(await pdfmake.createPdf(definition).getBuffer())], {
        type: "application/pdf",
      }),
  });
  return {
    generated,
    progress,
    bytes: new Uint8Array(await generated.blob.arrayBuffer()),
  };
}

// Typesetting the whole course is the expensive part, so each language is generated once and every
// assertion below reads the same document.
const runs = new Map<Locale, Promise<Run>>();
function generateOnce(locale: Locale): Promise<Run> {
  const existing = runs.get(locale);
  if (existing) return existing;
  const run = generate(locale);
  runs.set(locale, run);
  return run;
}

describe.each(LOCALES)("the generated PDF (%s)", (locale) => {
  it("is a valid PDF with a page for the cover, the contents and every lesson", async () => {
    const { generated, bytes } = await generateOnce(locale);
    expect(new TextDecoder().decode(bytes.subarray(0, 5))).toBe("%PDF-");
    // Cover + contents + at least one page per lesson, because every lesson starts a new one.
    expect(pageCount(bytes)).toBeGreaterThanOrEqual(2 + manifestLessons().length);
    expect(generated.blob.size).toBeGreaterThan(50_000);
  }, 300_000);

  it("is named for the course, the language and the day", async () => {
    const { generated } = await generateOnce(locale);
    expect(generated.filename).toBe(`tradeschool-crypto-futures-${locale}-2026-08-03.pdf`);
  }, 300_000);

  it("reports each phase of the work, figures included", async () => {
    const { progress } = await generateOnce(locale);
    expect(progress.map((p) => p.phase)).toEqual(["export", "figures", "figures", "typeset"]);
    expect(progress.find((p) => p.phase === "figures" && p.done > 0)?.total).toBe(
      new Set(figureDirectives(locale)).size,
    );
  }, 300_000);

  it("carries no exercise id in its bytes", async () => {
    // Belt and braces: exercise ids are ASCII, so one in metadata or an uncompressed stream shows here.
    const { bytes } = await generateOnce(locale);
    const text = new TextDecoder("latin1").decode(bytes);
    expect(manifestExerciseIds().filter((id) => text.includes(id))).toEqual([]);
  }, 300_000);
});

describe("pagination in the produced file", () => {
  /** Six one-line lessons: short enough that the page count can only be page breaks. */
  const tiny: CourseExport = {
    locale: "en",
    blocks: [
      {
        id: "b",
        title: "Block",
        modules: Array.from({ length: 6 }, (_, i) => ({
          id: `m0${i + 1}`,
          title: `Module ${i + 1}`,
          summary: "One line of summary.",
          lessons: [{ id: `m0${i + 1}-l1`, title: `Lesson ${i + 1}`, markdown: `# Lesson ${i + 1}\n\nOne line.\n` }],
        })),
      },
    ],
  };

  it("gives every lesson a page of its own, however short the lesson is", async () => {
    const pdfmake = await nodePdfMake();
    const { blob } = await generateCoursePdf({
      locale: "en",
      courseId: "tiny",
      courseTitle: "T",
      courseDescription: "D",
      labels: { contents: "Contents", generated: "g", page: (c, t) => `${c} / ${t}` },
      date: new Date(2026, 7, 3),
      fetchExport: async () => tiny,
      captureAll: async () => new Map(),
      renderPdf: async (definition) =>
        new Blob([new Uint8Array(await pdfmake.createPdf(definition).getBuffer())]),
    });
    // Exactly: six one-line lessons would otherwise share one page, which is why this is a count and
    // not a lower bound.
    expect(pageCount(new Uint8Array(await blob.arrayBuffer()))).toBe(2 + tiny.blocks[0].modules.length);
  }, 300_000);
});

describe("the generated PDF", () => {
  it("stops with the figure named when one could not be drawn", async () => {
    const ids = figureDirectives("en");
    const incomplete = stubFigures(ids);
    const dropped = ids[0];
    incomplete.delete(dropped);
    await expect(generate("en", incomplete)).rejects.toThrowError(
      new RegExp(`figure ${dropped} was not rendered`),
    );
  }, 300_000);
});
