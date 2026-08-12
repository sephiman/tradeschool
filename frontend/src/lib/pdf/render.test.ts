// @vitest-environment node
// Typesetting is pure bytes in, bytes out: no DOM, and — importantly — node's own Buffer/zlib rather
// than jsdom's realm, where pdfkit's `src instanceof Uint8Array` font check silently fails.
import { describe, expect, it } from "vitest";
import type { NodeQueries, TDocumentDefinitions } from "pdfmake/interfaces";
import type { CourseExport, PrintExercises } from "@/api/course";
import { PRINT_FONTS, buildCourseDocument, type CapturedFigure } from "@/lib/pdf/document";
import { createSectionTracker, type SectionTracker } from "@/lib/pdf/sections";
import {
  MIN_BODY_HEIGHT,
  roomBelow,
  type LayoutNode,
  type OversizedBlock,
} from "@/lib/pdf/pagination";
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
import { testPng } from "@/test/png";
import { printExercisesFromContent, stubExerciseCharts } from "@/test/printExercises";
import { testPdfLabels } from "@/test/printLabels";

/**
 * The whole course, both languages, typeset by pdfmake into a real PDF.
 *
 * Two stand-ins: the figure bitmaps (canvas needs a browser) and the PDF writer. The layout engine,
 * document and pagination are the real ones.
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

/** An exercise chart's stand-in bitmap, the size a real capture produces. */
const STUB_CHART_PNG = testPng(1520, 600);

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

