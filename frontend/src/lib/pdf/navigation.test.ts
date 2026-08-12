// @vitest-environment node
import { describe, expect, it } from "vitest";
import type { TDocumentDefinitions } from "pdfmake/interfaces";
import { buildCourseDocument, lessonSections } from "@/lib/pdf/document";
import { DEST } from "@/lib/pdf/pagination";
import { PRINT } from "@/lib/pdf/page";
import { buildLinkReport } from "@/lib/glossary/report";
import { buildRefReport } from "@/lib/refs/report";
import {
  courseExportFromContent,
  figureDirectives,
  glossaryFromContent,
  lessonMarkdown,
  manifestLessons,
  readManifest,
  refModulesFromManifest,
  stubFigures,
  LOCALES,
  type Locale,
} from "@/test/courseContent";
import { printExercisesFromContent, stubExerciseCharts } from "@/test/printExercises";
import { testPdfLabels } from "@/test/printLabels";
import { testPng } from "@/test/png";

/**
 * The book's internal navigation: term links, glossary anchors, the outline, and the exercise pair.
 *
 * Asserted on the built document rather than the rendered bytes, because that is where a dangling
 * link is still readable — in the PDF it is a link annotation that silently goes nowhere.
 */

const STUB_CHART_PNG = testPng(1520, 600);

interface Node {
  id?: string;
  text?: unknown;
  linkToDestination?: string;
  outline?: boolean;
  outlineText?: string;
  outlineParentId?: string;
  tocItem?: boolean;
  decoration?: string;
  decorationStyle?: string;
  decorationColor?: string;
  color?: string;
}

/** Walking 36 lessons is slow enough to outlast vitest's 5s default when the whole suite runs. */
const SLOW = 120_000;

const documents = new Map<Locale, TDocumentDefinitions>();
function build(locale: Locale): TDocumentDefinitions {
  const existing = documents.get(locale);
  if (existing) return existing;
  const exercises = printExercisesFromContent(locale);
  const doc = buildCourseDocument({
    courseTitle: "T",
    courseDescription: "D",
    export: courseExportFromContent(locale),
    figures: stubFigures(figureDirectives(locale)),
    exercises,
    exerciseCharts: stubExerciseCharts(exercises, STUB_CHART_PNG),
    labels: testPdfLabels(locale),
  });
  documents.set(locale, doc);
  return doc;
}

/** Every node under `root`, in document order. */
function walkNodes(root: unknown): Node[] {
  const found: Node[] = [];
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) return node.forEach(walk);
    if (typeof node !== "object" || node === null) return;
    found.push(node as Node);
    for (const value of Object.values(node)) walk(value);
  };
  walk(root);
  return found;
}

function nodes(doc: TDocumentDefinitions): Node[] {
  return walkNodes(doc.content);
}

/** Ids that actually become a PDF destination: pdfmake writes one only where a text line carries it. */
function destinations(doc: TDocumentDefinitions): Set<string> {
  return new Set(
    nodes(doc)
      .filter((node) => typeof node.id === "string" && node.text !== undefined)
      .map((node) => node.id as string),
  );
}

function links(doc: TDocumentDefinitions): Node[] {
  return nodes(doc).filter((node) => typeof node.linkToDestination === "string");
}

