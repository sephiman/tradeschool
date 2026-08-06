import type { Content, ContentStack, TableCell } from "pdfmake/interfaces";
import type { OptionView } from "@/api/exercises";
import type { PrintAnchor, PrintExercise, PrintZone } from "@/api/course";
import { lessonToContent } from "@/lib/pdf/markdown";
import { ANSWER_ID, printedId, withId } from "@/lib/pdf/pagination";
import { PRINT, contentWidth } from "@/lib/pdf/page";

/**
 * Printed exercises and the answer key, as pure pdfmake content.
 *
 * Everything a reader needs to answer is on the page; everything that answers it is at the back. The
 * two halves are built from the SAME `PrintExercise` objects, and the key addresses the page through
 * it: an answer names option *ids*, which are resolved here against the very option list that was
 * laid out, so the key cannot cite a "b)" the page does not print. Chart answers quote prices the
 * server already indexed out of the published series.
 *
 * No i18next: like `document.ts`, every word arrives through `ExerciseLabels`, so both locales are
 * buildable — and assertable — in a test.
 */

/** The letters options are printed under. Beyond 26 options (nothing comes close) it wraps to aa, ab. */
export function letter(index: number): string {
  const alphabet = "abcdefghijklmnopqrstuvwxyz";
  if (index < alphabet.length) return alphabet[index];
  return `${alphabet[Math.floor(index / alphabet.length) - 1]}${alphabet[index % alphabet.length]}`;
}

export interface ExerciseLabels {
  /** Section heading above a lesson's exercises. */
  exercises: string;
  /** "Exercise 11.5" */
  exercise: (number: string) => string;
  /** The note a lesson carries when some of its exercises could not be printed. */
  excluded: (count: number) => string;
  answerKey: string;
  answerKeyIntro: string;
  working: string;
  why: string;
  trueLabel: string;
  falseLabel: string;
  trueFalseHint: string;
  selectAllHint: string;
  orderingHint: string;
  matchingHint: string;
  /** A chart exercise's choice, localized: `divergence.*` for the divergence charts, `chartLabel.*`
   *  for the pattern charts — the same two namespaces the app reads. */
  chartChoice: (label: string, isDivergence: boolean) => string;
  /** A ground-truth marker's name (`chartMarker.*`, falling back to the raw label). */
  marker: (raw: string) => string;
  /** A shaded zone's name (`band.<label>` -> `band.<kind>` -> raw), as the app resolves it. */
  zone: (label: string, kind: string) => string;
}

/** `exerciseId` is not a pdfmake property — the renderer ignores it, and it is what lets the tests
 *  check "every exercise is printed once, after its lesson" on the document itself. */
export interface ExerciseBlock extends ContentStack {
  exerciseId: string;
  exerciseNumber: string;
}

export interface AnswerEntry extends ContentStack {
  answerFor: string;
  exerciseNumber: string;
}

/** A captured exercise chart, keyed by exercise id. MUST throw for a missing one: an exercise whose
 *  chart never drew is a question with no question in it. */
export type ExerciseChartLookup = (exerciseId: string) => string;

const DIVERGENCE_TYPES = new Set(["synthetic_chart", "fixture_chart"]);

function isDivergence(exercise: PrintExercise): boolean {
  return DIVERGENCE_TYPES.has(exercise.type);
}

