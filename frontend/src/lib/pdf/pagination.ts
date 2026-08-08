import type { Node, NodeQueries, NodeStartPosition } from "pdfmake/interfaces";
import { DEFAULT_STYLE } from "@/lib/pdf/page";

/**
 * Where the book may break pages: a heading keeps 2 body lines, a callout prints whole.
 *
 * Uses `pageBreakBefore`, never `unbreakable: true` — the latter TRUNCATES a block taller than a page
 * rather than overflowing it, silently losing paragraphs.
 */

/** A laid-out node. pdfmake hands the callback a COPY of a property whitelist — no custom marker
 *  survives from the document definition. */
export type LayoutNode = Node;

/** Ids of the blocks that must print whole: a `:::note` box, an answer-key entry, a glossary entry. */
export const CALLOUT_ID = "note";
export const ANSWER_ID = "answer";
/** A glossary entry is a term and its definition; splitting one across a page orphans the term. */
export const GLOSSARY_ENTRY_ID = "glossaryterm";
const KEEP_WHOLE = [CALLOUT_ID, ANSWER_ID, GLOSSARY_ENTRY_ID];
/** Ids that mark a figure block. Only used to make the "never split from its caption" rule checkable. */
export const FIGURE_ID = "figure";

/** `<kind>-<source>-<ordinal>`, unique across the document — pdfmake throws on a duplicate id. */
export function printedId(kind: string, source: string, ordinal: number): string {
  return `${kind}-${source}-${ordinal}`;
}

/** pdfmake accepts `id` on any node, but `@types/pdfmake` declares it only on the table of contents.
 *  The gap is cast here once rather than at every call site. */
export function withId<T extends object>(content: T, id: string): T & { id: string } {
  return { ...content, id };
}

/** How much body a heading has to keep on its page. */
const MIN_BODY_LINES = 2;
const LINE_HEIGHT = (DEFAULT_STYLE.fontSize ?? 10.5) * (DEFAULT_STYLE.lineHeight ?? 1.35);
export const MIN_BODY_HEIGHT = MIN_BODY_LINES * LINE_HEIGHT;

/** A block that could not be kept whole because it is taller than the page itself. */
export interface OversizedBlock {
  id: string;
  /** The page its first fragment landed on — where a reviewer will find it. */
  page: number;
}

/** The node's style NAMES; inline style objects are ignored, as this document never uses them. */
function styleNames(node: LayoutNode): string[] {
  const style = node.style;
  if (typeof style === "string") return [style];
  if (Array.isArray(style)) return style.filter((entry): entry is string => typeof entry === "string");
  return [];
}

/** Does this node put ink on the page, or is it a container whose children do?
 *
 *  Load-bearing: pdfmake records a container's position where layout ENTERS it, not where its content
 *  lands, so a container can claim a page its content left. */
function draws(node: LayoutNode): boolean {
  return (
    node.text !== undefined ||
    node.image !== undefined ||
    node.canvas !== undefined ||
    node.svg !== undefined ||
    node.qr !== undefined
  );
}

/** The running footer lands in every page's "following nodes", making every heading look accompanied. */
function isFooter(node: LayoutNode): boolean {
  return styleNames(node).includes("footer");
}

function isHeading(node: LayoutNode): boolean {
  return typeof node.headlineLevel === "number";
}

function hasId(node: LayoutNode, kind: string): boolean {
  return typeof node.id === "string" && node.id.startsWith(`${kind}-`);
}

/** A block the rules print whole, or move, or (if taller than a page) report. */
export function isKeepWhole(node: LayoutNode): boolean {
  return KEEP_WHOLE.some((kind) => hasId(node, kind));
}

/** Room left on the page below where this node starts. */
export function roomBelow(position: NodeStartPosition): number {
  return position.pageInnerHeight * (1 - position.verticalRatio);
}

/** What stays on this page under this heading once the keep-whole rule has had its say.
 *
 *  A page-spanning box is about to move and takes its inner paragraphs — the ink-carrying nodes — too. */
function bodyBelow(surrounding: NodeQueries): LayoutNode[] {
  const following = surrounding.getFollowingNodesOnPage();
  const leaving = following.findIndex((node) => isKeepWhole(node) && node.pageNumbers.length > 1);
  const staying = leaving === -1 ? following : following.slice(0, leaving);
  return staying.filter((node) => draws(node) && !isFooter(node) && !isHeading(node));
}

export interface KeepTogetherOptions {
  /** Called once per block taller than a page, so the report can name it. Never a failure. */
  onOversizedBlock?: (block: OversizedBlock) => void;
}

/** The document's `pageBreakBefore`. Returns true to push the node to the next page. */
export function keepTogether(options: KeepTogetherOptions = {}): (
  node: LayoutNode,
  surrounding: NodeQueries,
) => boolean {
  return (node, surrounding) => {
    if (isKeepWhole(node)) {
      if (node.pageNumbers.length < 2) return false; // already whole
      const ownPage = node.startPosition.pageNumber;
      const before = surrounding
        .getPreviousNodesOnPage()
        .filter((other) => draws(other) && !isFooter(other));
      if (before.length === 0) {
        // Already at the top of a page and still spilling over: taller than the page itself. Moving
        // it again would change nothing, so it breaks — and gets named.
        options.onOversizedBlock?.({ id: String(node.id), page: ownPage });
        return false;
      }
      return true;
    }

    if (isHeading(node)) {
      const body = bodyBelow(surrounding);
      return body.length === 0 || roomBelow(body[0].startPosition) < MIN_BODY_HEIGHT;
    }

    return false;
  };
}