describe.each(LOCALES)("internal links (%s)", (locale) => {
  it("has no dangling link: every target is an id on a text node in the same document", () => {
    const doc = build(locale);
    const anchors = destinations(doc);
    const dangling = [
      ...new Set(links(doc).map((node) => node.linkToDestination as string)),
    ].filter((target) => !anchors.has(target));
    expect(dangling).toEqual([]);
  });

  it("links a real share of the book, so 'no dangling links' is not vacuous", () => {
    expect(links(build(locale)).length).toBeGreaterThan(200);
  });

  it("anchors every glossary entry, whether the prose links to it or not", () => {
    const anchors = destinations(build(locale));
    const missing = glossaryFromContent(locale)
      .map((entry) => DEST.term(entry.id))
      .filter((id) => !anchors.has(id));
    expect(missing).toEqual([]);
  });

  it("links exactly the terms the golden report says it links", () => {
    // The report and the book are two readings of one annotator; if they ever disagree, the golden
    // stops being evidence about what a reader sees. Scoped to the LESSON sections: the glossary's
    // own alias pointers are `gdest-` links too, and they are not prose marks.
    const linked = lessonSections(build(locale))
      .flatMap(walkNodes)
      .map((node) => node.linkToDestination)
      .filter((target): target is string => target?.startsWith("gdest-") ?? false);
    const report = buildLinkReport(
      manifestLessons().map((lesson) => ({ id: lesson.id, markdown: lessonMarkdown(locale, lesson.id) })),
      glossaryFromContent(locale),
      locale,
    );
    const expected = report.rows.filter((row) => row.flag === "WP").map((row) => DEST.term(row.termId));
    expect([...linked].sort()).toEqual([...expected].sort());
  }, SLOW);

  it("links exactly the lesson references the golden report says it links", () => {
    // Same drift rule as the terms: the report and the book are two readings of one annotator.
    // Scoped to the lesson sections, where `odest-` targets can only be prose reference marks — the
    // glossary section's own origin pointers are `odest-` links too, and they are not prose.
    const linked = lessonSections(build(locale))
      .flatMap(walkNodes)
      .map((node) => node.linkToDestination)
      .filter((target): target is string => target?.startsWith("odest-") ?? false);
    const modules = refModulesFromManifest(locale);
    const displayByKey = new Map(
      modules.flatMap((m) => [[m.key ?? m.id, m.id] as const, ...m.lessons.map((l) => [l.key ?? l.id, l.id] as const)]),
    );
    const report = buildRefReport(
      manifestLessons().map((lesson) => ({
        id: lesson.id,
        key: lesson.key ?? lesson.id,
        markdown: lessonMarkdown(locale, lesson.id),
      })),
      modules,
      locale,
    );
    const expected = report.rows.map((row) => DEST.outline(displayByKey.get(row.targetKey) as string));
    expect([...linked].sort()).toEqual([...expected].sort());
    expect(expected.length).toBeGreaterThan(150);
  }, SLOW);

  it("styles a lesson reference as a printed cross-reference, never as a web link", () => {
    const ref = lessonSections(build(locale))
      .flatMap(walkNodes)
      .find((node) => node.linkToDestination?.startsWith("odest-"));
    expect(ref).toBeDefined();
    expect(ref?.decoration).toBe("underline");
    expect(ref?.decorationStyle).toBe("dotted");
    expect(ref?.decorationColor).toBe(PRINT.muted);
    expect(ref?.color).not.toBe(PRINT.link);
  });

  it("styles a term link as a printed cross-reference, never as a web link", () => {
    const term = links(build(locale)).find((node) =>
      (node.linkToDestination as string).startsWith("gdest-"),
    );
    expect(term).toBeDefined();
    expect(term?.decoration).toBe("underline");
    expect(term?.decorationStyle).toBe("dotted");
    expect(term?.decorationColor).toBe(PRINT.muted);
    expect(term?.color).not.toBe(PRINT.link);
  });

  it("pairs every printed exercise with its answer, in both directions", () => {
    const doc = build(locale);
    // Addressed by the printed number, not the id: `render.test.ts` requires that no exercise id
    // reaches the file, and a destination name is written into it.
    const numbers = printExercisesFromContent(locale).lessons.flatMap((lesson) =>
      lesson.exercises.map((exercise) => exercise.number),
    );
    expect(numbers.length).toBeGreaterThan(100);
    expect(new Set(numbers).size, "two exercises print the same number").toBe(numbers.length);
    const byTarget = new Set(links(doc).map((node) => `${node.id}→${node.linkToDestination}`));
    for (const number of numbers) {
      expect(byTarget.has(`${DEST.exercise(number)}→${DEST.answer(number)}`), `${number} → answer`).toBe(true);
      expect(byTarget.has(`${DEST.answer(number)}→${DEST.exercise(number)}`), `${number} answer → back`).toBe(true);
    }
  });

  it("makes the glossary's own pointers clickable too — origins, and an alias's canonical", () => {
    // The glossary is a reference, and in a navigable book every pointer in it should be followable:
    // "taught in M19-L1" reaches that lesson, and "CHoCH → change of character" reaches that entry.
    const targets = new Set(links(build(locale)).map((node) => node.linkToDestination));
    const entries = glossaryFromContent(locale);
    const withOrigin = entries.filter((entry) => entry.origin && !entry.senses?.length);
    expect(withOrigin.length).toBeGreaterThan(100);
    for (const entry of withOrigin) {
      expect(targets.has(DEST.outline(entry.origin as string)), `${entry.id} → its lesson`).toBe(true);
    }
    for (const alias of entries.filter((entry) => entry.aliasOf)) {
      expect(targets.has(DEST.term(alias.aliasOf?.id as string)), `${alias.id} → canonical`).toBe(true);
    }
    for (const sense of entries.flatMap((entry) => entry.senses ?? [])) {
      expect(targets.has(DEST.outline(sense.origin)), `a sense → ${sense.origin}`).toBe(true);
    }
  });

  it("gives every table-of-contents entry a stable id of its own to point at", () => {
    // pdfmake links a TOC row to the heading's id, inventing `toc-_default_-N` when there is none.
    // Ours are content ids, so a TOC destination survives a heading moving in the book.
    const anonymous = nodes(build(locale)).filter((node) => node.tocItem && typeof node.id !== "string");
    expect(anonymous).toEqual([]);
  });
});

