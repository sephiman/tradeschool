import { describe, expect, it } from "vitest";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import type { Root } from "mdast";
import type { GlossaryEntry } from "@/api/course";
import { remarkBlockDirectives } from "@/lib/directives";
import { annotateLesson, GLOSSARY_TERM, type TermMark } from "@/lib/glossary/annotate";
import { buildTermIndex, derivedVariants } from "@/lib/glossary/terms";

/** The annotator's promises: which occurrence is marked, and which are deliberately left alone. */

const processor = unified().use(remarkParse).use(remarkGfm).use(remarkBlockDirectives);

function entry(id: string, term: string, extra: Partial<GlossaryEntry> = {}): GlossaryEntry {
  return { id, term, origin: "m01-l1", originTitle: null, definition: "d", ...extra };
}

/** One lesson through the annotator, with the caller-owned `marked` set the policies differ by. */
function annotate(markdown: string, lessonId: string, entries: GlossaryEntry[], marked = new Set<string>()) {
  const tree = processor.parse(markdown) as Root;
  const marks = annotateLesson(tree, { lessonId, terms: buildTermIndex(entries, "en"), marked });
  return { tree, marks, marked };
}

/** Every marked run in the tree, in reading order — what a renderer would turn into a link. */
function marked(tree: Root): { termId: string; text: string }[] {
  const found: { termId: string; text: string }[] = [];
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) return node.forEach(walk);
    if (typeof node !== "object" || node === null) return;
    const n = node as { type?: string; termId?: string; children?: unknown[] };
    if (n.type === GLOSSARY_TERM) {
      found.push({ termId: n.termId as string, text: (n.children?.[0] as { value: string }).value });
      return;
    }
    if (n.children) walk(n.children);
  };
  walk((tree as unknown as { children: unknown[] }).children);
  return found;
}

describe("which occurrence gets marked", () => {
  const funding = entry("g-funding", "funding", { origin: "m04-l1" });
  const lesson = "Funding is paid hourly.\n\nThe funding rate flips, and funding is the cost.\n";

  it("marks the first occurrence in a lesson and leaves the rest as prose", () => {
    const { tree, marks } = annotate(lesson, "m05-l1", [funding]);
    expect(marked(tree)).toEqual([{ termId: "g-funding", text: "Funding" }]);
    expect(marks).toHaveLength(1);
  });

  it("marks per lesson when each lesson gets its own set — the web's rule", () => {
    const seen = ["m05-l1", "m06-l1"].map((id) => annotate(lesson, id, [funding]).marks.length);
    expect(seen).toEqual([1, 1]);
  });

  it("marks once across the course when one set is carried through — the PDF's rule", () => {
    const carried = new Set<string>();
    const seen = ["m05-l1", "m06-l1"].map(
      (id) => annotate(lesson, id, [funding], carried).marks.length,
    );
    expect(seen).toEqual([1, 0]);
  });

  it("never marks a term in the lesson it points back at", () => {
    const { tree, marks } = annotate(lesson, "m04-l1", [funding]);
    expect(marked(tree)).toEqual([]);
    expect(marks).toEqual([]);
  });

  it("spends the term's one PDF slot on its first occurrence even when that lesson vetoes it", () => {
    // The book meets `funding` first in the lesson that teaches it, so the PDF links it nowhere —
    // correct, not a bug. The web, whose slot resets each lesson, still marks it in m05-l1.
    const carried = new Set<string>();
    const inOrder = ["m04-l1", "m05-l1"].map((id) => annotate(lesson, id, [funding], carried).marks);
    expect(inOrder.flat()).toEqual([]);
    expect(["m04-l1", "m05-l1"].map((id) => annotate(lesson, id, [funding]).marks.length)).toEqual([0, 1]);
  });

  it("never marks a homonym in ANY of its senses' lessons", () => {
    const premium = entry("g-premium", "premium", {
      origin: null,
      senses: [
        { origin: "m19-l1", originTitle: null, definition: "a" },
        { origin: "m32-l1", originTitle: null, definition: "b" },
      ],
    });
    const text = "The premium is wide.";
    expect(annotate(text, "m19-l1", [premium]).marks).toEqual([]);
    expect(annotate(text, "m32-l1", [premium]).marks).toEqual([]);
    expect(annotate(text, "m23-l1", [premium]).marks).toHaveLength(1);
  });

  it("never marks an alias in the lesson its CANONICAL entry points back at", () => {
    // Linking `CHoCH` to an entry that says "see change of character, taught in m34-l1" while the
    // reader is in m34-l1 is the same loop, one hop longer.
    const canonical = entry("g-change-of-character", "change of character", { origin: "m34-l1" });
    const alias = entry("g-choch", "CHoCH", {
      origin: "m33-l1",
      definition: undefined,
      aliasOf: { id: "g-change-of-character", term: "change of character" },
    });
    expect(annotate("A CHoCH prints.", "m34-l1", [canonical, alias]).marks).toEqual([]);
    expect(annotate("A CHoCH prints.", "m33-l1", [canonical, alias]).marks).toEqual([]);
    expect(annotate("A CHoCH prints.", "m32-l1", [canonical, alias]).marks).toHaveLength(1);
  });
});

