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
