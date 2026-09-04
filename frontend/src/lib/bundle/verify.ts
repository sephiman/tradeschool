import type { Nodes, Root } from "mdast";
import type { GlossaryEntry } from "@/api/course";

/**
 * The bundle's text is the web's text: a multiset diff, per locale, that must come out empty.
 *
 * What it is for. The bundle crosses a repository boundary as JSON, and everything that can go wrong
 * on that trip is silent — an annotator that drops a text node while splitting it around a mark, a
 * serializer that loses a node, a re-encoding that mangles a `→` or an accent, a stale file left
 * behind by a partial export. None of those makes the bundle unreadable; they make it subtly wrong,
 * in one paragraph, in one locale. So the export re-READS what it wrote and compares the words in it
 * against the words the web serves from the same content.
 *
 * Why a multiset and not a string. The AST's text is split at mark boundaries and grouped by block,
 * so it never reassembles into the markdown byte for byte — but no word may appear a different
 * number of times. A multiset diff also says *which* word moved, which a length check never does.
 *
 * The comparison is per BLOCK for tokenizing (a paragraph, a heading, a table cell) because those
 * are the only nodes text lives inside, and joining across two of them would fuse the last word of
 * one to the first of the next.
 *
 * WHAT THE MULTISET CANNOT SEE, and why there is a second check below it.
 *
 * Two blind spots, both by construction. It splits on `/\s+/`, so no whitespace bug can reach it: a
 * soft break that became a hard one, a doubled space, a lost line — the delimiter eats them all. And
 * it is a multiset, so word ORDER is not in it at all; a paragraph whose sentences swapped, or that
 * split into two, is exactly the same bag of words. Worse than either: its reference is the web's own
 * mdast of the same markdown, off the same parser as the bundle's, so a change to that parser moves
 * BOTH sides together and the diff stays empty. An oracle derived from the code under test agrees
 * with its bugs.
 *
 * So `bundleBlocks`/`renderedBlocks`/`blockDiff` are the second opinion: the bundle's text against
 * the text the web actually PAINTS, per lesson, block by block, in order, with whitespace kept as
 * information. The reference comes out the far end of `LessonMarkdown` — mdast to hast to HTML to
 * DOM — which shares no code with the bundle's serialization and is configured separately from
 * `bundle/ast.ts`, so the two parsers diverging is the first thing it reports.
 */

/** Nodes that hold text directly; every `text`/`inlineCode` in the course sits inside one of these. */
const TEXT_BLOCKS = new Set(["paragraph", "heading", "tableCell"]);

/** One string per text-bearing block, in reading order, marks concatenated back into their sentence. */
export function blockTexts(tree: Root): string[] {
  const blocks: string[] = [];
  const inline = (node: Nodes): string => {
    if (node.type === "text" || node.type === "inlineCode") return node.value;
    if ("children" in node) return (node.children as Nodes[]).map(inline).join("");
    return "";
  };
  const walk = (node: Nodes): void => {
    if (TEXT_BLOCKS.has(node.type)) {
      blocks.push(inline(node));
      return;
    }
    if ("children" in node) for (const child of node.children as Nodes[]) walk(child);
  };
  walk(tree);
  return blocks;
}

/** Every word in the glossary a reader can read: the term, its definitions, and its origin titles. */
export function glossaryTexts(entries: GlossaryEntry[]): string[] {
  const out: string[] = [];
  for (const entry of entries) {
    out.push(entry.term);
    if (entry.originTitle) out.push(entry.originTitle);
    if (entry.definition) out.push(entry.definition);
    if (entry.aliasOf) out.push(entry.aliasOf.term);
    for (const sense of entry.senses ?? []) {
      if (sense.originTitle) out.push(sense.originTitle);
      out.push(sense.definition);
    }
  }
  return out;
}

export function multiset(strings: string[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const value of strings) {
    for (const token of value.split(/\s+/)) {
      if (!token) continue;
      counts.set(token, (counts.get(token) ?? 0) + 1);
    }
  }
  return counts;
}

export interface MultisetDiff {
  /** `token -> (bundle count) - (reference count)`, only where the two disagree. */
  delta: Record<string, number>;
  bundleTokens: number;
  referenceTokens: number;
}