describe.each(LOCALES)("the document outline (%s)", (locale) => {
  /** The bookmark tree as pdfmake will build it: an item's parent is the node named by its id. */
  function outline(doc: TDocumentDefinitions): { label: string; children: string[] }[] {
    const items = nodes(doc).filter((node) => node.outline === true);
    const label = (node: Node) => node.outlineText ?? (node.text as string);
    const byId = new Map(items.map((node) => [node.id as string, label(node)]));
    const roots: { label: string; children: string[] }[] = [];
    const under = new Map<string, string[]>();
    for (const item of items) {
      const parent = item.outlineParentId;
      if (parent === undefined) roots.push({ label: label(item), children: [] });
      else under.set(parent, [...(under.get(parent) ?? []), label(item)]);
    }
    for (const item of items) {
      const parent = item.outlineParentId;
      if (parent !== undefined) continue;
      const found = roots.find((root) => root.label === byId.get(item.id as string));
      if (found) found.children = under.get(item.id as string) ?? [];
    }
    return roots;
  }

  it("nests exactly as course.yaml does: blocks, then their modules", () => {
    const manifest = readManifest();
    const tree = outline(build(locale));
    const blocks = tree.slice(0, manifest.blocks.length);
    expect(blocks.map((block) => block.label)).toEqual(
      manifest.blocks.map((block) => block.title[locale]),
    );
    blocks.forEach((block, index) => {
      expect(block.children).toEqual(
        manifest.blocks[index].modules.map(
          (module) => `${module.id.toUpperCase()} · ${module.title[locale]}`,
        ),
      );
    });
  });

  it("hangs every lesson under its own module", () => {
    const doc = build(locale);
    const items = nodes(doc).filter((node) => node.outline === true);
    for (const module of readManifest().blocks.flatMap((block) => block.modules)) {
      for (const lesson of module.lessons ?? []) {
        const item = items.find((node) => node.id === DEST.outline(lesson.id));
        expect(item, `${lesson.id} is not in the outline`).toBeDefined();
        expect(item?.outlineParentId).toBe(DEST.outline(module.id));
        expect(item?.outlineText).toBe(lesson.title[locale]);
      }
    }
  });

  it("ends with the glossary and the answer key, beside the blocks and not inside one", () => {
    const labels = testPdfLabels(locale);
    const tree = outline(build(locale));
    expect(tree.map((root) => root.label).slice(-2)).toEqual([labels.glossary, labels.answerKey]);
  });

  it("keeps the 161 glossary entries OUT of the outline", () => {
    const items = nodes(build(locale)).filter((node) => node.outline === true);
    expect(items.filter((node) => String(node.id).startsWith(DEST.term("")))).toEqual([]);
  });
});
