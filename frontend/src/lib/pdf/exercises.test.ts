import { describe, expect, it } from "vitest";
import type { PrintExercise } from "@/api/course";
import {
  answerEntry,
  answerLines,
  exerciseBlock,
  letter,
  printDate,
  printPrice,
  promptContent,
} from "@/lib/pdf/exercises";
import { testPdfLabels } from "@/test/printLabels";

/**
 * How one printed exercise reads, per kind — and, for each, how the answer at the back points back at
 * it. The join is the subject: the key cites the letter the page gave an option, not the option's
 * internal id, and quotes the price the chart plots at the bar it names.
 */

const labels = testPdfLabels("en");
const chart = () => "PNG";

/** Just the typeset text: the `text` (or `image`) of every node, in order — never a style name. A
 *  markdown-rendered prompt's `text` is a list of styled runs, which joins back into its sentence. */
function texts(node: unknown, found: string[] = []): string[] {
  if (Array.isArray(node)) node.forEach((child) => texts(child, found));
  else if (typeof node === "object" && node !== null) {
    const entry = node as { text?: unknown; image?: unknown };
    if (typeof entry.text === "string") found.push(entry.text);
    else if (Array.isArray(entry.text)) {
      found.push(entry.text.map((run) => (run as { text?: string }).text ?? "").join(""));
    }
    if (typeof entry.image === "string") found.push(entry.image);
    for (const value of Object.values(node)) {
      if (value !== entry.text && value !== entry.image) texts(value, found);
    }
  }
  return found;
}

function base(overrides: Partial<PrintExercise>): PrintExercise {
  return {
    id: "m01-ex-1",
    number: "1.1",
    type: "quiz",
    isChart: false,
    seed: 1,
    prompt: "The prompt.",
    payload: {},
    answer: { kind: "single_choice" },
    ...overrides,
  };
}

describe("option letters", () => {
  it("run a, b, c … and keep going past the alphabet", () => {
    expect([0, 1, 25].map(letter)).toEqual(["a", "b", "z"]);
    expect(letter(26)).toBe("aa");
  });
});

describe("a single-choice question", () => {
  const exercise = base({
    payload: {
      kind: "single_choice",
      options: [
        { id: "b", text: "wrong" },
        { id: "a", text: "right" },
      ],
    },
    answer: { kind: "single_choice", optionIds: ["a"], explanation: "because" },
  });

  it("prints its number, its prompt and its options in the order they were dealt", () => {
    const printed = texts(exerciseBlock(exercise, labels, chart));
    expect(printed.slice(0, 2)).toEqual(["Exercise 1.1", "The prompt."]);
    expect(printed).toContain("a)");
    expect(printed).toContain("wrong"); // option `b` was dealt first, so it is printed as a)
    expect(printed).toContain("right");
  });

  it("is answered by the letter the page printed, not by the option's id", () => {
    // The correct option is `a`, but it was dealt SECOND, so the answer is "b)". An answer key that
    // echoed the id would be confidently wrong on every shuffled question in the book.
    expect(answerLines(exercise, labels)).toEqual(["b)  right"]);
  });

  it("carries the explanation the content provides", () => {
    expect(texts(answerEntry(exercise, labels)).join(" ")).toContain("Why: because");
  });
});

describe("a prompt written in markdown", () => {
  it("prints as the app renders it, not as asterisks", () => {
    // Half the chart prompts emphasise the words the question turns on ("**close beyond it and
    // hold**"); the app runs the prompt through `<Prose>`, and printing it raw shows the markup.
    const exercise = base({ prompt: "Did it **close beyond** the level, or only `poke` it?" });
    const printed = texts(exerciseBlock(exercise, labels, chart)).join(" ");
    expect(printed).not.toContain("**");
    expect(printed).toContain("close beyond");
    const runs = promptContent(exercise.prompt, exercise.id)[0] as { text: { text: string; bold?: boolean }[] };
    expect(runs.text.find((run) => run.text === "close beyond")?.bold).toBe(true);
  });
});

describe("a true/false question", () => {
  const exercise = base({
    payload: { kind: "true_false" },
    answer: { kind: "true_false", value: false },
  });

  it("prints the claim and asks for a verdict, with no options to letter", () => {
    const printed = texts(exerciseBlock(exercise, labels, chart));
    expect(printed).toContain("True or false?");
    expect(printed).not.toContain("a)");
  });

  it("is answered with the word, not the boolean", () => {
    expect(answerLines(exercise, labels)).toEqual(["False"]);
  });
});

describe("a multi-select question", () => {
  const exercise = base({
    payload: {
      kind: "multi_select",
      options: [
        { id: "a", text: "one" },
        { id: "b", text: "two" },
        { id: "c", text: "three" },
      ],
    },
    // As the server reveals them: correct ids sorted, which need not be the order they were dealt in.
    answer: { kind: "multi_select", optionIds: ["c", "a"] },
  });

  it("says how many to pick", () => {
    expect(texts(exerciseBlock(exercise, labels, chart))).toContain("Select all that apply.");
  });

  it("lists every correct option, in the order the page dealt them", () => {
    // `a) … c)` and never `c) … a)`: a key whose letters run backwards reads as a mistake.
    expect(answerLines(exercise, labels)).toEqual(["a)  one", "c)  three"]);
  });
});

