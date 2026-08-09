import type { Content, ContentStack, TDocumentDefinitions } from "pdfmake/interfaces";
import type { Root } from "mdast";
import type { CourseExport, GlossaryEntry, PrintExercise, PrintExercises } from "@/api/course";
import { annotateLesson } from "@/lib/glossary/annotate";
import { buildTermIndex } from "@/lib/glossary/terms";
import {
  answerKeySection,
  lessonExercises,
  type AnswerKeyGroup,
  type ExerciseChartLookup,
  type ExerciseLabels,
} from "@/lib/pdf/exercises";
import { glossarySection, type GlossaryLabels } from "@/lib/pdf/glossary";
import { lessonToContent, type MarkdownRenderers } from "@/lib/pdf/markdown";
import { DEST, keepTogether, printedId, withId, type OversizedBlock } from "@/lib/pdf/pagination";
import { createSectionTracker, SECTION_ID, type SectionTracker } from "@/lib/pdf/sections";
import { DEFAULT_STYLE, PAGE, PRINT_FONT, PRINT_STYLES, panelWidth } from "@/lib/pdf/page";

/**
 * The course as a print document: a pure function of (identity, theory export, figures, exercises).
 *
 * No DOM, network or i18next — the localized chrome arrives as `labels` — so either locale is
 * assertable in a test. Two sources joined by id: prose from `/course/export`, exercises from
 * `/course/print/exercises`, whose answers make the key from the same objects.
 */

/** Who the course is by. Not translated; only the label around it, via `labels.author`. */
export const COURSE_AUTHOR = "Juan José Hernández Garrido";

/** A figure as captured from the app's chart renderer: one PNG per panel, plus its caption. */
export interface CapturedFigure {
  id: string;
  caption: string;
  panels: string[];
}

export interface PdfLabels extends ExerciseLabels, GlossaryLabels {
  contents: string;
  /** Cover line crediting the author, label localized around `COURSE_AUTHOR`. */
  author: string;
  /** Cover line naming the language and the day the document was made. */
  generated: string;
  page: (current: number, total: number) => string;
}

export interface BuildCourseDocumentOptions {
  courseTitle: string;
  courseDescription: string;
  export: CourseExport;
  figures: Map<string, CapturedFigure>;
  /** The printed exercises and their answers. Required: there is no exercise-free variant of the book. */
  exercises: PrintExercises;
  /** One captured PNG per chart exercise, keyed by exercise id. */
  exerciseCharts: Map<string, string>;
  /** Called for a box too tall for any page, so the report can name it. Never a failure. */
  onOversizedBlock?: (block: OversizedBlock) => void;
  /** Which page each top-level section starts on, for the footer. Pass one in to read it back. */
  sections?: SectionTracker;
  labels: PdfLabels;
}

/** `lessonId`/`figureId` are not pdfmake properties; the renderer ignores them and the tests use them. */
export interface LessonSection extends ContentStack {
  lessonId: string;
  pageBreak: "before";
}

export interface FigureBlock extends ContentStack {
  figureId: string;
}

function hasKey<K extends string>(node: unknown, key: K): node is Record<K, string> {
  return typeof node === "object" && node !== null && key in node;
}

export function lessonSections(doc: TDocumentDefinitions): LessonSection[] {
  const content = Array.isArray(doc.content) ? doc.content : [doc.content];
  return content.filter((node): node is LessonSection => hasKey(node, "lessonId"));
}

function collect<T>(doc: TDocumentDefinitions, key: string): T[] {
  const found: T[] = [];
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (typeof node !== "object" || node === null) return;
    if (hasKey(node, key)) found.push(node as unknown as T);
    for (const value of Object.values(node)) walk(value);
  };
  walk(doc.content);
  return found;
}

export function figureBlocks(doc: TDocumentDefinitions): FigureBlock[] {
  return collect<FigureBlock>(doc, "figureId");
}

/** Every printed exercise, in document order — the half of the bijection that lives on the page. */
export function exerciseBlocks(doc: TDocumentDefinitions): { exerciseId: string; exerciseNumber: string }[] {
  return collect(doc, "exerciseId");
}

/** Every answer-key entry, in document order — the other half. */
export function answerEntries(doc: TDocumentDefinitions): { answerFor: string; exerciseNumber: string }[] {
  return collect(doc, "answerFor");
}

