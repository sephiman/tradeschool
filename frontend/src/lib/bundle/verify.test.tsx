import { describe, expect, it } from "vitest";
import type { Nodes, Root } from "mdast";
import { annotationInputs, bareAst, lessonAst } from "@/lib/bundle/ast";
import { lessonHtml } from "@/lib/bundle/rendered";
import { blockDiff, blockTexts, bundleBlocks, diff, isClean, renderedBlocks } from "@/lib/bundle/verify";
import {
  glossaryFromContent,
  lessonMarkdown,
  manifestLessons,
  refModulesFromManifest,
  LOCALES,
  type Locale,
} from "@/test/courseContent";

/**
 * The second opinion about the bundle's text, and the three things the multiset diff beside it
 * cannot be asked.
 *
 * The multiset splits on whitespace, so whitespace is invisible to it by construction; it is a bag,
 * so order is not in it; and its reference is the web's own mdast off the same parser as the
 * bundle's, so a change to that parser moves both sides together and the diff stays empty. Each of
 * those is a fixture here: the multiset agrees with itself, and the block check does not.
 */

const SLOW = 120_000;

function blocksFromHtml(html: string): string[] {
  const host = document.createElement("div");
  host.innerHTML = html;
  return renderedBlocks(host);
}

/** What a `remark-breaks` added to the export's parser would produce: every soft break a `break`. */
function withHardBreaks(tree: Root): Root {
  const walk = (node: Nodes): void => {
    if (!("children" in node)) return;
    const children = node.children as Nodes[];
    for (const child of children) walk(child);
    node.children = children.flatMap((child) =>
      child.type === "text" && child.value.includes("\n")
        ? child.value
            .split("\n")
            .flatMap((part, index): Nodes[] =>
              index === 0
                ? [{ type: "text", value: part }]
                : [{ type: "break" }, { type: "text", value: part }],
            )
        : [child],
    ) as typeof node.children;
  };
  walk(tree);
  return tree;
}

describe("what the multiset text diff cannot be asked", () => {
  it("cannot see a soft break the export turned into a hard one", () => {
    const markdown = "alpha beta\ngamma delta";
    // The diff's two sides come off the SAME processor, so a parser change is in both of them and
    // the comparison is the bug agreeing with itself. This is the whole reason for the block check.
    const parsedWithBreaks = withHardBreaks(bareAst(markdown));
    const asTheExportComparesThem = diff(
      blockTexts(parsedWithBreaks),
      blockTexts(parsedWithBreaks),
    );
    expect(isClean(asTheExportComparesThem)).toBe(true);

    const painted = blocksFromHtml(lessonHtml(markdown));
    expect(painted).toEqual(["alpha beta gamma delta"]);
    expect(bundleBlocks(parsedWithBreaks)).toEqual(["alpha beta\ngamma delta"]);
    expect(blockDiff(bundleBlocks(parsedWithBreaks), painted)).toEqual([
      { index: 0, bundle: "alpha beta\ngamma delta", rendered: "alpha beta gamma delta" },
    ]);
    expect(blockDiff(bundleBlocks(bareAst(markdown)), painted)).toEqual([]);
  });

  it("cannot see word order, because a multiset has none", () => {
    expect(isClean(diff(["the stop is above the entry"], ["the entry is above the stop"]))).toBe(true);
    expect(blockDiff(["the stop is above the entry"], ["the entry is above the stop"])).toHaveLength(1);
  });

  it("cannot see a paragraph that split in two, because it joins nothing", () => {
    expect(isClean(diff(["one two"], ["one", "two"]))).toBe(true);
    expect(blockDiff(["one two"], ["one", "two"])).toEqual([
      { index: 0, bundle: "one two", rendered: "one" },
      { index: 1, bundle: null, rendered: "two" },
    ]);
  });
});

describe("the rendered block check", () => {
  it("reads a tight list item, a table cell and a callout as one block each", () => {
    const markdown = [
      "# Heading",
      "",
      "- first item",
      "- second item",
      "",
      "| a | b |",
      "| --- | --- |",
      "| one | two |",
      "",
      ":::note{type=tip}",
      "inside the callout",
      ":::",
      "",
      "::figure{id=f01}",
    ].join("\n");
    const expected = [
      "Heading", "first item", "second item", "a", "b", "one", "two", "inside the callout",
    ];
    expect(blocksFromHtml(lessonHtml(markdown))).toEqual(expected);
    expect(bundleBlocks(bareAst(markdown))).toEqual(expected);
  });

  it("keeps a sentence interrupted by a nested list from swallowing it", () => {
    const markdown = "- outer text\n  - inner text";
    expect(blocksFromHtml(lessonHtml(markdown))).toEqual(["outer text", "inner text"]);
    expect(bundleBlocks(bareAst(markdown))).toEqual(["outer text", "inner text"]);
  });
});

describe.each(LOCALES)("every lesson the bundle ships (%s)", (locale: Locale) => {
  it("carries the page the web paints, block for block, whitespace included", () => {
    const inputs = annotationInputs(
      glossaryFromContent(locale, "display"),
      refModulesFromManifest(locale),
      locale,
    );
    let compared = 0;
    for (const lesson of manifestLessons()) {
      const markdown = lessonMarkdown(locale, lesson.id);
      const blocks = bundleBlocks(lessonAst(markdown, lesson.id, inputs));
      const mismatches = blockDiff(blocks, blocksFromHtml(lessonHtml(markdown)));
      expect(mismatches, `${locale}/${lesson.id}`).toEqual([]);
      compared += blocks.length;
    }
    // Two empty lists compare equal, so the count is what stops a walker that stopped walking from
    // passing this as a clean course.
    expect(compared).toBeGreaterThan(manifestLessons().length * 10);
  }, SLOW);
});
