import { describe, expect, it } from "vitest";
import type { TDocumentDefinitions } from "pdfmake/interfaces";
import {
  COURSE_AUTHOR,
  answerEntries,
  buildCourseDocument,
  exerciseBlocks,
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
import { printExercisesFromContent, stubExerciseCharts } from "@/test/printExercises";
import { testPdfLabels } from "@/test/printLabels";

/**
 * The course PDF checked against the course itself: driven off `content/course.yaml`, no counts and no id
 * literals, like the backend's `test_export_is_complete_against_the_manifest`. A document whose job is to
 * be a faithful copy has one interesting defect — being quietly incomplete.
 *
 * With exercises in the book that defect has a second half: a question printed with no answer at the
 * back, or an answer whose question is not in the book. Both are checked as a bijection below.
 */

const labels: PdfLabels = testPdfLabels("en");

// The whole course is parsed to build the document; each locale is built once and shared.
const built = new Map<Locale, ReturnType<typeof buildCourseDocument>>();

function buildFor(locale: Locale) {
  const cached = built.get(locale);
  if (cached) return cached;
  const exercises = printExercisesFromContent(locale);
  const course = readManifest().course;
  const doc = buildCourseDocument({
    courseTitle: course.title[locale],
    courseDescription: course.description[locale],
    export: courseExportFromContent(locale),
    figures: stubFigures(figureDirectives(locale)),
    exercises,
    exerciseCharts: stubExerciseCharts(exercises, "png"),
    labels: testPdfLabels(locale),
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

  it("prints every exercise the course declares, in course order, each inside its own lesson", () => {
    const doc = buildFor(locale);
    const wanted = manifestExerciseIds();
    expect(wanted.length).toBeGreaterThan(0);
    // Ids AND order: the manifest's order is the order the book asks its questions in.
    expect(exerciseBlocks(doc).map((block) => block.exerciseId)).toEqual(wanted);

    // Each one inside the section of the lesson that declares it, after that lesson's prose.
    const sections = lessonSections(doc);
    for (const lesson of manifestLessons()) {
      const section = sections.find((s) => s.lessonId === lesson.id);
      expect(section, `${lesson.id} has no section`).toBeDefined();
      const inSection = exerciseBlocks({ content: [section!] } as TDocumentDefinitions).map((b) => b.exerciseId);
      expect(inSection).toEqual((lesson.exercises ?? []).map((exercise) => exercise.id));
    }
  });

  it("answers every printed exercise exactly once, and answers nothing else", () => {
    const doc = buildFor(locale);
    const printed = exerciseBlocks(doc);
    const answers = answerEntries(doc);
    // A bijection, asserted in both directions and on the label a reader navigates by.
    expect(answers.map((entry) => entry.answerFor)).toEqual(printed.map((block) => block.exerciseId));
    expect(answers.map((entry) => entry.exerciseNumber)).toEqual(
      printed.map((block) => block.exerciseNumber),
    );
    const numbers = printed.map((block) => block.exerciseNumber);
    expect(new Set(numbers).size, "two exercises share a number").toBe(numbers.length);
  });

  it("credits the author on the cover and in the document's metadata", () => {
    const doc = buildFor(locale);
    const cover = texts((doc.content as unknown[])[0]).join(" ");
    // The name is not translated; the label around it is.
    expect(cover).toContain(COURSE_AUTHOR);
    expect(cover).toContain(locale === "es" ? "Autor:" : "Author:");
    // Metadata carries the plain name, not the labelled line: it is a field, not a sentence.
    expect(doc.info?.author).toBe(COURSE_AUTHOR);
  });

  it("still renders the ::exercise directive as nothing, so the prose is unchanged", () => {
    // The exercises on the page come from the print export, never from a directive in the markdown:
    // the fixture feeds RAW lesson files (directives and all) where production strips them upstream.
    const doc = buildFor(locale);
    expect(allStrings(doc).join("\n")).not.toContain("::exercise");
  });

  it("draws one figure block per ::figure directive", () => {
    const directives = figureDirectives(locale);
    expect(directives.length).toBeGreaterThan(0);
    const doc = buildFor(locale);
    expect(figureBlocks(doc).map((block) => block.figureId)).toEqual(directives);
  });

  it("opens with a cover and a table of contents, and names every block, module and lesson in it", () => {
    const doc = buildFor(locale);
    const localized = testPdfLabels(locale);
    const content = doc.content as unknown as Record<string, unknown>[];
    const course = readManifest().course;
    // Cover: course title, who wrote it, and the description, before anything else.
    expect(texts(content[0])).toEqual([
      course.title[locale],
      localized.author,
      course.description[locale],
      localized.generated,
    ]);
    // Then the table of contents, which pdfmake fills — with resolved page numbers — from the
    // `tocItem` entries that follow it.
    expect(content[1]).toMatchObject({ toc: { title: { text: localized.contents } } });

    // Three levels, in order: blocks -> modules -> lessons, then the answer key at the same level as
    // a block — one entry, with a page number, for the back of the book.
    expect(tocTexts(doc, "tocBlock")).toEqual([
      ...readManifest().blocks.map((block) => block.title[locale]),
      localized.answerKey,
    ]);
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
      exercises: { locale: "en", lessons: [], excluded: [] },
      exerciseCharts: new Map(),
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

describe.each(LOCALES)("the answer key (%s)", (locale) => {
  it("is a table-of-contents entry of its own, so it resolves to a page number", () => {
    const doc = buildFor(locale);
    // pdfmake fills the `toc` block from the `tocItem` entries; a block-level entry is how the key
    // gets a resolved page number rather than a reader hunting for the back of the book.
    expect(tocTexts(doc, "tocBlock")).toContain(testPdfLabels(locale).answerKey);
  });

  it("starts on its own page, after the last lesson", () => {
    const doc = buildFor(locale);
    const content = doc.content as unknown as Record<string, unknown>[];
    const last = content[content.length - 1];
    expect(last).toMatchObject({ pageBreak: "before" });
    expect(answerEntries({ content: [last] } as unknown as TDocumentDefinitions).length).toBe(
      exerciseBlocks(doc).length,
    );
  });

  it("quotes, for a chart answer, the prices of the chart that was printed", () => {
    const exercises = printExercisesFromContent(locale);
    const chartExercise = exercises.lessons.flatMap((l) => l.exercises).find((e) => e.isChart);
    expect(chartExercise, "no chart exercise in the course").toBeDefined();
    const doc = buildFor(locale);
    const entry = answerEntries(doc).find((e) => e.answerFor === chartExercise!.id);
    const text = allStrings(entry).join(" ");
    // Recomputed from the PAYLOAD, not read back from the answer: a renderer that printed a rounded,
    // re-derived or generic number would pass an equality against its own input, and fail here.
    for (const anchor of chartExercise!.answer.anchors ?? []) {
      const series = chartExercise!.payload.series!;
      const column = anchor.kind === "high" ? series.high : series.low;
      expect(text, `${chartExercise!.id} does not quote its own chart`).toContain(
        column[anchor.index].toFixed(2),
      );
    }
  });

  it("cites the printed option, by the letter the page gave it", () => {
    const exercises = printExercisesFromContent(locale);
    const quiz = exercises.lessons
      .flatMap((l) => l.exercises)
      .find((e) => e.answer.kind === "single_choice");
    expect(quiz).toBeDefined();
    const doc = buildFor(locale);
    const entry = answerEntries(doc).find((e) => e.answerFor === quiz!.id);
    const options = quiz!.payload.options ?? [];
    const index = options.findIndex((option) => option.id === quiz!.answer.optionIds?.[0]);
    const letters = "abcdefghijklmnopqrstuvwxyz";
    const text = allStrings(entry).join(" ");
    expect(text).toContain(`${letters[index]})`);
    expect(text).toContain(options[index].text);
  });
});

describe("generating the same book twice", () => {
  it("prints byte-identical exercises and answers", () => {
    // The instances are frozen server-side (a seed derived from the exercise id); what is checked here
    // is that the renderer adds no drift of its own — no re-shuffle, no clock, no `Math.random`.
    const locale: Locale = "en";
    const course = readManifest().course;
    const build = () => {
      const exercises = printExercisesFromContent(locale);
      return buildCourseDocument({
        courseTitle: course.title[locale],
        courseDescription: course.description[locale],
        export: courseExportFromContent(locale),
        figures: stubFigures(figureDirectives(locale)),
        exercises,
        exerciseCharts: stubExerciseCharts(exercises, "png"),
        labels: testPdfLabels(locale),
      });
    };
    const [first, second] = [build(), build()];
    const exercisesOf = (doc: ReturnType<typeof build>) =>
      JSON.stringify(exerciseBlocks(doc)) + JSON.stringify(answerEntries(doc));
    expect(exercisesOf(first)).toBe(exercisesOf(second));
  });
});

describe("exercises that could not be printed", () => {
  const locale: Locale = "en";
  const labels = testPdfLabels(locale);

  function buildWith(exclude: Record<string, string>) {
    const exercises = printExercisesFromContent(locale, exclude);
    const course = readManifest().course;
    return {
      exercises,
      doc: buildCourseDocument({
        courseTitle: course.title[locale],
        courseDescription: course.description[locale],
        export: courseExportFromContent(locale),
        figures: stubFigures(figureDirectives(locale)),
        exercises,
        exerciseCharts: stubExerciseCharts(exercises, "png"),
        labels,
      }),
    };
  }

  it("says so in the lesson, and leaves them out of the book and the key", () => {
    const dropped = manifestExerciseIds()[0];
    const { exercises, doc } = buildWith({ [dropped]: "declared in the manifest but not authored yet" });
    const lessonId = exercises.excluded[0].lessonId;

    expect(exerciseBlocks(doc).map((b) => b.exerciseId)).not.toContain(dropped);
    expect(answerEntries(doc).map((e) => e.answerFor)).not.toContain(dropped);
    // The bijection survives an exclusion — that is the point of excluding it from both halves.
    expect(answerEntries(doc).map((e) => e.answerFor)).toEqual(
      exerciseBlocks(doc).map((b) => b.exerciseId),
    );

    const section = lessonSections(doc).find((s) => s.lessonId === lessonId);
    expect(allStrings(section)).toContain(labels.excluded(1));
  });

  it("prints no note at all in a lesson that lost nothing", () => {
    const { doc } = buildWith({});
    expect(allStrings(doc).join("\n")).not.toContain(labels.excluded(1));
    expect(allStrings(doc).join("\n")).not.toContain(labels.excluded(2));
  });
});

describe("a chart exercise with no chart", () => {
  it("stops the export, naming the exercise", () => {
    const locale: Locale = "en";
    const exercises = printExercisesFromContent(locale);
    const charts = stubExerciseCharts(exercises, "png");
    const dropped = [...charts.keys()][0];
    charts.delete(dropped);
    const course = readManifest().course;
    // Same rule as a missing figure: a question printed without its chart cannot be answered, and an
    // answer key entry for it would be worse than no book.
    expect(() =>
      buildCourseDocument({
        courseTitle: course.title[locale],
        courseDescription: course.description[locale],
        export: courseExportFromContent(locale),
        figures: stubFigures(figureDirectives(locale)),
        exercises,
        exerciseCharts: charts,
        labels: testPdfLabels(locale),
      }),
    ).toThrowError(new RegExp(`exercise ${dropped}'s chart was not rendered`));
  });
});

describe("figure ids read from the prose", () => {
  it("finds them in reading order, including a repeat", () => {
    const markdown = "# T\n\ntext\n\n::figure{id=a}\n\nmore\n\n::figure{id=b}\n\n::figure{id=a}\n";
    expect(figureIds(markdown)).toEqual(["a", "b", "a"]);
  });
});