function cover(o: BuildCourseDocumentOptions): Content {
  return {
    stack: [
      { text: o.courseTitle, style: "courseTitle" },
      { text: o.labels.author, style: "coverMeta" },
      { text: o.courseDescription, style: "courseDescription" },
      { text: o.labels.generated, style: "coverMeta" },
    ],
    margin: [0, 170, 0, 0],
  };
}

function toc(o: BuildCourseDocumentOptions): Content {
  return { toc: { title: { text: o.labels.contents, style: "tocTitle" } }, pageBreak: "before" };
}

/** Panels two-up as in the app, then the caption, kept together on one page. */
function figureContent(figure: CapturedFigure): FigureBlock {
  const perRow = figure.panels.length > 1 ? 2 : 1;
  const width = panelWidth(perRow);
  const rows: Content[] = [];
  for (let i = 0; i < figure.panels.length; i += perRow) {
    const row = figure.panels.slice(i, i + perRow).map((image) => ({ image, width }));
    rows.push(perRow === 1 ? row[0] : { columns: row, columnGap: 10 });
  }
  return {
    stack: [...rows, { text: figure.caption, style: "caption" }],
    margin: [0, 8, 0, 12],
    unbreakable: true,
    figureId: figure.id,
  };
}

function renderers(figures: Map<string, CapturedFigure>): MarkdownRenderers {
  return {
    figure: (id) => {
      const figure = figures.get(id);
      if (!figure) throw new Error(`figure ${id} was not rendered for this export`);
      return figureContent(figure);
    },
  };
}

/** The footer's left side: the book, plus the current section once the first block has started. */
export function runningTitle(courseTitle: string, section: string | undefined): string {
  return section ? `${courseTitle} · ${section}` : courseTitle;
}

/** The captured chart for one exercise, or a stop — a chartless question is unanswerable. */
function exerciseChart(charts: Map<string, string>): ExerciseChartLookup {
  return (exerciseId) => {
    const image = charts.get(exerciseId);
    if (!image) throw new Error(`exercise ${exerciseId}'s chart was not rendered for this export`);
    return image;
  };
}

/**
 * The book's glossary links: one pass over the course in reading order, one shared `marked` set.
 *
 * That shared set IS the PDF's policy — the first occurrence of a term in the whole book claims its
 * slot. Returns null when there is no glossary section to link into, so the book never carries a
 * link to a page it does not print.
 */
function termAnnotator(glossary: GlossaryEntry[], locale: string) {
  if (glossary.length === 0) return null;
  const terms = buildTermIndex(glossary, locale);
  const marked = new Set<string>();
  return (lessonId: string) => (tree: Root) => {
    annotateLesson(tree, { lessonId, terms, marked });
  };
}