describe("what counts as an occurrence", () => {
  it("is anchored to word boundaries: EMA inside `sistema` is not an EMA", () => {
    const ema = entry("g-ema", "EMA", { origin: "m10-l1" });
    expect(annotate("El sistema no es una cinemateca.", "m05-l1", [ema]).marks).toEqual([]);
    expect(annotate("The EMA slopes up.", "m05-l1", [ema]).marks).toHaveLength(1);
  });

  it("does not mark half of a hyphenated compound, but a number-prefixed one is still the term", () => {
    const custody = entry("g-custody", "custody", { origin: "m31-l1" });
    expect(annotate("That is self-custody.", "m05-l1", [custody]).marks).toEqual([]);
    expect(annotate("Who holds custody?", "m05-l1", [custody]).marks).toHaveLength(1);

    const ema = entry("g-ema", "EMA", { origin: "m10-l1" });
    expect(annotate("a rising 50-EMA", "m05-l1", [ema]).marks).toHaveLength(1);
  });

  it("matches a multi-word term across the prose's ~100-column hard wrap", () => {
    const book = entry("g-order-book", "order book", { origin: "m02-l1" });
    const wrapped = "Liquidity rests in the order\nbook at that hour.";
    expect(annotate(wrapped, "m05-l1", [book]).marks.map((m) => m.text)).toEqual(["order\nbook"]);
  });

  it("matches the derived plural, and an authored list replaces the derived pair outright", () => {
    expect(derivedVariants("candle", "en")).toEqual(["candle", "candles"]);
    expect(derivedVariants("vela", "es")).toEqual(["vela", "velas"]);
    expect(derivedVariants("cross", "en")).toEqual(["cross", "crosses"]);
    // An acronym pluralises to itself here, so it gets exactly one form.
    expect(derivedVariants("RSI", "en")).toEqual(["RSI"]);

    const candle = entry("g-candle", "candle", { origin: "m03-l1" });
    expect(annotate("Three candles later.", "m05-l1", [candle]).marks.map((m) => m.text)).toEqual([
      "candles",
    ]);

    const long = entry("g-long", "long", { origin: "m04-l1", match: ["longs", "go long"] });
    expect(annotate("A long wait, then longs unwind.", "m05-l1", [long]).marks.map((m) => m.text)).toEqual(
      ["longs"],
    );
  });

  it("is case-insensitive but keeps the prose's own casing in the marked text", () => {
    const candle = entry("g-candle", "candle", { origin: "m03-l1" });
    expect(annotate("Candles close.", "m05-l1", [candle]).marks.map((m) => m.text)).toEqual(["Candles"]);
  });

  it("skips headings, code spans, code blocks and link text", () => {
    const funding = entry("g-funding", "funding", { origin: "m04-l1" });
    const markdown = [
      "# The funding rate",
      "",
      "Use `funding` in the formula.",
      "",
      "```\nfunding = x\n```",
      "",
      "See [the funding docs](https://example.com).",
      "",
      "Then funding settles.",
    ].join("\n");
    const { marks } = annotate(markdown, "m05-l1", [funding]);
    expect(marks).toHaveLength(1);
    expect(marks[0].context).toContain("Then «funding» settles.");
  });

  it("marks inside a callout and inside bold, where the prose actually introduces terms", () => {
    const funding = entry("g-funding", "funding", { origin: "m04-l1" });
    const bold = annotate("A **funding** payment.", "m05-l1", [funding]);
    expect(marked(bold.tree)).toEqual([{ termId: "g-funding", text: "funding" }]);

    const callout = annotate(":::note{type=info}\nThe funding leg.\n:::\n", "m05-l1", [funding]);
    expect(callout.marks).toHaveLength(1);
  });

  it("does not detect a term split by markup, and marks its next clean occurrence instead", () => {
    const book = entry("g-order-book", "order book", { origin: "m02-l1" });
    const { marks } = annotate("The **order** book is thin. A deeper order book helps.", "m05-l1", [book]);
    expect(marks.map((m) => m.text)).toEqual(["order book"]);
    expect(marks[0].context).toContain("A deeper «order book» helps");
  });
});

