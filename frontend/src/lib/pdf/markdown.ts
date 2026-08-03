import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import remarkDirective from "remark-directive";
import type { Content, ContentText, TableCell } from "pdfmake/interfaces";
import type { PhrasingContent, Root, RootContent, TableContent } from "mdast";
// Type-only import: this is what teaches mdast about `containerDirective` / `leafDirective` nodes.
import type {} from "mdast-util-directive";
import { PRINT, contentWidth } from "@/lib/pdf/page";

/**
 * Lesson markdown -> pdfmake content: the print half of the pair whose screen half is `lib/markdown.tsx`,
 * over the same dialect (GFM + remark-directive, `:::note` callouts, `::figure` leaves).
 *
 * A directive with no print rule renders as nothing, which is how `::exercise` stays out. That is the
 * absence of a rule, not a second implementation of the server-side stripping: nothing here matches on
 * the word "exercise".
 */

const processor = unified().use(remarkParse).use(remarkGfm).use(remarkDirective);

export interface MarkdownRenderers {
  /** MUST throw for an unknown figure: one that cannot be rendered has to fail the export. */
  figure: (figureId: string) => Content;
}

interface Marks {
  bold?: boolean;
  italics?: boolean;
  color?: string;
  background?: string;
  decoration?: "underline" | "lineThrough";
  link?: string;
}

/** A soft break is a space in markdown but a HARD break in pdfmake, so prose wrapped at 110 columns
 *  has to be unwrapped or every source line breaks on the page. */
function unwrap(value: string): string {
  return value.replace(/[ \t]*\n[ \t]*/g, " ");
}

function runs(nodes: PhrasingContent[], marks: Marks = {}): ContentText[] {
  const out: ContentText[] = [];
  for (const node of nodes) {
    switch (node.type) {
      case "text":
        out.push({ text: unwrap(node.value), ...marks });
        break;
      case "strong":
        out.push(...runs(node.children, { ...marks, bold: true }));
        break;
      case "emphasis":
        out.push(...runs(node.children, { ...marks, italics: true }));
        break;
      case "delete":
        out.push(...runs(node.children, { ...marks, decoration: "lineThrough" }));
        break;
      case "inlineCode":
        // The app's tinted chip: it keeps a formula distinct from prose without a second embedded font.
        out.push({
          text: node.value,
          ...marks,
          color: PRINT.codeText,
          background: PRINT.codeFill,
        });
        break;
      case "link":
        out.push(
          ...runs(node.children, {
            ...marks,
            link: node.url,
            color: PRINT.link,
            decoration: "underline",
          }),
        );
        break;
      case "break":
        out.push({ text: "\n", ...marks });
        break;
      case "textDirective":
        out.push(...runs(node.children, marks)); // no print rule for one: drop it, keep its text
        break;
      default:
        if ("children" in node) out.push(...runs(node.children as PhrasingContent[], marks));
        break;
    }
  }
  return out;
}

const HEADING_STYLE = ["lessonTitle", "h2", "h3", "h4", "h4", "h4"] as const;

/** The app's callout: a one-cell table is how pdfmake draws a filled box with a coloured left rule. */
function callout(tone: string, body: Content[]): Content {
  const tones = PRINT.notes[tone] ?? PRINT.notes.info;
  return {
    table: { widths: ["*"], body: [[{ stack: body, fillColor: tones.fill, margin: [8, 7, 8, 7] }]] },
    layout: {
      hLineWidth: () => 0,
      vLineWidth: (i: number) => (i === 0 ? 3 : 0),
      vLineColor: () => tones.border,
      paddingLeft: () => 0,
      paddingRight: () => 0,
      paddingTop: () => 0,
      paddingBottom: () => 0,
    },
    style: "note",
    margin: [0, 6, 0, 8],
  };
}

function listItems(node: Extract<RootContent, { type: "list" }>, r: MarkdownRenderers): Content[] {
  return node.children.map((item) => {
    const [first, ...rest] = item.children;
    // One paragraph is the common shape: emit it as the item's text so the marker hugs the line.
    if (first?.type === "paragraph" && rest.length === 0) return { text: runs(first.children) };
    return { stack: blocks(item.children, r) };
  });
}

function tableRow(row: TableContent, header: boolean): TableCell[] {
  return row.children.map((cell) => ({ text: runs(cell.children), bold: header }));
}

function blocks(nodes: RootContent[], r: MarkdownRenderers): Content[] {
  const out: Content[] = [];
  for (const node of nodes) {
    switch (node.type) {
      case "heading":
        out.push({ text: runs(node.children), style: HEADING_STYLE[node.depth - 1] });
        break;
      case "paragraph":
        out.push({ text: runs(node.children), style: "p" });
        break;
      case "list": {
        const items = listItems(node, r);
        const shared = { style: "list", markerColor: PRINT.marker } as const;
        out.push(node.ordered ? { ol: items, ...shared } : { ul: items, ...shared });
        break;
      }
      case "code":
        out.push({ text: node.value, style: "codeBlock" });
        break;
      case "blockquote":
        out.push({ stack: blocks(node.children, r), style: "quote", margin: [14, 4, 0, 8] });
        break;
      case "thematicBreak":
        out.push({
          canvas: [
            { type: "line", x1: 0, y1: 0, x2: contentWidth(), y2: 0, lineWidth: 0.5, lineColor: PRINT.rule },
          ],
          margin: [0, 8, 0, 12],
        });
        break;
      case "table":
        out.push({
          table: {
            headerRows: 1,
            widths: node.children[0]?.children.map(() => "*") ?? ["*"],
            body: node.children.map((row, i) => tableRow(row, i === 0)),
          },
          layout: {
            hLineWidth: (i: number, t: { table: { body: unknown[] } }) =>
              i === 0 || i === 1 || i === t.table.body.length ? 0.5 : 0.25,
            vLineWidth: () => 0,
            hLineColor: () => PRINT.rule,
          },
          style: "p",
          margin: [0, 4, 0, 10],
        });
        break;
      case "containerDirective":
        if (node.name === "note") {
          out.push(callout(node.attributes?.type ?? "info", blocks(node.children, r)));
        }
        break;
      case "leafDirective":
        if (node.name === "figure") {
          const id = node.attributes?.id;
          if (!id) throw new Error("a ::figure directive has no id");
          out.push(r.figure(id));
        }
        break;
      default:
        break;
    }
  }
  return out;
}

function parseLesson(markdown: string): Root {
  return processor.parse(markdown);
}

/** A lesson's `::figure` ids in reading order; duplicates kept, since a figure may recur. */
export function figureIds(markdown: string): string[] {
  const ids: string[] = [];
  const visit = (nodes: RootContent[]): void => {
    for (const node of nodes) {
      if (node.type === "leafDirective" && node.name === "figure" && node.attributes?.id) {
        ids.push(node.attributes.id);
      } else if ("children" in node) {
        visit(node.children as RootContent[]);
      }
    }
  };
  visit(parseLesson(markdown).children);
  return ids;
}

export function lessonToContent(markdown: string, r: MarkdownRenderers): Content[] {
  return blocks(parseLesson(markdown).children, r);
}
