// @vitest-environment node
import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import yaml from "js-yaml";
import type { Root, RootContent } from "mdast";
import type {} from "mdast-util-directive";
import { remarkBlockDirectives } from "@/lib/directives";
import { CONTENT_DIR, LOCALES, lessonMarkdown, manifestLessons } from "@/test/courseContent";

/**
 * The course's markdown dialect has BLOCK directives and no inline ones.
 *
 * The inline `:name` syntax is what ate every clock time in the prose — `03:00` parsed as a `:00`
 * directive with no children and printed as `03` — so this pins its absence on the parser, where
 * both surfaces share it, rather than on the prose.
 */

const processor = unified().use(remarkParse).use(remarkGfm).use(remarkBlockDirectives);

function textDirectives(markdown: string): string[] {
  const eaten: string[] = [];
  const walk = (node: RootContent | Root): void => {
    if (node.type === "textDirective") eaten.push(`:${node.name}`);
    if ("children" in node) for (const child of node.children) walk(child);
  };
  walk(processor.parse(markdown));
  return eaten;
}

/** Every text node's value, which is what a surface has left to print. */
function plainText(markdown: string): string {
  const out: string[] = [];
  const walk = (node: RootContent | Root): void => {
    if (node.type === "text" || node.type === "inlineCode") out.push(node.value);
    if ("children" in node) for (const child of node.children) walk(child);
  };
  walk(processor.parse(markdown));
  return out.join("");
}

describe("the lesson dialect", () => {
  it("keeps a clock time literal", () => {
    expect(plainText("Tu stop está vivo a las 03:00, y no hay campana.")).toBe(
      "Tu stop está vivo a las 03:00, y no hay campana.",
    );
    expect(plainText("commonly 00:00, 08:00 and 16:00 UTC")).toBe("commonly 00:00, 08:00 and 16:00 UTC");
  });

  it("keeps a ratio literal", () => {
    expect(plainText("That is a 3:1 bid imbalance.")).toBe("That is a 3:1 bid imbalance.");
  });

  it("parses no inline directive at all, whatever follows the colon", () => {
    expect(textDirectives("a las 03:00 y un :note suelto y R:R")).toEqual([]);
  });

  it("still parses the three block directives the course writes", () => {
    const tree = processor.parse(":::note{type=warning}\nCuidado.\n:::\n\n::figure{id=fig-demo}\n");
    expect(tree.children.map((node) => node.type)).toEqual(["containerDirective", "leafDirective"]);
  });
});

/** Every markdown string a surface renders through the dialect: lesson prose and exercise prompts. */
function renderedStrings(): { where: string; markdown: string }[] {
  const strings = LOCALES.flatMap((locale) =>
    manifestLessons().map((lesson) => ({
      where: `${locale}/lessons/${lesson.id}.md`,
      markdown: lessonMarkdown(locale, lesson.id),
    })),
  );
  const dir = resolve(CONTENT_DIR, "exercises");
  for (const file of readdirSync(dir).filter((name) => name.endsWith(".yaml")).sort()) {
    const doc = yaml.load(readFileSync(resolve(dir, file), "utf8")) as {
      variants?: { id: string; prompt?: Record<string, string> }[];
    };
    for (const variant of doc.variants ?? []) {
      for (const locale of LOCALES) {
        const prompt = variant.prompt?.[locale];
        if (prompt) strings.push({ where: `exercises/${file} ${variant.id} (${locale})`, markdown: prompt });
      }
    }
  }
  return strings;
}

describe("the authored course", () => {
  it("has nothing the parser swallows", () => {
    // A prose-integrity guard, like the reference report's zero-dangling assertion: no authored
    // string may contain a sequence the dialect drops instead of printing.
    const strings = renderedStrings();
    // A floor, not a fingerprint: an empty walk would "pass" against nothing.
    expect(strings.length).toBeGreaterThan(80);
    const swallowed = strings.flatMap(({ where, markdown }) =>
      textDirectives(markdown).map((eaten) => `${where}: ${eaten}`),
    );
    expect(swallowed).toEqual([]);
  });
});
