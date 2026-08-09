import type { Nodes, Parent, PhrasingContent, Root, Text } from "mdast";
import { compileTerms, normalize, type CompiledTerms, type TermMatcher } from "@/lib/glossary/terms";

/**
 * The ONE annotator: which glossary terms in a lesson's prose become a link, on every surface.
 *
 * It runs on the mdast the two renderers already parse, so what is skipped is skipped structurally —
 * code spans, link text and `::figure` directives are node types, not regions a regex has to mask.
 * Both surfaces call this and then render the `glossaryTerm` nodes it plants; neither detects on its
 * own, which is the same drift rule that governs figure rendering.
 *
 * The two marking policies are ONE algorithm with two lifetimes for `marked`: a fresh set per lesson
 * is the web's "first occurrence in this lesson", one set carried across the course in reading order
 * is the PDF's "first occurrence in the book".
 *
 * The first occurrence CLAIMS the term's slot and the origin exception then vetoes it; no later
 * occurrence takes its place. That is why a term the book first uses inside its own origin lesson
 * carries no PDF link anywhere — correct, not a bug: the reader met it where it is taught. The web,
 * whose slot resets each lesson, still marks it everywhere else. An entry's `link_except` lessons
 * work the other way round: there the word is a false friend, so it is not an occurrence to spend.
 *
 * A term split by markup (`**order** block`) is not detected, so it is not marked — the term's next
 * clean occurrence is.
 */

export const GLOSSARY_TERM = "glossaryTerm";

export interface GlossaryTermNode extends Parent {
  type: "glossaryTerm";
  termId: string;
  children: Text[];
  data: { hName: "span"; hProperties: { "data-term-id": string } };
}

declare module "mdast" {
  interface PhrasingContentMap {
    glossaryTerm: GlossaryTermNode;
  }
  interface RootContentMap {
    glossaryTerm: GlossaryTermNode;
  }
}

/** One decision the annotator made, as the golden report records it. */
export interface TermMark {
  lessonId: string;
  termId: string;
  /** The characters the reader sees marked — the variant that actually matched, as written. */
  text: string;
  /** One flattened line of the prose around it, the mark in «», for review. */
  context: string;
}

export interface AnnotateOptions {
  lessonId: string;
  terms: TermMatcher[];
  /** Terms already marked. The caller owns its lifetime, and that lifetime IS the policy. */
  marked: Set<string>;
}

/** Nodes whose whole subtree is out of bounds: a link inside a link, or a term inside a title. */
const SKIP = new Set([
  "heading",
  "code",
  "inlineCode",
  "html",
  "link",
  "linkReference",
  "image",
  "imageReference",
  "definition",
  "footnoteDefinition",
  "leafDirective",
  "yaml",
  "toml",
  GLOSSARY_TERM,
]);

interface Hit {
  start: number;
  end: number;
  matcher: TermMatcher;
}

const CONTEXT = 46;

