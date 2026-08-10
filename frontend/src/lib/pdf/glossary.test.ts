import { describe, expect, it } from "vitest";
import type { Content, TDocumentDefinitions } from "pdfmake/interfaces";
import type { GlossaryEntry } from "@/api/course";
import { sortGlossary } from "@/lib/glossary";
import { glossarySection, type GlossaryLabels } from "@/lib/pdf/glossary";
import { GLOSSARY_ENTRY_ID, isKeepWhole, type LayoutNode } from "@/lib/pdf/pagination";
import { courseExportFromContent, glossaryFromContent } from "@/test/courseContent";

const labels: GlossaryLabels = {
  glossary: "Glossary",
  glossaryIntro: "intro",
  alias: (canonical) => `→ ${canonical}`,
  origin: (lesson) => lesson,
  sense: (index) => `${index}. `,
};

function texts(node: unknown): string[] {
  const found: string[] = [];
  const walk = (value: unknown): void => {
    if (Array.isArray(value)) return value.forEach(walk);
    if (typeof value !== "object" || value === null) return;
    const record = value as Record<string, unknown>;
    if (typeof record.text === "string") found.push(record.text);
    Object.values(record).forEach(walk);
  };
  walk(node);
  return found;
}

const entry = (over: Partial<GlossaryEntry> & { id: string; term: string }): GlossaryEntry => ({
  origin: "m01-l1",
  originTitle: "A lesson",
  ...over,
});

describe("the printed glossary", () => {
  it("returns nothing when there are no terms, so the section never prints empty", () => {
    expect(glossarySection([], "en", labels, "section-glossary-0")).toBeNull();
  });

  it("renders an alias as a pointer, never as a repeated definition", () => {
    const terms = [
      entry({ id: "g-canon", term: "change of character", definition: "The first break." }),
      entry({ id: "g-alias", term: "CHoCH", aliasOf: { id: "g-canon", term: "change of character" } }),
    ];
    const printed = texts(glossarySection(terms, "en", labels, "s"));
    expect(printed).toContain("→ change of character");
    // The definition appears exactly once — under the canonical entry.
    expect(printed.filter((t) => t === "The first break.")).toHaveLength(1);
  });

  it("numbers a homonym's senses and names each sense's own origin", () => {
    const terms = [
      entry({
        id: "g-premium",
        term: "premium",
        origin: null,
        originTitle: null,
        senses: [
          { origin: "m19-l1", originTitle: "Derivatives", definition: "Perp above spot." },
          { origin: "m32-l1", originTitle: "Premium", definition: "Between venues." },
        ],
      }),
    ];
    const printed = texts(glossarySection(terms, "en", labels, "s"));
    expect(printed).toContain("1. ");
    expect(printed).toContain("2. ");
    expect(printed).toContain("Perp above spot.");
    // Each sense points at its OWN lesson, id upper-cased and joined to the lesson title.
    expect(printed).toContain("M19-L1 · Derivatives");
    expect(printed).toContain("M32-L1 · Premium");
  });

  it("gives every entry a keep-whole id, so a term never splits from its definition", () => {
    const section = glossarySection(
      [entry({ id: "g-a", term: "a", definition: "d" })],
      "en",
      labels,
      "s",
    ) as { stack: Content[] };
    const block = section.stack.at(-1) as { id: string };
    expect(block.id.startsWith(`${GLOSSARY_ENTRY_ID}-`)).toBe(true);
    expect(isKeepWhole({ id: block.id } as LayoutNode)).toBe(true);
  });

  it("prints in the collator's order and does not re-sort on its own terms", () => {
    // Deliberately unsorted input: the section must not simply preserve it.
    const terms = [
      entry({ id: "g-z", term: "zona dorada", definition: "d" }),
      entry({ id: "g-e", term: "emisión", definition: "d" }),
      entry({ id: "g-a", term: "apalancamiento", definition: "d" }),
    ];
    const section = glossarySection(terms, "es", labels, "s") as { stack: Content[] };
    const printedTerms = section.stack
      .slice(2) // heading + intro
      .map((node) => texts(node)[0]);
    expect(printedTerms).toEqual(sortGlossary(terms, "es").map((t) => t.term));
    expect(printedTerms).toEqual(["apalancamiento", "emisión", "zona dorada"]);
  });
});

describe("collation is shared with the app", () => {
  it.each(["en", "es"] as const)("%s: the PDF order is exactly sortGlossary's order", (locale) => {
    const terms = glossaryFromContent(locale);
    expect(terms.length).toBeGreaterThan(0);
    const section = glossarySection(terms, locale, labels, "s") as { stack: Content[] };
    const printedTerms = section.stack.slice(2).map((node) => texts(node)[0]);
    // The app page renders `sortGlossary(...)` directly; printing the same list is the guarantee.
    expect(printedTerms).toEqual(sortGlossary(terms, locale).map((t) => t.term));
  });

  it("the two locales do not share one order", () => {
    const es = sortGlossary(glossaryFromContent("es"), "es").map((t) => t.id);
    const en = sortGlossary(glossaryFromContent("en"), "en").map((t) => t.id);
    expect(new Set(es)).toEqual(new Set(en));
    expect(es).not.toEqual(en);
  });

  it("folds accents onto the base letter, so `emisión` sorts under E", () => {
    const terms = [
      entry({ id: "g-1", term: "envolvente", definition: "d" }),
      entry({ id: "g-2", term: "emisión", definition: "d" }),
      entry({ id: "g-3", term: "esperanza", definition: "d" }),
    ];
    expect(sortGlossary(terms, "es").map((t) => t.term)).toEqual([
      "emisión",
      "envolvente",
      "esperanza",
    ]);
  });
});

describe("placement in the book", () => {
  it("the real export carries the glossary the document builds from", () => {
    const exported = courseExportFromContent("es");
    expect(exported.glossary.length).toBeGreaterThan(0);
    expect(exported.glossary.some((t) => t.aliasOf)).toBe(true);
    expect(exported.glossary.some((t) => t.senses?.length)).toBe(true);
  });
});

/** Asserted from the built document in `document.test.ts`; re-exported so both files agree on it. */
export function sectionTitles(doc: TDocumentDefinitions): string[] {
  const content = Array.isArray(doc.content) ? doc.content : [doc.content];
  return content.flatMap((node) => {
    const stack = (node as { stack?: Content[] }).stack;
    const first = stack?.[0] as { style?: string; text?: string } | undefined;
    return first?.style === "blockTitle" && first.text ? [first.text] : [];
  });
}