describe("an ordering question", () => {
  const exercise = base({
    payload: {
      kind: "ordering",
      items: [
        { id: "close", text: "the close" },
        { id: "reach", text: "the reach" },
        { id: "volume", text: "the volume" },
      ],
    },
    answer: { kind: "ordering", order: ["reach", "close", "volume"] },
  });

  it("prints the items lettered in their shuffled order", () => {
    const printed = texts(exerciseBlock(exercise, labels, chart));
    expect(printed).toContain("Put these in the right order.");
    expect(printed.filter((t) => /^[abc]\)$/.test(t))).toEqual(["a)", "b)", "c)"]);
  });

  it("is answered as positions, each naming the letter it refers to", () => {
    expect(answerLines(exercise, labels)).toEqual([
      "1.  b)  the reach",
      "2.  a)  the close",
      "3.  c)  the volume",
    ]);
  });
});

describe("a matching question", () => {
  const exercise = base({
    payload: {
      kind: "matching",
      lefts: [
        { id: "l0", text: "rising" },
        { id: "l1", text: "falling" },
      ],
      rights: [
        { id: "r0", text: "bitcoin winning" },
        { id: "r1", text: "ether winning" },
      ],
    },
    answer: { kind: "matching", pairs: { l1: "r0", l0: "r1" } },
  });

  it("prints the items numbered and the options lettered, so a pair can be named", () => {
    const printed = texts(exerciseBlock(exercise, labels, chart)).join("\n");
    expect(printed).toContain("1.  rising");
    expect(printed).toContain("a)  bitcoin winning");
  });

  it("is answered down the printed list of items, whatever order the pairs arrived in", () => {
    expect(answerLines(exercise, labels)).toEqual([
      "1.  rising → b)  ether winning",
      "2.  falling → a)  bitcoin winning",
    ]);
  });
});

describe("a calculation", () => {
  const exercise = base({
    type: "calculation",
    payload: {
      kind: "multiple_choice",
      unit: "USDT",
      options: [
        { id: "o0", value: "-6.80" },
        { id: "o1", value: "6.80" },
      ],
    },
    answer: {
      kind: "calculation",
      optionIds: ["o1"],
      numericValue: "6.80",
      unit: "USDT",
      steps: ["funding = notional × rate", "        = 6.80"],
    },
  });

  it("prints its options as values carrying their unit", () => {
    expect(texts(exerciseBlock(exercise, labels, chart))).toContain("-6.80 USDT");
  });

  it("is answered with the letter, the value and the working", () => {
    expect(answerLines(exercise, labels)).toEqual(["b)  6.80 USDT"]);
    expect(texts(answerEntry(exercise, labels)).join(" ")).toContain(
      "Working: funding = notional × rate  ·          = 6.80",
    );
  });
});

describe("a chart question", () => {
  const exercise = base({
    type: "pattern_chart",
    isChart: true,
    payload: {
      series: { time: [1], open: [1], high: [2], low: [0], close: [1], volume: [1] },
      choices: ["zone_respected", "no_zone"],
    },
    answer: {
      kind: "chart",
      label: "zone_respected",
      anchors: [{ index: 0, time: 1711491200, kind: "low", label: "origin", price: 106.94 }],
      zones: [{ low: 106.9, high: 108.2, kind: "origin", label: "" }],
    },
  });

  it("prints the captured chart above its localized choices", () => {
    const printed = texts(exerciseBlock(exercise, labels, chart));
    expect(printed).toContain("PNG");
    expect(printed).toContain("Origin zone respected"); // never the raw injector label
    expect(printed).toContain("No zone — nothing broke structure");
  });

  it("is answered by the resolution, anchored to the printed chart's own prices", () => {
    expect(answerLines(exercise, labels)).toEqual([
      "Origin zone respected",
      "Origin — 106.94 · 26/03/2024",
      "Origin zone — 106.90 … 108.20",
    ]);
  });

  it("stops when the chart was never captured", () => {
    expect(() =>
      exerciseBlock(exercise, labels, () => {
        throw new Error(`exercise ${exercise.id}'s chart was not rendered for this export`);
      }),
    ).toThrowError(/m01-ex-1's chart was not rendered/);
  });
});

describe("printed numbers", () => {
  it("keep two decimals, locale-neutrally, so the key reads what the candle carries", () => {
    expect(printPrice(41230.5)).toBe("41230.50");
    expect(printPrice(115.09)).toBe("115.09");
  });

  it("date a bar the way the chart's own axis does (dd/MM/yyyy, UTC)", () => {
    expect(printDate(1711491200)).toBe("26/03/2024");
  });
});
