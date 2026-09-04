import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import type { Nodes, Root } from "mdast";
import type { GlossaryEntry } from "@/api/course";
import { remarkBlockDirectives } from "@/lib/directives";
import { annotateLesson, annotateLessonRefs } from "@/lib/glossary/annotate";
import { buildTermIndex, type TermMatcher } from "@/lib/glossary/terms";
import { buildRefRegistry, type RefModule, type RefRegistry } from "@/lib/refs/registry";

/**
 * The lesson AST the Android bundle ships: the mdast **after** the annotator and **before**
 * `remarkDirectiveToHast`.
 *
 * That tap point is the whole design. After the annotator, because glossary marks and
 * lesson-reference marks are decided by ONE detector (`lib/glossary/annotate.ts`) whose rules —
 * word boundaries, the hard wrap, structural blindness to headings and code — are the drift this
 * codebase refuses to have twice; a Kotlin re-detector would be a second opinion about which words
 * a reader may tap. Before the hast hints, because `data.hName`/`data.hProperties` are instructions
 * for `mdast-util-to-hast`, i.e. for a DOM the app does not have: the app reads `::figure` as a
 * figure slot from the directive node itself, not from a `<div data-figure-id>`.
 *
 * The marking policy is the WEB's, which is what the app needs: a fresh `marked` set per lesson, so
 * a term is a tooltip once per lesson wherever it appears. The book's once-per-book policy is a
 * property of a 200-page print run and has no meaning on a phone.
 *
 * Positions are dropped. They are byte offsets into the markdown, they roughly triple the file, and
 * a reflowed paragraph upstream would otherwise rewrite every node after it — a diff no reviewer of
 * this bundle can read.
 */

const processor = unified().use(remarkParse).use(remarkGfm).use(remarkBlockDirectives);

/** The tap point, written into the bundle's own index so an artifact says where it was taken. */
export const BUNDLE_AST_TAP = "mdast after lib/glossary/annotate, before markdown.tsx's remarkDirectiveToHast";

/** Named in the exercise-reference file so a port can see the two mark types share one detector. */
export const BUNDLE_REF_DETECTOR = "lib/glossary/annotate.ts REF_PATTERN over lib/refs/registry.ts";

/** The two per-locale indexes the annotator needs, built once for a whole locale rather than per lesson. */
export interface AnnotationInputs {
  terms: TermMatcher[];
  registry: RefRegistry;
}

export function annotationInputs(
  entries: GlossaryEntry[],
  modules: RefModule[],
  locale: string,
): AnnotationInputs {
  return { terms: buildTermIndex(entries, locale), registry: buildRefRegistry(modules) };
}

function stripPositions(node: Nodes): void {
  delete node.position;
  if ("children" in node) for (const child of node.children as Nodes[]) stripPositions(child);
}

/**
 * One lesson's annotated mdast. `lessonId` is the DISPLAY id, which is the space the running app
 * annotates in — glossary origins and `linkExcept` arrive as display ids from the export, and a
 * self-reference is an exact match on the page's own id.
 */
export function lessonAst(markdown: string, lessonId: string, inputs: AnnotationInputs): Root {
  const tree = processor.parse(markdown);
  // Glossary first, then references — the order `LessonMarkdown` runs them in. It matters: each
  // mark type's node is in the other's SKIP set, so whichever runs first owns an overlapping span.
  annotateLesson(tree, { lessonId, terms: inputs.terms, marked: new Set<string>() });
  annotateLessonRefs(tree, { lessonId, registry: inputs.registry });
  stripPositions(tree);
  return tree;
}

/** The same parse with NO annotation — the reference the bundle's text is diffed against. */
export function bareAst(markdown: string): Root {
  const tree = processor.parse(markdown);
  stripPositions(tree);
  return tree;
}

/** Every node type in a tree, with how many times it occurs — the census the block vaccine reads. */
export function nodeTypeCensus(tree: Root): Record<string, number> {
  const counts: Record<string, number> = {};
  const walk = (node: Nodes): void => {
    counts[node.type] = (counts[node.type] ?? 0) + 1;
    if ("children" in node) for (const child of node.children as Nodes[]) walk(child);
  };
  walk(tree);
  return counts;
}
