// @vitest-environment node
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { Nodes, Root } from "mdast";
import { annotationInputs, bareAst, lessonAst, nodeTypeCensus } from "@/lib/bundle/ast";
import { blockTexts, diff, glossaryTexts, isClean, multiset } from "@/lib/bundle/verify";
import {
  CONTENT_DIR,
  glossaryFromContent,
  lessonMarkdown,
  manifestLessons,
  refModulesFromManifest,
  LOCALES,
  type Locale,
} from "@/test/courseContent";

/**
 * The Android bundle's lesson ASTs: taken at the right point in the pipeline, and carrying exactly
 * the marks the two frozen golden reports say the annotator draws.
 *
 * The tap point is asserted from both sides. After the annotator, because the marks have to be in the
 * tree; before `remarkDirectiveToHast`, because a `data.hName` on a directive would mean the export
 * is shipping instructions for a DOM the app does not have — and that mistake is silent, since a
 * `::figure` still renders either way on the web.
 *
 * Tying the marks to `content/glossary-links.<locale>.txt` and `content/lesson-refs.<locale>.txt` is
 * the load-bearing part. Those files are reviewed by hand and frozen; if the bundle marked a
 * different set of words than they record, the app would tooltip words no reviewer has ever seen.
 * The reports' lesson axis is the permanent KEY and the bundle's is the display id, which is exactly
 * the pair of spaces a renumbering separates — so the comparison goes through the manifest.
 */

const SLOW = 120_000;

function keyToId(): Map<string, string> {
  return new Map(manifestLessons().map((lesson) => [lesson.key ?? lesson.id, lesson.id]));
}

function inputsFor(locale: Locale) {
  // Display space, which is what the running app annotates in: the export renders glossary origins
  // and `linkExcept` as display ids, and a self-reference is an exact match on the page's own id.
  return annotationInputs(glossaryFromContent(locale, "display"), refModulesFromManifest(locale), locale);
}

function treesFor(locale: Locale): Map<string, Root> {
  const inputs = inputsFor(locale);
  return new Map(
    manifestLessons().map((lesson) => [
      lesson.id,
      lessonAst(lessonMarkdown(locale, lesson.id), lesson.id, inputs),
    ]),
  );
}

const cache = new Map<Locale, Map<string, Root>>();
function trees(locale: Locale): Map<string, Root> {
  const existing = cache.get(locale);
  if (existing) return existing;
  const built = treesFor(locale);
  cache.set(locale, built);
  return built;
}

function nodesOfType(tree: Root, type: string): Nodes[] {
  const found: Nodes[] = [];
  const walk = (node: Nodes): void => {
    if (node.type === type) found.push(node);
    if ("children" in node) for (const child of node.children as Nodes[]) walk(child);
  };
  walk(tree);
  return found;
}

/** The frozen glossary report's web rows: `lessonKey policy termId context`, comments dropped. */
function goldenTermMarks(locale: Locale): { lessonKey: string; termId: string }[] {
  const text = readFileSync(resolve(CONTENT_DIR, `glossary-links.${locale}.txt`), "utf8");
  return text
    .split("\n")
    .filter((line) => line && !line.startsWith("#"))
    .map((line) => line.trim().split(/\s+/))
    .map(([lessonKey, _flag, termId]) => ({ lessonKey, termId }));
}

/** The frozen reference report's rows: `lessonKey mention kind targetKey context`. */
function goldenRefMarks(locale: Locale): { lessonKey: string; kind: string; targetKey: string }[] {
  const text = readFileSync(resolve(CONTENT_DIR, `lesson-refs.${locale}.txt`), "utf8");
  return text
    .split("\n")
    .filter((line) => line && !line.startsWith("#"))
    .map((line) => line.trim().split(/\s+/))
    .map(([lessonKey, _mention, kind, targetKey]) => ({ lessonKey, kind, targetKey }));
}