function flatten(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function contextOf(value: string, hit: Hit): string {
  const before = value.slice(Math.max(0, hit.start - CONTEXT), hit.start);
  const after = value.slice(hit.end, hit.end + CONTEXT);
  const lead = hit.start > CONTEXT ? "…" : "";
  const tail = hit.end + CONTEXT < value.length ? "…" : "";
  return flatten(`${lead}${before}«${value.slice(hit.start, hit.end)}»${after}${tail}`);
}

/**
 * Every candidate in one text node.
 *
 * One scan, leftmost-longest by construction (see `compileTerms`), so a longer term always takes the
 * span a shorter one sits inside — and it takes it BEFORE the policy runs. A longer term that turns
 * out to be unmarkable here still shadows the shorter one: a link on a fragment of a longer term
 * would be worse than no link at all.
 */
function candidates(value: string, terms: CompiledTerms): Hit[] {
  const hits: Hit[] = [];
  for (const match of value.matchAll(terms.pattern)) {
    const matcher = terms.byVariant.get(normalize(match[0]));
    if (matcher) hits.push({ start: match.index, end: match.index + match[0].length, matcher });
  }
  return hits;
}

function termNode(text: string, termId: string): GlossaryTermNode {
  return {
    type: GLOSSARY_TERM,
    termId,
    children: [{ type: "text", value: text }],
    // How the web renderer sees it: mdast-util-to-hast turns an unknown node with `hName` into that
    // element, which is the same seam `remarkDirectiveToHast` uses for callouts.
    data: { hName: "span", hProperties: { "data-term-id": termId } },
  };
}

function annotateText(
  node: Text,
  o: AnnotateOptions,
  terms: CompiledTerms,
): { nodes: PhrasingContent[]; marks: TermMark[] } | null {
  const value = node.value;
  const marks: TermMark[] = [];
  const nodes: PhrasingContent[] = [];
  let cut = 0;
  for (const hit of candidates(value, terms)) {
    const { matcher } = hit;
    // An excluded lesson is one where this word is a false friend — `base de datos`, `Wall Street`.
    // It is not an occurrence at all, so it costs the term nothing and the next one still counts.
    if (matcher.notHere.has(o.lessonId) || o.marked.has(matcher.id)) continue;
    // The slot is claimed here, BEFORE the origin veto: an occurrence in a lesson the term points
    // back at spends the term's one chance rather than passing it to the next occurrence.
    o.marked.add(matcher.id);
    if (matcher.origins.has(o.lessonId)) continue;
    const text = value.slice(hit.start, hit.end);
    if (hit.start > cut) nodes.push({ type: "text", value: value.slice(cut, hit.start) });
    nodes.push(termNode(text, matcher.id));
    cut = hit.end;
    marks.push({ lessonId: o.lessonId, termId: matcher.id, text, context: contextOf(value, hit) });
  }
  if (marks.length === 0) return null;
  if (cut < value.length) nodes.push({ type: "text", value: value.slice(cut) });
  return { nodes, marks };
}

/** Every text node the annotator may touch, in reading order, with where it sits. */
function eligibleText(tree: Root): { parent: Parent; index: number; node: Text }[] {
  const found: { parent: Parent; index: number; node: Text }[] = [];
  const walk = (parent: Parent): void => {
    parent.children.forEach((child, index) => {
      if (SKIP.has(child.type)) return;
      if (child.type === "text") found.push({ parent, index, node: child });
      else if ("children" in child) walk(child as Parent);
    });
  };
  walk(tree);
  return found;
}

/**
 * The terms worth scanning this lesson for at all.
 *
 * A variant can only match if its FIRST word is somewhere in the prose — first word, because a
 * multi-word term may be split by the hard wrap and would not survive a whole-phrase `includes`.
 * It keeps the compiled alternation down to the terms this lesson could possibly contain, which is
 * what makes annotating 36 lessons a second of the export rather than a minute of it.
 */
function present(terms: TermMatcher[], haystack: string): TermMatcher[] {
  const lowered = haystack.toLowerCase();
  return terms.filter((matcher) =>
    matcher.variants.some((variant) => lowered.includes(variant.split(/\s+/)[0].toLowerCase())),
  );
}

/** Marks the tree in place and reports what it marked, in reading order. */
export function annotateLesson(tree: Root, o: AnnotateOptions): TermMark[] {
  const targets = eligibleText(tree);
  const here = present(o.terms, targets.map((target) => target.node.value).join("\n"));
  if (here.length === 0) return [];
  const terms = compileTerms(here);

  const marks: TermMark[] = [];
  const replacements = new Map<Parent, Map<number, PhrasingContent[]>>();
  for (const { parent, index, node } of targets) {
    const split = annotateText(node, o, terms);
    if (!split) continue;
    marks.push(...split.marks);
    const byIndex = replacements.get(parent) ?? new Map<number, PhrasingContent[]>();
    byIndex.set(index, split.nodes);
    replacements.set(parent, byIndex);
  }
  for (const [parent, byIndex] of replacements) {
    parent.children = parent.children.flatMap(
      (child, index) => (byIndex.get(index) ?? [child]) as Nodes[],
    ) as Parent["children"];
  }
  return marks;
}
