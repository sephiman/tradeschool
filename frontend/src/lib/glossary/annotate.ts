import type { Nodes, Parent, PhrasingContent, Root, Text } from "mdast";
import {
  compileTerms,
  normalize,
  NOT_HYPHENATED,
  WORD,
  type CompiledTerms,
  type TermMatcher,
} from "@/lib/glossary/terms";
import type { RefKind, RefRegistry } from "@/lib/refs/registry";

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

/** The second mark type: a lesson/module mention (`m22`, `m19-l2`) that resolved to a real target. */
export const LESSON_REF = "lessonRef";

export interface LessonRefNode extends Parent {
  type: "lessonRef";
  refKind: RefKind;
  /** The mentioned entity's display id — each surface derives its own link from it. */
  refId: string;
  children: Text[];
  data: { hName: "span"; hProperties: { "data-ref-kind": RefKind; "data-ref-id": string } };
}

declare module "mdast" {
  interface PhrasingContentMap {
    glossaryTerm: GlossaryTermNode;
    lessonRef: LessonRefNode;
  }
  interface RootContentMap {
    glossaryTerm: GlossaryTermNode;
    lessonRef: LessonRefNode;
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
  LESSON_REF,
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

function contextOf(value: string, hit: { start: number; end: number }): string {
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

/** Every text node the annotator may touch, in reading order, with where it sits.
 *
 *  `block` is the prose unit the node belongs to — the paragraph or table cell — so a report can
 *  quote a sentence of context around a mark that is alone in its own inline node (`**m22**`). */
function eligibleText(tree: Root): { parent: Parent; index: number; node: Text; block: Parent }[] {
  const found: { parent: Parent; index: number; node: Text; block: Parent }[] = [];
  const walk = (parent: Parent, block: Parent): void => {
    parent.children.forEach((child, index) => {
      if (SKIP.has(child.type)) return;
      const inner = child.type === "paragraph" || child.type === "tableCell" ? (child as Parent) : block;
      if (child.type === "text") found.push({ parent, index, node: child, block });
      else if ("children" in child) walk(child as Parent, inner);
    });
  };
  walk(tree, tree);
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

/**
 * Every id-shaped token in prose: `m22`, `m19-l2` — same boundary rules as the term pattern, so
 * `fig-m11-…` and `m08-ex-6` are not mentions of m11 or m08. This is the ONE detector for lesson
 * references; the dangling guard works because detection is by SHAPE and resolution then has to
 * answer for every hit, rather than a resolver-driven scan that could not see what it missed.
 */
const REF_PATTERN = new RegExp(
  `(?<![${WORD}])${NOT_HYPHENATED.before}m\\d{2}(?:-l\\d+)?(?![${WORD}])${NOT_HYPHENATED.after}`,
  "giu",
);

/** One reference decision, as the golden report records it — linked, self-skipped, or dangling. */
export interface RefMark {
  /** The lesson the mention sits in, as the caller addressed it (display id). */
  lessonId: string;
  /** The mention as written. */
  mention: string;
  /** What it resolved to; absent on a dangling mention. */
  refKind?: RefKind;
  refId?: string;
  refKey?: string;
  context: string;
}

export interface AnnotateRefsResult {
  /** Mentions now carrying a link, in reading order. */
  marks: RefMark[];
  /** Mentions of the page they sit on — real, deliberately not linked. */
  self: RefMark[];
  /** Id-shaped tokens no entity answers to. The suite asserts this stays empty. */
  dangling: RefMark[];
}

export interface AnnotateRefsOptions {
  /** The DISPLAY id of the lesson being annotated — mentions are display ids, and self is exact. */
  lessonId: string;
  registry: RefRegistry;
}

function refNode(text: string, kind: RefKind, refId: string): LessonRefNode {
  return {
    type: LESSON_REF,
    refKind: kind,
    refId,
    children: [{ type: "text", value: text }],
    data: { hName: "span", hProperties: { "data-ref-kind": kind, "data-ref-id": refId } },
  };
}

/** A block's prose flattened back together, so a mark alone in its inline node still gets a sentence
 *  of context — `**m22**` is a text node of six characters, and six characters review nothing. */
interface BlockPose {
  value: string;
  offsets: Map<Text, number>;
}

function poseBlocks(targets: { node: Text; block: Parent }[]): Map<Parent, BlockPose> {
  const blocks = new Map<Parent, BlockPose>();
  for (const { node, block } of targets) {
    const pose = blocks.get(block) ?? { value: "", offsets: new Map() };
    pose.offsets.set(node, pose.value.length);
    pose.value += node.value;
    blocks.set(block, pose);
  }
  return blocks;
}

function annotateRefText(
  node: Text,
  o: AnnotateRefsOptions,
  out: AnnotateRefsResult,
  pose: BlockPose,
): PhrasingContent[] | null {
  const value = node.value;
  const at = pose.offsets.get(node) ?? 0;
  const nodes: PhrasingContent[] = [];
  let cut = 0;
  for (const match of value.matchAll(REF_PATTERN)) {
    const hit = { start: match.index, end: match.index + match[0].length };
    const mention = match[0];
    const mark: RefMark = {
      lessonId: o.lessonId,
      mention,
      context: contextOf(pose.value, { start: at + hit.start, end: at + hit.end }),
    };
    const target = o.registry.resolve(mention);
    if (!target) {
      out.dangling.push(mark);
      continue;
    }
    mark.refKind = target.kind;
    mark.refId = target.id;
    mark.refKey = target.key;
    // Self is by landing page, not by spelling: a single-lesson module's mention inside that very
    // lesson would link the reader to where they already are, exactly like naming the lesson itself.
    if (target.path === `/lessons/${o.lessonId}`) {
      out.self.push(mark);
      continue;
    }
    if (hit.start > cut) nodes.push({ type: "text", value: value.slice(cut, hit.start) });
    nodes.push(refNode(mention, target.kind, target.id));
    cut = hit.end;
    out.marks.push(mark);
  }
  if (nodes.length === 0) return null;
  if (cut < value.length) nodes.push({ type: "text", value: value.slice(cut) });
  return nodes;
}

/**
 * Marks every resolvable lesson/module mention in place and reports every decision.
 *
 * No first-occurrence policy here, unlike the terms: a reference is navigation, not vocabulary, so
 * each mention carries its link on every surface. What is skipped is skipped structurally, by the
 * same `eligibleText` walk the terms use — code spans, headings, links and directives never match.
 */
export function annotateLessonRefs(tree: Root, o: AnnotateRefsOptions): AnnotateRefsResult {
  const out: AnnotateRefsResult = { marks: [], self: [], dangling: [] };
  const targets = eligibleText(tree);
  const blocks = poseBlocks(targets);
  const replacements = new Map<Parent, Map<number, PhrasingContent[]>>();
  for (const { parent, index, node, block } of targets) {
    const split = annotateRefText(node, o, out, blocks.get(block) as BlockPose);
    if (!split) continue;
    const byIndex = replacements.get(parent) ?? new Map<number, PhrasingContent[]>();
    byIndex.set(index, split);
    replacements.set(parent, byIndex);
  }
  for (const [parent, byIndex] of replacements) {
    parent.children = parent.children.flatMap(
      (child, index) => (byIndex.get(index) ?? [child]) as Nodes[],
    ) as Parent["children"];
  }
  return out;
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