describe.each(LOCALES)("the bundle's lesson ASTs (%s)", (locale) => {
  it("is taken AFTER the annotator: every lesson's marks are in the tree", () => {
    const marked = [...trees(locale).values()].filter(
      (tree) => nodesOfType(tree, "glossaryTerm").length > 0,
    );
    expect(marked.length).toBe(manifestLessons().length);
  }, SLOW);

  it("is taken BEFORE remarkDirectiveToHast: no directive carries a hast hint", () => {
    for (const [lessonId, tree] of trees(locale)) {
      for (const type of ["leafDirective", "containerDirective"]) {
        for (const node of nodesOfType(tree, type)) {
          expect((node as { data?: object }).data, `${locale}/${lessonId}`).toBeUndefined();
          expect((node as { name?: string }).name, `${locale}/${lessonId}`).toBeTruthy();
        }
      }
    }
  }, SLOW);

  it("carries no source positions", () => {
    for (const [lessonId, tree] of trees(locale)) {
      const walk = (node: Nodes): void => {
        expect(node.position, `${locale}/${lessonId} ${node.type}`).toBeUndefined();
        if ("children" in node) for (const child of node.children as Nodes[]) walk(child);
      };
      walk(tree);
    }
  }, SLOW);

  it("is deterministic: two runs serialize identically", () => {
    const once = JSON.stringify([...treesFor(locale)]);
    const twice = JSON.stringify([...treesFor(locale)]);
    expect(once).toBe(twice);
  }, SLOW);

  it("marks exactly the glossary terms the frozen report records, lesson for lesson", () => {
    const ids = keyToId();
    const expected = new Map<string, string[]>();
    for (const row of goldenTermMarks(locale)) {
      const lessonId = ids.get(row.lessonKey) ?? row.lessonKey;
      expected.set(lessonId, [...(expected.get(lessonId) ?? []), row.termId]);
    }
    for (const [lessonId, tree] of trees(locale)) {
      const marked = nodesOfType(tree, "glossaryTerm").map(
        (node) => (node as { termId: string }).termId,
      );
      expect(marked, `${locale}/${lessonId}`).toEqual(expected.get(lessonId) ?? []);
    }
  }, SLOW);

  it("marks exactly the lesson references the frozen report records", () => {
    const ids = keyToId();
    const moduleIds = new Map(
      refModulesFromManifest(locale).map((module) => [module.key ?? module.id, module.id]),
    );
    const expected = new Map<string, string[]>();
    for (const row of goldenRefMarks(locale)) {
      const lessonId = ids.get(row.lessonKey) ?? row.lessonKey;
      const targetId =
        row.kind === "lesson" ? ids.get(row.targetKey) : moduleIds.get(row.targetKey);
      expected.set(lessonId, [...(expected.get(lessonId) ?? []), `${row.kind} ${targetId}`]);
    }
    for (const [lessonId, tree] of trees(locale)) {
      const marked = nodesOfType(tree, "lessonRef").map((node) => {
        const mark = node as { refKind: string; refId: string };
        return `${mark.refKind} ${mark.refId}`;
      });
      expect(marked, `${locale}/${lessonId}`).toEqual(expected.get(lessonId) ?? []);
    }
  }, SLOW);

  it("annotating does not change a single word of the prose", () => {
    // The annotator splits text nodes around every mark. Splitting is exactly where a character gets
    // lost, and losing one is invisible on a page nobody is re-reading word by word.
    const annotated = [...trees(locale).values()].flatMap(blockTexts);
    const bare = manifestLessons().flatMap((lesson) =>
      blockTexts(bareAst(lessonMarkdown(locale, lesson.id))),
    );
    expect(isClean(diff(annotated, bare))).toBe(true);
  }, SLOW);

  it("uses only the node kinds the app has a renderer for", () => {
    // A floor, not the contract: `scripts/export_bundle.py`'s BLOCK_INVENTORY is the closed set and
    // the export refuses to write a bundle that leaves it. This says the census is worth reading.
    const census: Record<string, number> = {};
    for (const tree of trees(locale).values()) {
      for (const [type, count] of Object.entries(nodeTypeCensus(tree))) {
        census[type] = (census[type] ?? 0) + count;
      }
    }
    expect(Object.keys(census).sort()).toEqual([
      "blockquote", "containerDirective", "emphasis", "glossaryTerm", "heading", "inlineCode",
      "leafDirective", "lessonRef", "list", "listItem", "paragraph", "root", "strong", "table",
      "tableCell", "tableRow", "text",
    ]);
  }, SLOW);
});

describe("the multiset text diff", () => {
  it("is empty for identical text and names the token that moved otherwise", () => {
    expect(isClean(diff(["a b c"], ["c b a"]))).toBe(true);
    const dropped = diff(["a b"], ["a b c"]);
    expect(isClean(dropped)).toBe(false);
    expect(dropped.delta).toEqual({ c: -1 });
    const duplicated = diff(["a a b"], ["a b"]);
    expect(duplicated.delta).toEqual({ a: 1 });
  });

  it("catches a mangled character, which a token count alone would not", () => {
    const clean = diff(["entry → stop"], ["entry → stop"]);
    expect(isClean(clean)).toBe(true);
    const mangled = diff(["entry ? stop"], ["entry → stop"]);
    expect(isClean(mangled)).toBe(false);
    expect(mangled.bundleTokens).toBe(mangled.referenceTokens);
  });

  it("counts every word of the glossary a reader can read", () => {
    const entries = glossaryFromContent("es", "display");
    const words = multiset(glossaryTexts(entries));
    expect(words.size).toBeGreaterThan(1000);
    const withSenses = entries.find((entry) => (entry.senses?.length ?? 0) > 1);
    expect(withSenses, "the glossary has homonyms; their senses must be counted").toBeTruthy();
    for (const sense of withSenses?.senses ?? []) {
      expect(glossaryTexts([withSenses!])).toContain(sense.definition);
    }
  });
});
