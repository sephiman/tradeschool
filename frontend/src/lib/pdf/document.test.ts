import { describe, expect, it } from "vitest";
import {
  buildCourseDocument,
  figureBlocks,
  lessonSections,
  type CapturedFigure,
  type PdfLabels,
} from "@/lib/pdf/document";
import { figureIds } from "@/lib/pdf/markdown";
import {
  courseExportFromContent,
  figureDirectives,
  manifestExerciseIds,
  manifestLessons,
  manifestModules,
  readManifest,
  stubFigures,
  LOCALES,
  type Locale,
} from "@/test/courseContent";

/**
 * The course PDF checked against the course itself: driven off `content/course.yaml`, no counts and no id
 * literals, like the backend's `test_export_is_complete_against_the_manifest`. A document whose job is to
 * be a faithful copy has one interesting defect — being quietly incomplete.
 */

const labels: PdfLabels = {
  contents: "Contents",
  generated: "English · generated 2026-08-03",
  page: (current, total) => `${current} / ${total}`,
};

// The whole course is parsed to build the document; each locale is built once and shared.
const built = new Map<Locale, ReturnType<typeof buildCourseDocument>>();

function buildFor(locale: Locale) {
  const cached = built.get(locale);
  if (cached) return cached;
  const course = readManifest().course;
  const doc = buildCourseDocument({
    courseTitle: course.title[locale],
    courseDescription: course.description[locale],
    export: courseExportFromContent(locale),
    figures: stubFigures(figureDirectives(locale)),
    labels,
  });
  built.set(locale, doc);
  return doc;
}

/** The visible text of a list of inline runs. */
function texts_(runs: unknown[]): string {
  return runs.map((run) => (run as { text?: string }).text ?? "").join("");
}

/** The text of every entry the table of contents will list at one level, in document order. */
function tocTexts(doc: ReturnType<typeof buildFor>, tocStyle: string): string[] {
  const texts: string[] = [];
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (typeof node !== "object" || node === null) return;
    const entry = node as { tocItem?: unknown; tocStyle?: unknown; text?: unknown };
    if (entry.tocItem === true && entry.tocStyle === tocStyle) {
      // A heading's text is a list of runs (bold/italic spans); a synthesized one is a plain string.
      texts.push(Array.isArray(entry.text) ? texts_(entry.text) : String(entry.text));
    }
    for (const value of Object.values(node)) walk(value);
  };
  walk(doc.content);
  return texts;
}

/** Every string anywhere, style names and ids included, so "nowhere" means nowhere. */
function allStrings(node: unknown, found: string[] = []): string[] {
  if (typeof node === "string") found.push(node);
  else if (Array.isArray(node)) node.forEach((child) => allStrings(child, found));
  else if (typeof node === "object" && node !== null) {
    for (const value of Object.values(node)) allStrings(value, found);
  }
  return found;
}

/** Just the typeset text: the `text` of every node, in document order. */
function texts(node: unknown, found: string[] = []): string[] {
  if (Array.isArray(node)) node.forEach((child) => texts(child, found));
  else if (typeof node === "object" && node !== null) {
    const value = (node as { text?: unknown }).text;
    if (typeof value === "string") found.push(value);
    for (const child of Object.values(node)) if (child !== value) texts(child, found);
  }
  return found;
}