/** The chart's own axis format (`dd/MM/yyyy`, UTC) — so a date in the key is a date on the chart. */
export function printDate(seconds: number): string {
  const date = new Date(seconds * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(date.getUTCDate())}/${pad(date.getUTCMonth() + 1)}/${date.getUTCFullYear()}`;
}

/** Payload numbers are already rounded to two decimals server-side; this keeps them locale-neutral,
 *  so the price in the key is character-for-character the number behind the printed candle. */
export function printPrice(price: number): string {
  return price.toFixed(2);
}

function optionsOf(exercise: PrintExercise, key: "options" | "items" | "lefts" | "rights"): OptionView[] {
  return exercise.payload[key] ?? [];
}

/** One printed option line: `a)  text`. A hanging indent keeps a wrapped option under its own text. */
function optionLine(index: number, text: string): Content {
  return {
    columns: [
      { text: `${letter(index)})`, width: 16, color: PRINT.muted },
      { text, width: "*" },
    ],
    columnGap: 4,
    margin: [8, 0, 0, 3],
  };
}

function hint(text: string): Content {
  return { text, style: "exerciseHint" };
}

/** Matching prints as a two-column table: the items numbered, the options lettered, because the
 *  answer has to name one of each ("1 → c") and a bare list of ten strings names neither. */
function matchingTable(exercise: PrintExercise): Content {
  const lefts = optionsOf(exercise, "lefts");
  const rights = optionsOf(exercise, "rights");
  const rows: TableCell[][] = [];
  for (let i = 0; i < Math.max(lefts.length, rights.length); i++) {
    rows.push([
      { text: lefts[i] ? `${i + 1}.  ${lefts[i].text ?? ""}` : "" },
      { text: rights[i] ? `${letter(i)})  ${rights[i].text ?? ""}` : "" },
    ]);
  }
  return {
    table: { widths: ["*", "*"], body: rows },
    layout: {
      hLineWidth: () => 0,
      vLineWidth: () => 0,
      paddingLeft: (i: number) => (i === 0 ? 8 : 10),
      paddingRight: () => 0,
      paddingTop: () => 2,
      paddingBottom: () => 2,
    },
    margin: [0, 2, 0, 4],
  };
}

function chartImage(exercise: PrintExercise, chart: ExerciseChartLookup): Content {
  return { image: chart(exercise.id), width: contentWidth(), margin: [0, 4, 0, 6] };
}

/** A prompt is markdown, and the app renders it as such (`<Prose markdown={instance.prompt} />`) —
 *  half of them emphasise the words the question turns on. Printed raw, those arrive as asterisks. */
export function promptContent(markdown: string, source: string): Content[] {
  const rendered = lessonToContent(
    markdown,
    {
      figure: (id) => {
        throw new Error(`an exercise prompt embeds figure ${id}; prompts carry no figures`);
      },
    },
    source,
  );
  return rendered.map((node) => {
    // `lessonToContent` styles paragraphs as prose; a prompt sits tighter to the options under it.
    const block = node as { style?: string };
    if (block.style === "p") block.style = "exercisePrompt";
    return node;
  });
}

/** The statement: prompt, then whatever the reader chooses between. */
function question(
  exercise: PrintExercise,
  labels: ExerciseLabels,
  chart: ExerciseChartLookup,
): Content[] {
  const body: Content[] = [...promptContent(exercise.prompt, exercise.id)];
  const kind = exercise.answer.kind;

  if (exercise.isChart) {
    body.push(chartImage(exercise, chart));
    const divergence = isDivergence(exercise);
    (exercise.payload.choices ?? []).forEach((choice, index) => {
      body.push(optionLine(index, labels.chartChoice(choice, divergence)));
    });
    return body;
  }
  if (kind === "true_false") {
    body.push(hint(labels.trueFalseHint));
    return body;
  }
  if (kind === "ordering") {
    body.push(hint(labels.orderingHint));
    optionsOf(exercise, "items").forEach((item, index) => body.push(optionLine(index, item.text ?? "")));
    return body;
  }
  if (kind === "matching") {
    body.push(hint(labels.matchingHint), matchingTable(exercise));
    return body;
  }
  if (kind === "multi_select") body.push(hint(labels.selectAllHint));
  const unit = exercise.payload.unit ?? exercise.answer.unit;
  optionsOf(exercise, "options").forEach((option, index) => {
    // A calculation's options are values, a quiz's are statements; the unit rides with the value.
    body.push(optionLine(index, option.text ?? `${option.value}${unit ? ` ${unit}` : ""}`));
  });
  return body;
}

export function exerciseBlock(
  exercise: PrintExercise,
  labels: ExerciseLabels,
  chart: ExerciseChartLookup,
): ExerciseBlock {
  return {
    stack: [
      // A heading: it must not be printed at the foot of a page with its question overleaf.
      { text: labels.exercise(exercise.number), style: "exerciseNumber", headlineLevel: 3 },
      ...question(exercise, labels, chart),
    ],
    margin: [0, 0, 0, 12],
    exerciseId: exercise.id,
    exerciseNumber: exercise.number,
  };
}

/** A lesson's exercises, under one heading, plus the note naming what could not be printed. */
export function lessonExercises(
  exercises: PrintExercise[],
  excludedCount: number,
  labels: ExerciseLabels,
  chart: ExerciseChartLookup,
): Content[] {
  if (exercises.length === 0 && excludedCount === 0) return [];
  const out: Content[] = [
    { text: labels.exercises, style: "exercisesHeading", headlineLevel: 2 },
  ];
  out.push(...exercises.map((exercise) => exerciseBlock(exercise, labels, chart)));
  // Never silently: a reader is told the lesson has more than the page shows.
  if (excludedCount > 0) out.push({ text: labels.excluded(excludedCount), style: "exerciseNote" });
  return out;
}

// --- the answer key ------------------------------------------------------------------------------

function textOf(options: OptionView[], id: string): string {
  const found = options.find((option) => option.id === id);
  return found?.text ?? String(found?.value ?? id);
}

function indexOf(options: OptionView[], id: string): number {
  return options.findIndex((option) => option.id === id);
}

function cite(options: OptionView[], id: string): string {
  const index = indexOf(options, id);
  return index < 0 ? textOf(options, id) : `${letter(index)})  ${textOf(options, id)}`;
}

function anchorLine(anchor: PrintAnchor, labels: ExerciseLabels): string {
  const name = labels.marker(anchor.label || anchor.kind);
  return `${name} — ${printPrice(anchor.price)} · ${printDate(anchor.time)}`;
}

function zoneLine(zone: PrintZone, labels: ExerciseLabels): string {
  return `${labels.zone(zone.label, zone.kind)} — ${printPrice(zone.low)} … ${printPrice(zone.high)}`;
}

/** The answer itself, in the reader's language, citing what the page printed. */
export function answerLines(exercise: PrintExercise, labels: ExerciseLabels): string[] {
  const answer = exercise.answer;
  if (exercise.isChart) {
    const lines = [labels.chartChoice(answer.label ?? "", isDivergence(exercise))];
    lines.push(...(answer.anchors ?? []).map((anchor) => anchorLine(anchor, labels)));
    lines.push(...(answer.zones ?? []).map((zone) => zoneLine(zone, labels)));
    return lines;
  }
  switch (answer.kind) {
    case "true_false":
      return [answer.value ? labels.trueLabel : labels.falseLabel];
    case "ordering": {
      const items = optionsOf(exercise, "items");
      return (answer.order ?? []).map(
        (id, position) => `${position + 1}.  ${cite(items, id)}`,
      );
    }
    case "matching": {
      const lefts = optionsOf(exercise, "lefts");
      const rights = optionsOf(exercise, "rights");
      return Object.entries(answer.pairs ?? {})
        // Printed order, not object order, so the key reads down the page's own list of items.
        .sort(([a], [b]) => indexOf(lefts, a) - indexOf(lefts, b))
        .map(([left, right]) => `${indexOf(lefts, left) + 1}.  ${textOf(lefts, left)} → ${cite(rights, right)}`);
    }
    case "calculation": {
      const options = optionsOf(exercise, "options");
      const id = (answer.optionIds ?? [])[0] ?? "";
      const unit = answer.unit ? ` ${answer.unit}` : "";
      const index = indexOf(options, id);
      return [`${index < 0 ? "" : `${letter(index)})  `}${answer.numericValue ?? ""}${unit}`];
    }
    default: {
      const options = optionsOf(exercise, "options");
      return (
        [...(answer.optionIds ?? [])]
          // Down the page, not by id: the server reveals a multi-select's correct ids sorted, and
          // `a) … c) … b)` reads as a mistake even when every letter is right.
          .sort((a, b) => indexOf(options, a) - indexOf(options, b))
          .map((id) => cite(options, id))
      );
    }
  }
}

export function answerEntry(exercise: PrintExercise, labels: ExerciseLabels): AnswerEntry {
  const stack: Content[] = [
    {
      columns: [
        { text: exercise.number, width: 42, style: "answerNumber" },
        { stack: answerLines(exercise, labels).map((text) => ({ text })), width: "*" },
      ],
      columnGap: 4,
    },
  ];
  const steps = exercise.answer.steps ?? [];
  if (steps.length > 0) {
    stack.push({
      text: `${labels.working}: ${steps.join("  ·  ")}`,
      style: "answerAside",
    });
  }
  if (exercise.answer.explanation) {
    stack.push({ text: `${labels.why}: ${exercise.answer.explanation}`, style: "answerAside" });
  }
  // An answer must never be split across a page turn from the number that addresses it. `unbreakable`
  // would do that too — and did, until it was found stranding the module heading above it: pdfmake
  // moves such a block during layout, and a moved block reports positions that make the heading look
  // accompanied. Worse, a block taller than a page is TRUNCATED rather than overflowed. The id puts
  // this entry under the same keep-whole rule the callouts use, which moves it honestly and reports
  // it if it can never fit.
  return withId(
    {
      stack,
      margin: [0, 0, 0, 8],
      answerFor: exercise.id,
      exerciseNumber: exercise.number,
    },
    printedId(ANSWER_ID, exercise.id, 0),
  );
}

export interface AnswerKeyGroup {
  /** Printed above the group — the module the answers belong to. */
  title: string;
  exercises: PrintExercise[];
}

/** The one answer-key section, at the back of the book, in the book's own order.
 *
 *  `null` when nothing was printed to answer: a key with no answers in it is a heading, and a heading
 *  in the table of contents pointing at an empty page is worse than no section. */
export function answerKeySection(
  groups: AnswerKeyGroup[],
  labels: ExerciseLabels,
  /** Marks this heading as a top-level section, so the running footer can name it. */
  sectionId: string,
): Content | null {
  if (groups.every((group) => group.exercises.length === 0)) return null;
  const body: Content[] = [
    withId(
      {
        text: labels.answerKey,
        style: "blockTitle",
        headlineLevel: 1,
        tocItem: true,
        tocStyle: "tocBlock",
      },
      sectionId,
    ),
    { text: labels.answerKeyIntro, style: "moduleSummary" },
  ];
  for (const group of groups) {
    if (group.exercises.length === 0) continue;
    body.push({ text: group.title, style: "answerGroup", headlineLevel: 2 });
    body.push(...group.exercises.map((exercise) => answerEntry(exercise, labels)));
  }
  return { stack: body, pageBreak: "before" };
}