describe("overlapping terms", () => {
  const block = entry("g-order-block", "order block", { origin: "m34-l1" });
  const order = entry("g-order", "order", { origin: "m02-l1" });

  it("gives the longest term the span it covers", () => {
    const { marks } = annotate("Price left an order block behind.", "m05-l1", [order, block]);
    expect(marks.map((m) => m.termId)).toEqual(["g-order-block"]);
  });

  it("still shadows the shorter term when the longer one turns out to be unmarkable there", () => {
    // In `order block`'s own lesson the phrase is not linked — and `order` must not be linked inside
    // it either: a link on half a term reads as a mistake.
    const { marks } = annotate("Price left an order block behind.", "m34-l1", [order, block]);
    expect(marks).toEqual([]);
  });
});

describe("opting out", () => {
  it("honours `link: false` — the term is never a candidate anywhere", () => {
    const base = entry("g-base", "base", { origin: "m19-l1", link: false });
    expect(buildTermIndex([base], "en")).toEqual([]);
    expect(annotate("The base widens.", "m05-l1", [base]).marks).toEqual([]);
  });

  it("honours `linkExcept` for the named lessons only", () => {
    const long = entry("g-long", "long", { origin: "m04-l1", linkExcept: ["m01-l1"] });
    expect(annotate("A long position.", "m01-l1", [long]).marks).toEqual([]);
    expect(annotate("A long position.", "m02-l1", [long]).marks).toHaveLength(1);
  });

  it("does NOT spend the term's slot on an excluded lesson, the way an origin does", () => {
    // `linkExcept` says the word there is a false friend — `Wall Street`, `base de datos` — so it is
    // not an occurrence at all and the book still links the term at its next real one.
    const wall = entry("g-wall", "wall", { origin: "m31-l1", linkExcept: ["m17-l1"] });
    const carried = new Set<string>();
    const pdf = ["m17-l1", "m18-l1"].map(
      (id) => annotate("A wall of resting size.", id, [wall], carried).marks.length,
    );
    expect(pdf).toEqual([0, 1]);
  });
});

describe("the mark the report records", () => {
  it("names the lesson, the term, the matched text and one line of context", () => {
    const funding = entry("g-funding", "funding", { origin: "m04-l1" });
    const { marks } = annotate("The\nperpetual pays funding every eight hours.", "m05-l1", [funding]);
    expect(marks).toEqual<TermMark[]>([
      {
        lessonId: "m05-l1",
        termId: "g-funding",
        text: "funding",
        context: "The perpetual pays «funding» every eight hours.",
      },
    ]);
  });
});