describe.each(LOCALES)("course PDF document (%s)", (locale) => {
  it("carries every lesson the manifest declares, in manifest order, one page group each", () => {
    const doc = buildFor(locale);
    const wanted = manifestLessons().map((lesson) => lesson.id);
    expect(wanted.length).toBeGreaterThan(0);
    // Order is asserted, not just membership: the manifest's order IS the curriculum.
    expect(lessonSections(doc).map((section) => section.lessonId)).toEqual(wanted);
  });

  it("starts every lesson on a new page", () => {
    const doc = buildFor(locale);
    const sections = lessonSections(doc);
    expect(sections.length).toBe(manifestLessons().length);
    for (const section of sections) {
      expect(section.pageBreak, `${section.lessonId} does not start a page`).toBe("before");
    }
  });

  it("holds no exercise directive and no exercise id anywhere", () => {
    const doc = buildFor(locale);
    const text = allStrings(doc).join("\n");
    expect(text).not.toContain("::exercise");
    const leaked = manifestExerciseIds().filter((id) => text.includes(id));
    expect(leaked, "exercise ids reached the PDF").toEqual([]);
  });

  it("draws one figure block per ::figure directive", () => {
    const directives = figureDirectives(locale);
    expect(directives.length).toBeGreaterThan(0);
    const doc = buildFor(locale);
    expect(figureBlocks(doc).map((block) => block.figureId)).toEqual(directives);
  });

  it("opens with a cover and a table of contents, and names every block, module and lesson in it", () => {
    const doc = buildFor(locale);
    const content = doc.content as unknown as Record<string, unknown>[];
    const course = readManifest().course;
    // Cover: course title and description, before anything else.
    expect(texts(content[0])).toEqual([
      course.title[locale],
      course.description[locale],
      labels.generated,
    ]);
    // Then the table of contents, which pdfmake fills — with resolved page numbers — from the
    // `tocItem` entries that follow it.
    expect(content[1]).toMatchObject({ toc: { title: { text: labels.contents } } });

    // Three levels, in order: blocks -> modules -> lessons.
    expect(tocTexts(doc, "tocBlock")).toEqual(
      readManifest().blocks.map((block) => block.title[locale]),
    );
    expect(tocTexts(doc, "tocModule")).toEqual(
      manifestModules().map((module) => `${module.id.toUpperCase()} · ${module.title[locale]}`),
    );
    expect(tocTexts(doc, "tocLesson")).toEqual(
      manifestLessons().map((lesson) => lesson.title[locale]),
    );
  });

  it("includes every module summary as its section heading blurb", () => {
    const doc = buildFor(locale);
    const text = allStrings(doc);
    for (const module of manifestModules()) {
      expect(text, `${module.id} summary missing`).toContain(module.summary[locale]);
      expect(text.some((s) => s.includes(module.title[locale]))).toBe(true);
    }
  });
});

describe("figure layout", () => {
  const single: CapturedFigure = { id: "f1", caption: "one panel", panels: ["a"] };
  const quad: CapturedFigure = { id: "f4", caption: "four panels", panels: ["a", "b", "c", "d"] };

  /** One lesson embedding `embeddedId`, with `rendered` as the captured figures. */
  function build(embeddedId: string, rendered: CapturedFigure[]) {
    return buildCourseDocument({
      courseTitle: "T",
      courseDescription: "D",
      export: {
        locale: "en",
        blocks: [
          {
            id: "b",
            title: "B",
            modules: [
              {
                id: "m",
                title: "M",
                summary: "S",
                lessons: [{ id: "m-l1", title: "L", markdown: `# L\n\n::figure{id=${embeddedId}}\n` }],
              },
            ],
          },
        ],
      },
      figures: new Map(rendered.map((figure) => [figure.id, figure])),
      labels,
    });
  }

  it("prints a single-panel figure full width, and a multi-panel figure two-up", () => {
    const one = figureBlocks(build(single.id, [single]))[0];
    expect(one.stack).toHaveLength(2); // the image, then the caption
    expect(one.stack[0]).toMatchObject({ image: "a", width: 483.28 });
    expect(one.stack[1]).toMatchObject({ text: single.caption, style: "caption" });

    const four = figureBlocks(build(quad.id, [quad]))[0];
    expect(four.stack).toHaveLength(3); // two rows of two, then the caption
    expect(four.stack[0]).toMatchObject({ columns: [{ image: "a" }, { image: "b" }] });
    expect(four.stack[1]).toMatchObject({ columns: [{ image: "c" }, { image: "d" }] });
  });

  it("fails loudly when a figure in the prose was never rendered", () => {
    // A hole where a chart should be is not an acceptable PDF: the prose quotes the numbers it draws.
    expect(() => build(single.id, [{ ...single, id: "other" }])).toThrowError(
      /figure f1 was not rendered/,
    );
  });
});

describe("figure ids read from the prose", () => {
  it("finds them in reading order, including a repeat", () => {
    const markdown = "# T\n\ntext\n\n::figure{id=a}\n\nmore\n\n::figure{id=b}\n\n::figure{id=a}\n";
    expect(figureIds(markdown)).toEqual(["a", "b", "a"]);
  });
});
