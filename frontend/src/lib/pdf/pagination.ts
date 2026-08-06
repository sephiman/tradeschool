import type { Node, NodeQueries, NodeStartPosition } from "pdfmake/interfaces";
import { DEFAULT_STYLE } from "@/lib/pdf/page";

/**
 * Where the book is allowed to break pages.
 *
 * Two rules, both about not stranding something from the thing that explains it:
 *
 * * **A heading stays with its body.** A heading printed at the foot of a page with its first
 *   paragraph overleaf reads as the end of a section rather than the start of one. If a heading
 *   cannot keep a couple of lines of its own content company, it moves to the next page.
 * * **A callout is printed whole.** A `:::note` is a box; half a box at the foot of a page, with the
 *   sentence finishing inside the top of another box overleaf, is worse than a gap.
 *
 * pdfmake offers `unbreakable: true`, and it is the wrong tool for the second rule: a block taller
 * than a page is not overflowed but **truncated** — `commitUnbreakableBlock` keeps `pages[0]` and
 * discards the rest ("no support for multi-page unbreakableBlocks"). Silently losing a paragraph is
 * a worse outcome than any page break. `pageBreakBefore` cannot lose content: the worst it can do is
 * leave a box split, which is what happens to a callout genuinely taller than a page — and that one
 * is reported rather than hidden.
 *
 * Each break costs a full re-layout of the document (pdfmake inserts one break per pass), which is
 * why the rules only fire where a reader would actually notice.
 */

/** The subset of a laid-out node this module reasons about. `Node` is what pdfmake hands the
 *  callback: a *copy* of a whitelist of properties, so only `id`, `headlineLevel`, `style`, the ink
 *  properties and the positions survive from the document definition — no custom marker would. */
export type LayoutNode = Node;

/** Ids of the blocks that must print whole: a `:::note` box, and an answer-key entry (whose number
 *  must never be parted from the answer it addresses). */
export const CALLOUT_ID = "note";
export const ANSWER_ID = "answer";
const KEEP_WHOLE = [CALLOUT_ID, ANSWER_ID];
/** Ids that mark a figure block. Only used to make the "never split from its caption" rule checkable. */
export const FIGURE_ID = "figure";

/** `<kind>-<source>-<ordinal>`: unique across the document, which pdfmake requires — a duplicate id
 *  throws — and readable enough to name a location in the generation report. */
export function printedId(kind: string, source: string, ordinal: number): string {
  return `${kind}-${source}-${ordinal}`;
}

/** pdfmake accepts `id` on any node — `DocPreprocessor` registers it as a reference, and it is one of
 *  the properties the pagination callback receives — but `@types/pdfmake` declares it only on the
 *  table of contents. The gap is named here once rather than cast at every call site. */
export function withId<T extends object>(content: T, id: string): T & { id: string } {
  return { ...content, id };
}

/** How much body a heading has to keep on its page: two lines of it. One line under a heading at the
 *  foot of a page is a technicality, not a beginning. */
const MIN_BODY_LINES = 2;
const LINE_HEIGHT = (DEFAULT_STYLE.fontSize ?? 10.5) * (DEFAULT_STYLE.lineHeight ?? 1.35);
export const MIN_BODY_HEIGHT = MIN_BODY_LINES * LINE_HEIGHT;

/** A block that could not be kept whole because it is taller than the page itself. */
export interface OversizedBlock {
  id: string;
  /** The page its first fragment landed on — where a reviewer will find it. */
  page: number;
}

/** The node's style NAME, if it has one. `StyleReference` also allows inline style objects and lists;
 *  everything this document builds names its styles, so only the names are of interest. */
function styleNames(node: LayoutNode): string[] {
  const style = node.style;
  if (typeof style === "string") return [style];
  if (Array.isArray(style)) return style.filter((entry): entry is string => typeof entry === "string");
  return [];
}

/** Does this node put ink on the page, or is it a container whose children do?
 *
 *  The distinction is load-bearing. pdfmake records a container's position where layout ENTERS it,
 *  not where its content lands, so a stack whose unbreakable child then moved to the next page still
 *  claims the page it was entered on. Counting that as "the heading has body below it" strands the
 *  heading with a third of a page of white space under it — observed, twice, before this filter. */
function draws(node: LayoutNode): boolean {
  return (
    node.text !== undefined ||
    node.image !== undefined ||
    node.canvas !== undefined ||
    node.svg !== undefined ||
    node.qr !== undefined
  );
}

/** The running footer is laid out after every page's content, so it appears in every page's
 *  "following nodes" and would make every heading look accompanied. */
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

/** What will still be on this page, under this heading, once the keep-whole rule has had its say.
 *
 *  A box that spans pages is about to be moved off this page and takes its inner paragraphs with it —
 *  and those paragraphs, not the box, are the nodes carrying the ink. Counting them left three
 *  headings stranded behind a callout that then walked away. */
function bodyBelow(surrounding: NodeQueries): LayoutNode[] {
  const following = surrounding.getFollowingNodesOnPage();
  const leaving = following.findIndex((node) => isKeepWhole(node) && node.pageNumbers.length > 1);
  const staying = leaving === -1 ? following : following.slice(0, leaving);
  return staying.filter((node) => draws(node) && !isFooter(node) && !isHeading(node));
}

export interface KeepTogetherOptions {
  /** Called once per block that is taller than a page, so the report can name it. Never a failure:
   *  such a box has to break somewhere, and generating the book matters more. */
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
