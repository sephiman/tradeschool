import type { Content, ContentStack, TDocumentDefinitions } from "pdfmake/interfaces";
import type { CourseExport, PrintExercise, PrintExercises } from "@/api/course";
import {
  answerKeySection,
  lessonExercises,
  type AnswerKeyGroup,
  type ExerciseChartLookup,
  type ExerciseLabels,
} from "@/lib/pdf/exercises";
import { lessonToContent, type MarkdownRenderers } from "@/lib/pdf/markdown";
import { keepTogether, printedId, withId, type OversizedBlock } from "@/lib/pdf/pagination";
import { createSectionTracker, SECTION_ID, type SectionTracker } from "@/lib/pdf/sections";
import { DEFAULT_STYLE, PAGE, PRINT_FONT, PRINT_STYLES, panelWidth } from "@/lib/pdf/page";

/**
 * The course as a print document: a pure function of (course identity, theory export, figure images,
 * printed exercises). No DOM, no network, no i18next — the localized chrome arrives as `labels` — so
 * the whole document is buildable, and assertable, for either locale in a test.
 *
 * Two sources, joined by id. The lesson tree comes from `/course/export`, which is prose only
 * (`registry._theory_only` strips the `::exercise` directives server-side); the exercises come from
 * `/course/print/exercises`, one frozen instance each, and are printed after the prose of the lesson
 * they belong to. Their answers make the key at the back — built from the same objects, so an
 * exercise and its answer cannot come from different instances.
 */

/** Who the course is by. Not translated — a name is a name — so the localized part is only the label
 *  around it, which arrives through `labels.author`. */
export const COURSE_AUTHOR = "Juan José Hernández Garrido";

/** A figure as captured from the app's chart renderer: one PNG per panel, plus its caption. */
export interface CapturedFigure {
  id: string;
  caption: string;
  panels: string[];
}

export interface PdfLabels extends ExerciseLabels {
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
  /** Called for a box too tall to fit on any page, so the report can name it. Such a box has to
   *  break somewhere; it is reported, never a failure. */
  onOversizedBlock?: (block: OversizedBlock) => void;
  /** Collects which page each top-level section starts on, for the running footer. Pass one in to
   *  read the mapping back after rendering; otherwise the document keeps its own. */
  sections?: SectionTracker;
  labels: PdfLabels;
}

/** `lessonId` and `figureId` are not pdfmake properties — the renderer ignores them, and they are what
 *  let the tests check "every lesson starts a page" and "one block per figure" on the document itself. */
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

/** What the footer prints on the left: the book, and — once the first block has started — where in it
 *  the reader is. Before that (cover, contents) there is no section, and it reads as it always did. */
export function runningTitle(courseTitle: string, section: string | undefined): string {
  return section ? `${courseTitle} · ${section}` : courseTitle;
}

/** The captured chart for one exercise, or a stop: a question printed without its chart is unanswerable
 *  — the same rule a lesson figure follows, for the same reason. */
function exerciseChart(charts: Map<string, string>): ExerciseChartLookup {
  return (exerciseId) => {
    const image = charts.get(exerciseId);
    if (!image) throw new Error(`exercise ${exerciseId}'s chart was not rendered for this export`);
    return image;
  };
}

export function buildCourseDocument(o: BuildCourseDocumentOptions): TDocumentDefinitions {
  const sections = o.sections ?? createSectionTracker();
  const keepPagesTogether = keepTogether({ onOversizedBlock: o.onOversizedBlock });
  const render = renderers(o.figures);
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
      if (!blockOpened) {
        // The block heading opens a top-level section, and the footer names it from here on.
        const sectionId = printedId(SECTION_ID, block.id, 0);
        sections.declare(sectionId, block.title);
        opening.push(
          withId(
            {
              text: block.title,
              style: "blockTitle",
              headlineLevel: 1,
              tocItem: true,
              tocStyle: "tocBlock",
            },
            sectionId,
          ),
        );
        blockOpened = true;
      }
      opening.push(
        {
          text: moduleTitle,
          style: "moduleTitle",
          headlineLevel: 2,
          tocItem: true,
          tocStyle: "tocModule",
          tocMargin: [12, 0, 0, 0],
        },
        { text: module.summary, style: "moduleSummary" },
      );

      if (module.lessons.length === 0) {
        // The manifest allows a module with no lesson yet; it still gets its heading.
        content.push({ stack: opening, pageBreak: "before" });
        continue;
      }

      const moduleExercises: PrintExercise[] = [];

      module.lessons.forEach((lesson, index) => {
        const body = lessonToContent(lesson.markdown, render, lesson.id);
        const exercises = byLesson.get(lesson.id) ?? [];
        moduleExercises.push(...exercises);
        // A lesson's prose opens with its own `# title` — the string the manifest carries and the app
        // shows. Promote it to the TOC entry rather than printing the title twice; a body without one
        // falls back to the manifest title, so the TOC is never short an entry.
        const first = body[0] as { style?: string } | undefined;
        if (first?.style === "lessonTitle") {
          Object.assign(first, { tocItem: true, tocStyle: "tocLesson", tocMargin: [24, 0, 0, 0] });
        } else {
          body.unshift({
            text: lesson.title,
            style: "lessonTitle",
            headlineLevel: 1,
            tocItem: true,
            tocStyle: "tocLesson",
            tocMargin: [24, 0, 0, 0],
          });
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