async function generate(
  locale: Locale,
  figures?: Map<string, CapturedFigure>,
  printed?: PrintExercises,
): Promise<Run> {
  const course = readManifest().course;
  const progress: GenerateProgress[] = [];
  const pdfmake = await nodePdfMake();
  const exercises = printed ?? printExercisesFromContent(locale);
  const generated = await generateCoursePdf({
    locale,
    courseId: course.id,
    courseTitle: course.title[locale],
    courseSubtitle: course.subtitle[locale],
    courseDescription: course.description[locale],
    labels: testPdfLabels(locale),
    date: new Date(2026, 7, 3),
    onProgress: (p) => progress.push(p),
    fetchExport: async (lang) => courseExportFromContent(lang as Locale),
    fetchExercises: async () => exercises,
    captureAll: async (ids, onProgress) => {
      onProgress?.({ done: new Set(ids).size, total: new Set(ids).size });
      return figures ?? stubFigures(ids);
    },
    captureCharts: async (charts, onProgress) => {
      onProgress?.({ done: charts.length, total: charts.length });
      return stubExerciseCharts(exercises, STUB_CHART_PNG);
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
  it("is a valid PDF with a page for the cover, the contents, every lesson and the answer key", async () => {
    const { generated, bytes } = await generateOnce(locale);
    expect(new TextDecoder().decode(bytes.subarray(0, 5))).toBe("%PDF-");
    // Cover + contents + at least one page per lesson + at least one for the key at the back.
    expect(pageCount(bytes)).toBeGreaterThanOrEqual(3 + manifestLessons().length);
    expect(generated.blob.size).toBeGreaterThan(50_000);
  }, 300_000);

  it("is named for the course, the language and the day", async () => {
    const { generated } = await generateOnce(locale);
    expect(generated.filename).toBe(`tradeschool-crypto-futures-${locale}-2026-08-03.pdf`);
  }, 300_000);

  it("reports each phase of the work, both capture phases counted", async () => {
    const { progress } = await generateOnce(locale);
    // The two long phases count rather than spin: 29 figures, then 23 exercise charts.
    expect(progress.map((p) => p.phase)).toEqual([
      "export",
      "exercises",
      "figures",
      "figures",
      "charts",
      "charts",
      "typeset",
    ]);
    expect(progress.find((p) => p.phase === "figures" && p.done > 0)?.total).toBe(
      new Set(figureDirectives(locale)).size,
    );
    const charts = printExercisesFromContent(locale)
      .lessons.flatMap((lesson) => lesson.exercises)
      .filter((exercise) => exercise.isChart);
    expect(charts.length).toBeGreaterThan(0);
    expect(progress.find((p) => p.phase === "charts")?.total).toBe(charts.length);
  }, 300_000);

  it("carries no exercise id in its bytes — the book speaks in numbers", async () => {
    // The printed label is `11.5`, derived from `m11-ex-5`; the id itself is a database key and has no
    // business on a page. Ids are ASCII, so one in the metadata or an uncompressed stream shows here.
    // (Which exercises are printed, and that each has exactly one answer, is asserted on the built
    // document in `document.test.ts` — the streams here are compressed, so absence is what bytes can
    // honestly prove.)
    const { bytes } = await generateOnce(locale);
    const text = new TextDecoder("latin1").decode(bytes);
    expect(manifestExerciseIds().filter((id) => text.includes(id))).toEqual([]);
  }, 300_000);

  it("ships a real outline and real link annotations, not just a definition that asks for them", async () => {
    // `navigation.test.ts` proves the document ASKS for these; only the bytes prove pdfmake wrote
    // them. Outline dictionaries and link annotations are objects, so they survive stream compression.
    const { bytes } = await generateOnce(locale);
    const text = new TextDecoder("latin1").decode(bytes);
    expect(text, "no document outline in the file").toContain("/Outlines");
    const bookmarks = [...text.matchAll(/\/Title/g)].length - 1; // the info dictionary carries one too
    const lessons = manifestLessons().length;
    const modules = readManifest().blocks.flatMap((block) => block.modules).length;
    const blocks = readManifest().blocks.length;
    expect(bookmarks).toBeGreaterThanOrEqual(blocks + modules + lessons + 2);
    // The contents alone accounted for ~440 before this batch; terms and the exercise pair add more.
    expect([...text.matchAll(/\/GoTo/g)].length).toBeGreaterThan(600);
  }, 300_000);

  it("grows by the exercises: more pages than the same book without them", async () => {
    const { bytes } = await generateOnce(locale);
    const withoutExercises = await generate(locale, undefined, {
      locale,
      lessons: [],
      excluded: [],
    });
    expect(pageCount(bytes)).toBeGreaterThan(pageCount(withoutExercises.bytes));
  }, 600_000);
});

/**
 * Where the pages actually broke, in the book as it will be printed.
 *
 * Needs a SECOND pass: pdfmake decides each break once, so the enforcing pass only ever sees offenders
 * before they are fixed. The second keeps the inserted breaks, clears the "already decided" flags, and
 * observes every node at its final position.
 */
describe.each(LOCALES)("the printed pages (%s)", (locale) => {
  /** Walk the document's OWN container keys — pdfmake's post-layout internals are cyclic. */
  function walk(node: unknown, visit: (n: Record<string, unknown>) => void): void {
    if (Array.isArray(node)) {
      node.forEach((child) => walk(child, visit));
      return;
    }
    if (typeof node !== "object" || node === null) return;
    const container = node as Record<string, unknown>;
    visit(container);
    for (const key of ["stack", "columns", "ul", "ol", "text"]) walk(container[key], visit);
    const table = container.table as { body?: unknown } | undefined;
    if (table?.body) walk(table.body, visit);
  }

  interface Observed {
    headings: number;
    orphans: string[];
    thin: string[];
    splitCallouts: string[];
    splitFigures: string[];
    callouts: number;
    figures: number;
  }

  async function layout(): Promise<{
    observed: Observed;
    moved: number;
    oversized: OversizedBlock[];
    sections: SectionTracker;
    doc: TDocumentDefinitions;
  }> {
    const pdfmake = await nodePdfMake();
    const exercises = printExercisesFromContent(locale);
    const course = readManifest().course;
    const oversized: OversizedBlock[] = [];
    const sections = createSectionTracker();
    const doc = buildCourseDocument({
      sections,
      courseTitle: course.title[locale],
      courseSubtitle: course.subtitle[locale],
      courseDescription: course.description[locale],
      export: courseExportFromContent(locale),
      figures: stubFigures(figureDirectives(locale)),
      exercises,
      exerciseCharts: stubExerciseCharts(exercises, STUB_CHART_PNG),
      onOversizedBlock: (callout) => oversized.push(callout),
      labels: testPdfLabels(locale),
    }) as TDocumentDefinitions & { pageBreakBefore?: unknown };

    // Pass 1: the real rules, inserting the real breaks.
    await pdfmake.createPdf(doc).getBuffer();

    // Pass 2: same document, same breaks, nothing decided — just watch.
    let cleared = 0;
    walk(doc.content, (n) => {
      if (n.pageBreakCalculated) {
        delete n.pageBreakCalculated;
        cleared++;
      }
    });
    expect(cleared, "pdfmake no longer marks decided nodes; the observation pass is blind").toBeGreaterThan(0);

    const observed: Observed = {
      headings: 0,
      orphans: [],
      thin: [],
      splitCallouts: [],
      splitFigures: [],
      callouts: 0,
      figures: 0,
    };
    const name = (n: LayoutNode) =>
      `p${n.pageNumbers.join("+")} ${String(n.style)} "${
        Array.isArray(n.text)
          ? n.text.map((run) => (run as { text?: string }).text ?? "").join("")
          : String(n.text ?? n.id)
      }"`.slice(0, 90);

    doc.pageBreakBefore = (node: LayoutNode, near: NodeQueries) => {
      const id = typeof node.id === "string" ? node.id : "";
      if (typeof node.headlineLevel === "number") {
        observed.headings++;
        const body = near
          .getFollowingNodesOnPage()
          .filter(
            (f) =>
              f.text !== undefined || f.image !== undefined || f.canvas !== undefined || f.svg !== undefined,
          )
          .filter((f) => f.style !== "footer" && typeof f.headlineLevel !== "number");
        if (body.length === 0) observed.orphans.push(name(node));
        else if (roomBelow(body[0].startPosition) < MIN_BODY_HEIGHT) observed.thin.push(name(node));
      }
      if (id.startsWith("note-") || id.startsWith("answer-")) {
        observed.callouts++;
        if (node.pageNumbers.length > 1) observed.splitCallouts.push(name(node));
      }
      if (id.startsWith("figure-")) {
        observed.figures++;
        if (node.pageNumbers.length > 1) observed.splitFigures.push(name(node));
      }
      return false;
    };
    await pdfmake.createPdf(doc).getBuffer();

    // Everything the rules moved starts a page of its own, so it cannot be stranded — and pdfmake
    // skips those nodes in pass 2, which is why they are counted here instead of observed.
    let moved = 0;
    walk(doc.content, (n) => {
      if (n.pageBreak === "before" && n.lessonId === undefined && n.toc === undefined) moved++;
    });
    return { observed, moved, oversized, sections, doc };
  }

  const laid = layout();

  it("never leaves a heading stranded at the foot of a page", async () => {
    const { observed } = await laid;
    expect(observed.orphans, "headings printed with their body overleaf").toEqual([]);
    expect(observed.thin, "headings printed with barely a line under them").toEqual([]);
  }, 600_000);

  it("prints every callout and every answer-key entry whole", async () => {
    const { observed, oversized } = await laid;
    expect(observed.callouts).toBeGreaterThan(0);
    // A box taller than a page is allowed to break — and must then be named in the report.
    expect(observed.splitCallouts.filter((c) => !oversized.some((o) => c.includes(o.id)))).toEqual([]);
  }, 600_000);

  it("never separates a figure from its caption", async () => {
    const { observed } = await laid;
    expect(observed.figures).toBeGreaterThan(0);
    expect(observed.splitFigures).toEqual([]);
  }, 600_000);

  /** What the running footer prints on the left of a given page. */
  function footerTitle(doc: TDocumentDefinitions, page: number): string {
    const footer = doc.footer as (p: number, count: number) => unknown;
    const drawn = footer(page, 999) as { columns?: { text?: string }[]; text?: string };
    return drawn.columns?.[0]?.text ?? drawn.text ?? "";
  }

  it("names, in the footer, the section each page belongs to", async () => {
    const { sections, doc } = await laid;
    const course = readManifest().course;
    const found = sections.resolved();
    // Every block, then the glossary, then the answer key, in the order the book prints them: a
    // reference you consult while reading comes before the solutions you consult after.
    expect(found.map((s) => s.title)).toEqual([
      ...readManifest().blocks.map((block) => block.title[locale]),
      testPdfLabels(locale).glossary,
      testPdfLabels(locale).answerKey,
    ]);

    found.forEach((section, index) => {
      const next = found[index + 1];
      // The page a section starts on already carries its name...
      expect(footerTitle(doc, section.page), `first page of ${section.title}`).toBe(
        `${course.subtitle[locale]} · ${section.title}`,
      );
      // ...and it keeps it to the last page before the next one begins.
      const last = next ? next.page - 1 : section.page;
      expect(footerTitle(doc, last), `last page of ${section.title}`).toBe(
        `${course.subtitle[locale]} · ${section.title}`,
      );
      // The page before a section starts belongs to whatever came before, never to it.
      expect(footerTitle(doc, section.page - 1)).not.toContain(section.title);
    });
  }, 600_000);

  it("names no section on the cover or the contents", async () => {
    const { sections, doc } = await laid;
    const course = readManifest().course;
    const firstBlockPage = sections.resolved()[0].page;
    expect(firstBlockPage).toBeGreaterThan(1);
    expect(footerTitle(doc, 1)).toBe(""); // the cover carries no footer at all
    for (let page = 2; page < firstBlockPage; page++) {
      expect(footerTitle(doc, page), `page ${page} precedes the first block`).toBe(
        course.subtitle[locale],
      );
    }
  }, 600_000);

  it("accounts for every heading: verified in place, or moved to the top of a page", async () => {
    // The two numbers have to add up, or the observation pass is quietly missing nodes and the
    // assertions above are weaker than they look.
    const { observed, moved } = await laid;
    const doc = buildCourseDocument({
      courseTitle: "T",
      courseSubtitle: "S",
      courseDescription: "D",
      export: courseExportFromContent(locale),
      figures: stubFigures(figureDirectives(locale)),
      exercises: printExercisesFromContent(locale),
      exerciseCharts: stubExerciseCharts(printExercisesFromContent(locale), STUB_CHART_PNG),
      labels: testPdfLabels(locale),
    });
    let declared = 0;
    walk(doc.content, (n) => {
      if (typeof n.headlineLevel === "number") declared++;
    });
    expect(declared).toBeGreaterThan(100);
    expect(observed.headings + moved).toBeGreaterThanOrEqual(declared);
  }, 600_000);
});

describe("pagination in the produced file", () => {
  /** Six one-line lessons: short enough that the page count can only be page breaks. */
  const tiny: CourseExport = {
    locale: "en",
    glossary: [],
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
      courseSubtitle: "S",
      courseDescription: "D",
      labels: testPdfLabels("en"),
      date: new Date(2026, 7, 3),
      fetchExport: async () => tiny,
      fetchExercises: async () => ({ locale: "en", lessons: [], excluded: [] }),
      captureAll: async () => new Map(),
      captureCharts: async () => new Map(),
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
