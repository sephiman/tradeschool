import type { Content, ContentStack, TDocumentDefinitions } from "pdfmake/interfaces";
import type { CourseExport } from "@/api/course";
import { lessonToContent, type MarkdownRenderers } from "@/lib/pdf/markdown";
import { DEFAULT_STYLE, PAGE, PRINT_FONT, PRINT_STYLES, panelWidth } from "@/lib/pdf/page";

/**
 * The course as a print document: a pure function of (course identity, theory export, figure images).
 * No DOM, no network, no i18next — the localized chrome arrives as `labels` — so the whole document is
 * buildable, and assertable, for either locale in a test.
 *
 * The lesson tree comes from `/course/export`, so the PDF is theory-only for the same reason that
 * endpoint is (`registry._theory_only` strips the exercises) and complete for the same reason too.
 */

/** A figure as captured from the app's chart renderer: one PNG per panel, plus its caption. */
export interface CapturedFigure {
  id: string;
  caption: string;
  panels: string[];
}

export interface PdfLabels {
  contents: string;
  /** Cover line naming the language and the day the document was made. */
  generated: string;
  page: (current: number, total: number) => string;
}

export interface BuildCourseDocumentOptions {
  courseTitle: string;
  courseDescription: string;
  export: CourseExport;
  figures: Map<string, CapturedFigure>;
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

export function figureBlocks(doc: TDocumentDefinitions): FigureBlock[] {
  const found: FigureBlock[] = [];
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (typeof node !== "object" || node === null) return;
    if (hasKey(node, "figureId")) found.push(node as unknown as FigureBlock);
    for (const value of Object.values(node)) walk(value);
  };
  walk(doc.content);
  return found;
}

function cover(o: BuildCourseDocumentOptions): Content {
  return {
    stack: [
      { text: o.courseTitle, style: "courseTitle" },
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

export function buildCourseDocument(o: BuildCourseDocumentOptions): TDocumentDefinitions {
  const render = renderers(o.figures);
  const content: Content[] = [cover(o), toc(o)];

  for (const block of o.export.blocks) {
    let blockOpened = false;
    for (const module of block.modules) {
      // Block and module headings open the page their first lesson starts on, rather than taking a
      // mostly empty page of their own: the lesson still begins on a fresh page.
      const opening: Content[] = [];
      if (!blockOpened) {
        opening.push({ text: block.title, style: "blockTitle", tocItem: true, tocStyle: "tocBlock" });
        blockOpened = true;
      }
      opening.push(
        {
          text: `${module.id.toUpperCase()} · ${module.title}`,
          style: "moduleTitle",
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

      module.lessons.forEach((lesson, index) => {
        const body = lessonToContent(lesson.markdown, render);
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
            tocItem: true,
            tocStyle: "tocLesson",
            tocMargin: [24, 0, 0, 0],
          });
        }
        const section: LessonSection = {
          stack: [...(index === 0 ? opening : []), ...body],
          pageBreak: "before",
          lessonId: lesson.id,
        };
        content.push(section);
      });
    }
  }

  return {
    info: {
      title: o.courseTitle,
      subject: o.courseDescription,
      author: "TradeSchool",
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
              { text: o.courseTitle, style: "footer" },
              { text: o.labels.page(currentPage, pageCount), style: "footer", alignment: "right" },
            ],
            margin: [PAGE.margins[0], 18, PAGE.margins[2], 0],
          },
    styles: PRINT_STYLES,
    defaultStyle: DEFAULT_STYLE,
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