export function diff(bundle: string[], reference: string[]): MultisetDiff {
  const left = multiset(bundle);
  const right = multiset(reference);
  const delta: Record<string, number> = {};
  for (const token of new Set([...left.keys(), ...right.keys()])) {
    const gap = (left.get(token) ?? 0) - (right.get(token) ?? 0);
    if (gap !== 0) delta[token] = gap;
  }
  const total = (counts: Map<string, number>): number => [...counts.values()].reduce((a, b) => a + b, 0);
  return { delta, bundleTokens: total(left), referenceTokens: total(right) };
}

export function isClean(result: MultisetDiff): boolean {
  return Object.keys(result.delta).length === 0;
}

// --- the second opinion: the bundle's blocks against the ones the web paints ----------------------

/** A hard break is the one whitespace a reader can SEE, so it survives normalization as a newline. */
const HARD_BREAK = "\n";

/** Inline mdast: what a sentence is made of. Every other kind ENDS the block being read. */
const INLINE_NODES = new Set([
  "text", "inlineCode", "strong", "emphasis", "delete", "link", "glossaryTerm", "lessonRef",
]);

/** The same closed set on the rendered side. `br` is absent on purpose — it is not silent. */
const INLINE_TAGS = new Set([
  "SPAN", "STRONG", "EM", "B", "I", "CODE", "A", "DEL", "S", "SUB", "SUP", "SMALL", "MARK", "ABBR", "U",
]);

const ELEMENT_NODE = 1;
const TEXT_NODE = 3;

/** Whitespace inside one text run carries no meaning: a soft break, a tab and two spaces all read alike. */
function collapse(value: string): string {
  return value.replace(/\s+/g, " ");
}

/** A finished block: single spaces, no space hugging a hard break, no edges. Empty means no block. */
function finish(buffer: string): string {
  return buffer.replace(/ *\n */g, HARD_BREAK).replace(/ {2,}/g, " ").trim();
}

/** What both walkers fill: text runs and break marks in, one string per block of reading out. */
function blockBuffer() {
  const blocks: string[] = [];
  let buffer = "";
  return {
    blocks,
    text: (value: string): void => {
      buffer += collapse(value);
    },
    hardBreak: (): void => {
      buffer += HARD_BREAK;
    },
    // Called on both sides of every block node, so a block that opens mid-sentence (a nested list
    // under an item's own text) closes the sentence it interrupted instead of swallowing it.
    endBlock: (): void => {
      const text = finish(buffer);
      if (text) blocks.push(text);
      buffer = "";
    },
  };
}

/** One string per block of reading in the bundle's AST, in order, whitespace kept as information. */
export function bundleBlocks(tree: Root): string[] {
  const out = blockBuffer();
  const walk = (node: Nodes): void => {
    if (node.type === "text" || node.type === "inlineCode") return out.text(node.value);
    if (node.type === "break") return out.hardBreak();
    const inline = INLINE_NODES.has(node.type);
    if (!inline) out.endBlock();
    if ("children" in node) for (const child of node.children as Nodes[]) walk(child);
    if (!inline) out.endBlock();
  };
  walk(tree);
  out.endBlock();
  return out.blocks;
}

/** The same, read off the DOM the web renders — a `<p>`, an `<li>`, a `<td>`; a `<br>` kept as one. */
export function renderedBlocks(root: Node): string[] {
  const out = blockBuffer();
  const walk = (node: Node): void => {
    if (node.nodeType === TEXT_NODE) return out.text(node.nodeValue ?? "");
    if (node.nodeType !== ELEMENT_NODE) return;
    if (node.nodeName === "BR") return out.hardBreak();
    const inline = INLINE_TAGS.has(node.nodeName);
    if (!inline) out.endBlock();
    for (const child of node.childNodes) walk(child);
    if (!inline) out.endBlock();
  };
  walk(root);
  out.endBlock();
  return out.blocks;
}

export interface BlockMismatch {
  /** Position in reading order; a block one side does not have at all reports `null` there. */
  index: number;
  bundle: string | null;
  rendered: string | null;
}

/** Block for block, in order. Empty means the bundle carries the page the web paints, exactly. */
export function blockDiff(bundle: string[], rendered: string[]): BlockMismatch[] {
  const mismatches: BlockMismatch[] = [];
  for (let index = 0; index < Math.max(bundle.length, rendered.length); index++) {
    const left = bundle[index] ?? null;
    const right = rendered[index] ?? null;
    if (left !== right) mismatches.push({ index, bundle: left, rendered: right });
  }
  return mismatches;
}