export function buildCourseDocument(o: BuildCourseDocumentOptions): TDocumentDefinitions {
  const sections = o.sections ?? createSectionTracker();
  const keepPagesTogether = keepTogether({ onOversizedBlock: o.onOversizedBlock });
  const render = renderers(o.figures);
  const annotator = termAnnotator(o.export.glossary, o.export.locale);
  const chart = exerciseChart(o.exerciseCharts);
  const byLesson = new Map(o.exercises.lessons.map((lesson) => [lesson.lessonId, lesson.exercises]));
  const excludedByLesson = new Map<string, number>();
  for (const exclusion of o.exercises.excluded) {
    excludedByLesson.set(exclusion.lessonId, (excludedByLesson.get(exclusion.lessonId) ?? 0) + 1);
  }
  // The key follows the book: grouped by module, in the order the exercises were printed.
  const keyGroups: AnswerKeyGroup[] = [];
  const content: Content[] = [cover(o), toc(o)];

  for (const block of o.export.blocks) {
    let blockOpened = false;
    for (const module of block.modules) {
      // Block and module headings open the page their first lesson starts on, rather than taking a
      // mostly empty page of their own: the lesson still begins on a fresh page.
      const opening: Content[] = [];
      const moduleTitle = `${module.id.toUpperCase()} · ${module.title}`;
      // The outline nests exactly as the manifest does — block › module › lesson — and each level
      // parents the next by id, so a reader's bookmark pane is the course tree.
      const blockOutlineId = printedId(SECTION_ID, block.id, 0);
      if (!blockOpened) {
        // The block heading opens a top-level section, and the footer names it from here on.
        sections.declare(blockOutlineId, block.title);
        opening.push(
          withId(
            {
              text: block.title,
              style: "blockTitle",
              headlineLevel: 1,
              tocItem: true,
              tocStyle: "tocBlock",
              outline: true,
              outlineExpanded: true,
            },
            blockOutlineId,
          ),
        );
        blockOpened = true;
      }
      opening.push(
        withId(
          {
            text: moduleTitle,
            style: "moduleTitle",
            headlineLevel: 2,
            tocItem: true,
            tocStyle: "tocModule",
            tocMargin: [12, 0, 0, 0],
            outline: true,
            outlineParentId: blockOutlineId,
          },
          DEST.outline(module.id),
        ),
        { text: module.summary, style: "moduleSummary" },
      );

      if (module.lessons.length === 0) {
        // The manifest allows a module with no lesson yet; it still gets its heading.
        content.push({ stack: opening, pageBreak: "before" });
        continue;
      }

      const moduleExercises: PrintExercise[] = [];

      module.lessons.forEach((lesson, index) => {
        const body = lessonToContent(lesson.markdown, render, lesson.id, annotator?.(lesson.id));
        const exercises = byLesson.get(lesson.id) ?? [];
        moduleExercises.push(...exercises);
        // A lesson's prose opens with its own `# title` — the string the manifest carries and the app
        // shows. Promote it to the TOC entry rather than printing the title twice; a body without one
        // falls back to the manifest title, so the TOC is never short an entry.
        //
        // `outlineText` is not optional here: the parsed title is an ARRAY of styled runs, and
        // pdfmake would hand that array to the bookmark as its label.
        const nav = {
          tocItem: true,
          tocStyle: "tocLesson",
          tocMargin: [24, 0, 0, 0],
          outline: true,
          outlineText: lesson.title,
          outlineParentId: DEST.outline(module.id),
          id: DEST.outline(lesson.id),
        };
        const first = body[0] as { style?: string } | undefined;
        if (first?.style === "lessonTitle") {
          Object.assign(first, nav);
        } else {
          body.unshift({ text: lesson.title, style: "lessonTitle", headlineLevel: 1, ...nav });
        }
        const section: LessonSection = {
          stack: [
            ...(index === 0 ? opening : []),
            ...body,
            // The prose is unchanged; the exercises follow it, inside the lesson's own section.
            ...lessonExercises(exercises, excludedByLesson.get(lesson.id) ?? 0, o.labels, chart),
          ],
          pageBreak: "before",
          lessonId: lesson.id,
        };
        content.push(section);
      });

      keyGroups.push({ title: moduleTitle, exercises: moduleExercises });
    }
  }

  // The glossary sits between the course and the answer key: a reference you consult while reading,
  // ahead of the solutions you consult after.
  const glossaryId = printedId(SECTION_ID, "glossary", 0);
  sections.declare(glossaryId, o.labels.glossary);
  const glossary = glossarySection(o.export.glossary, o.export.locale, o.labels, glossaryId);
  if (glossary) content.push(glossary);

  const answerKeyId = printedId(SECTION_ID, "answer-key", 0);
  sections.declare(answerKeyId, o.labels.answerKey);
  const key = answerKeySection(keyGroups, o.labels, answerKeyId);
  if (key) content.push(key);

  return {
    info: {
      title: o.courseTitle,
      subject: o.courseDescription,
      author: COURSE_AUTHOR,
      creator: "TradeSchool",
    },
    pageSize: PAGE.size,
    pageMargins: PAGE.margins,
    content,
    footer: (currentPage: number, pageCount: number) =>
      currentPage === 1 // the cover carries no number; every page after it does
        ? { text: "" }
        : {
            columns: [
              { text: runningTitle(o.courseTitle, sections.at(currentPage)), style: "footer" },
              { text: o.labels.page(currentPage, pageCount), style: "footer", alignment: "right" },
            ],
            margin: [PAGE.margins[0], 18, PAGE.margins[2], 0],
          },
    styles: PRINT_STYLES,
    defaultStyle: DEFAULT_STYLE,
    // Where pages may break: headings stay with their body, callouts print whole. The same hook is
    // pdfmake's only view of a laid-out node, so the footer's section tracking rides along with it.
    pageBreakBefore: (node, near) => {
      sections.observe(node);
      return keepPagesTogether(node, near);
    },
  };
}

/** One family, four variants, resolved from pdfmake's vfs by file name. */
export const PRINT_FONTS = {
  [PRINT_FONT]: {
    normal: "LiberationSans-Regular.ttf",
    bold: "LiberationSans-Bold.ttf",
    italics: "LiberationSans-Italic.ttf",
    bolditalics: "LiberationSans-BoldItalic.ttf",
  },
} as const;
