import { describe, expect, it } from "vitest";
import type { Node, NodeQueries } from "pdfmake/interfaces";
import { MIN_BODY_HEIGHT, keepTogether, type OversizedBlock } from "@/lib/pdf/pagination";

/**
 * The pagination rules, against the node shapes pdfmake actually hands the callback.
 *
 * Three cases are regressions, each a property of pdfmake's node model rather than the document: the
 * footer following every page, the container claiming a page its ink never reached, and the callout
 * whose paragraphs leave with it.
 */

const PAGE_HEIGHT = 726;

/** A laid-out node, with only what the rules read. */
function node(props: Partial<Node> & { page?: number; at?: number }): Node {
  const { page = 1, at = 0, ...rest } = props;
  return {
    pageNumbers: [page],
    pages: 1,
    stack: false,
    startPosition: {
      pageNumber: page,
      left: 56,
      top: 54 + at * PAGE_HEIGHT,
      verticalRatio: at,
      horizontalRatio: 0,
      pageInnerHeight: PAGE_HEIGHT,
      pageInnerWidth: 483,
      pageOrientation: "portrait",
    },
    ...rest,
  } as Node;
}

const heading = (props: Partial<Node> & { page?: number; at?: number } = {}) =>
  node({ text: "A heading", headlineLevel: 2, ...props });
const paragraph = (props: Partial<Node> & { page?: number; at?: number } = {}) =>
  node({ text: "Body text", style: "p", ...props });
const footer = (props: Partial<Node> & { page?: number; at?: number } = {}) =>
  node({ text: "Crypto Futures, from Zero", style: "footer", at: 1, ...props });
const callout = (props: Partial<Node> & { page?: number; at?: number } = {}) =>
  node({ id: "note-m08-l1-0", table: { body: [] }, style: "note", ...props });
/** A container: a stack has no ink of its own — its children carry it. */
const container = (props: Partial<Node> & { page?: number; at?: number } = {}) =>
  node({ stack: true, ...props });

function surrounding(before: Node[], after: Node[]): NodeQueries {
  return {
    getPreviousNodesOnPage: () => before,
    getFollowingNodesOnPage: () => after,
    getNodesOnNextPage: () => [],
  };
}

describe("a heading", () => {
  const rule = keepTogether();

  it("stays where its body starts under it with room to breathe", () => {
    const body = paragraph({ at: 0.5 });
    expect(rule(heading({ at: 0.45 }), surrounding([], [body, footer()]))).toBe(false);
  });

  it("moves when its body would begin on the next page", () => {
    expect(rule(heading({ at: 0.95 }), surrounding([paragraph()], [footer()]))).toBe(true);
  });

  it("moves when only a sliver of body would fit under it", () => {
    // One line under a heading at the foot of a page is a technicality, not a beginning.
    const sliver = paragraph({ at: 1 - MIN_BODY_HEIGHT / PAGE_HEIGHT / 2 });
    expect(rule(heading({ at: 0.93 }), surrounding([], [sliver, footer()]))).toBe(true);
  });

  it("is not kept company by the running footer", () => {
    // The footer is laid out after every page's content, so it follows EVERY heading. Counting it
    // made a census of the real book report zero orphans on a page that visibly ended in a heading.
    expect(rule(heading({ at: 0.95 }), surrounding([], [footer(), footer()]))).toBe(true);
  });

  it("is not kept company by another heading", () => {
    // "Exercises" followed by "Exercise 8.1" is two headings and still no content: if the question
    // itself is overleaf, both have to go.
    const next = heading({ at: 0.9 });
    expect(rule(heading({ at: 0.86 }), surrounding([], [next, footer()]))).toBe(true);
  });

  it("is not kept company by a container whose ink never landed on the page", () => {
    // pdfmake records a container's position where layout ENTERS it. An unbreakable figure that then
    // moved to the next page leaves the container still claiming this one — which stranded two
    // headings with a third of a page of white space under them.
    const empty = container({ at: 0.7, page: 1, pageNumbers: [1, 2] });
    expect(rule(heading({ at: 0.68 }), surrounding([], [empty, footer()]))).toBe(true);
  });

  it("is not kept company by a callout that is itself about to move", () => {
    // The box's ink lives in its inner paragraphs, and they leave with it.
    const leaving = callout({ at: 0.6, pageNumbers: [1, 2] });
    const inside = paragraph({ at: 0.62, pageNumbers: [1, 2] });
    expect(rule(heading({ at: 0.55 }), surrounding([], [leaving, inside, footer()]))).toBe(true);
  });

  it("stays when the doomed callout is only what comes after its real body", () => {
    const body = paragraph({ at: 0.3 });
    const leaving = callout({ at: 0.6, pageNumbers: [1, 2] });
    expect(rule(heading({ at: 0.25 }), surrounding([], [body, leaving, footer()]))).toBe(false);
  });
});

describe("a callout", () => {
  it("stays when it already fits on one page", () => {
    expect(keepTogether()(callout({ at: 0.4 }), surrounding([paragraph()], []))).toBe(false);
  });

  it("moves to the next page rather than break across one", () => {
    const split = callout({ at: 0.8, pageNumbers: [1, 2] });
    expect(keepTogether()(split, surrounding([paragraph()], []))).toBe(true);
  });

  it("breaks, and is reported, when it is taller than a page itself", () => {
    // Already at the top of a page and still spilling over: moving it again would change nothing, so
    // it has to break. The book still generates; the box gets named instead.
    const reported: OversizedBlock[] = [];
    const rule = keepTogether({ onOversizedBlock: (c) => reported.push(c) });
    const giant = callout({ at: 0, page: 7, pageNumbers: [7, 8] });
    expect(rule(giant, surrounding([footer()], []))).toBe(false);
    expect(reported).toEqual([{ id: "note-m08-l1-0", page: 7 }]);
  });

  it("is not reported merely for sitting under the previous page's footer", () => {
    const rule = keepTogether({
      onOversizedBlock: () => expect.unreachable("a callout with content above it is not oversized"),
    });
    const split = callout({ at: 0.5, pageNumbers: [3, 4] });
    expect(rule(split, surrounding([footer(), paragraph()], []))).toBe(true);
  });
});

describe("an answer-key entry", () => {
  const entry = (props: Partial<Node> & { page?: number; at?: number } = {}) =>
    node({ id: "answer-m07-ex-1-0", stack: true, ...props });

  it("moves rather than part its number from its answer", () => {
    expect(keepTogether()(entry({ at: 0.9, pageNumbers: [1, 2] }), surrounding([paragraph()], []))).toBe(
      true,
    );
  });

  it("does not strand the module heading above it", () => {
    // What `unbreakable: true` did here: pdfmake moved the entry itself during layout and left the
    // "M07 · Real PnL" heading alone at the foot of the page, where no rule could see it.
    const leaving = entry({ at: 0.9, pageNumbers: [1, 2] });
    expect(keepTogether()(heading({ at: 0.87 }), surrounding([], [leaving, footer()]))).toBe(true);
  });
});

describe("everything else", () => {
  it("breaks wherever it falls", () => {
    const rule = keepTogether();
    expect(rule(paragraph({ at: 0.99 }), surrounding([], [footer()]))).toBe(false);
    expect(rule(container({ at: 0.99 }), surrounding([], [footer()]))).toBe(false);
  });
});
