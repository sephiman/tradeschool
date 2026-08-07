import { readFileSync } from "node:fs";
import yaml from "js-yaml";
import type { PrintExercise, PrintExercises, PrintLesson } from "@/api/course";
import type { AttemptPayload, OptionView } from "@/api/exercises";
import { CONTENT_DIR, manifestModules, type Locale } from "@/test/courseContent";

/**
 * The print document as `/course/print/exercises?lang=…` serves it, with every id, type and order read
 * off `content/` so the completeness tests cannot age.
 *
 * The INSTANCES are stand-ins deliberately: reimplementing the Python generators in TypeScript is the
 * drift this codebase refuses. The frontend owns the JOIN, which instances of the right SHAPE exercise
 * fully; whether the numbers are right is `test_print_exercises.py`'s job.
 */

interface RawOption {
  id: string;
  text: Record<Locale, string>;
  correct?: boolean;
}
interface RawItem {
  id: string;
  text: Record<Locale, string>;
  position: number;
}
interface RawPair {
  id: string;
  left: Record<Locale, string>;
  right: Record<Locale, string>;
}
interface RawVariant {
  id: string;
  kind?: string;
  prompt: Record<Locale, string>;
  explanation?: Record<Locale, string>;
  options?: RawOption[];
  answer?: boolean;
  items?: RawItem[];
  pairs?: RawPair[];
}
interface RawConfig {
  type: string;
  prompt?: Record<Locale, string>;
  explanation?: Record<Locale, string>;
  variants?: RawVariant[];
  choices?: string[];
  unit?: string | null;
  params?: Record<string, { kind: string; min?: number; max?: number; values?: string[] }>;
}

const configs = new Map<string, RawConfig>();

function config(exerciseId: string): RawConfig {
  const cached = configs.get(exerciseId);
  if (cached) return cached;
  const raw = yaml.load(
    readFileSync(`${CONTENT_DIR}exercises/${exerciseId}.yaml`, "utf8"),
  ) as RawConfig;
  configs.set(exerciseId, raw);
  return raw;
}

/** A small stable hash, so every choice below is a function of the id — no clock, no randomness. */
function digest(value: string): number {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i++) {
    hash = Math.imul(hash ^ value.charCodeAt(i), 16777619) >>> 0;
  }
  return hash;
}

/** The printed seed's stand-in — same contract (a pure function of the id), different hash. */
function seedFor(exerciseId: string): number {
  return digest(exerciseId);
}

function shuffled<T>(items: T[], salt: number): T[] {
  return items
    .map((item, index) => ({ item, key: digest(`${salt}:${index}`) }))
    .sort((a, b) => a.key - b.key)
    .map(({ item }) => item);
}

function quiz(id: string, raw: RawConfig, locale: Locale): Omit<PrintExercise, "id" | "number" | "type" | "isChart" | "seed"> {
  const variants = raw.variants ?? [];
  const variant = variants[digest(id) % variants.length];
  const kind = (variant.kind ?? "single_choice") as NonNullable<AttemptPayload["kind"]>;
  const explanation = variant.explanation?.[locale] ?? null;
  const prompt = variant.prompt[locale];

  if (kind === "true_false") {
    return { prompt, payload: { kind }, answer: { kind, value: !!variant.answer, explanation } };
  }
  if (kind === "ordering") {
    const items = shuffled(variant.items ?? [], digest(id));
    const order = [...(variant.items ?? [])].sort((a, b) => a.position - b.position).map((i) => i.id);
    return {
      prompt,
      payload: { kind, items: items.map((i) => ({ id: i.id, text: i.text[locale] })) },
      answer: { kind, order, explanation },
    };
  }
  if (kind === "matching") {
    const pairs = variant.pairs ?? [];
    const lefts = shuffled(pairs.map((p, i) => ({ p, i })), digest(`l${id}`));
    const rights = shuffled(pairs.map((p, i) => ({ p, i })), digest(`r${id}`));
    const leftId = new Map(lefts.map(({ i }, slot) => [i, `l${slot}`]));
    const rightId = new Map(rights.map(({ i }, slot) => [i, `r${slot}`]));
    return {
      prompt,
      payload: {
        kind,
        lefts: lefts.map(({ p }, slot) => ({ id: `l${slot}`, text: p.left[locale] })),
        rights: rights.map(({ p }, slot) => ({ id: `r${slot}`, text: p.right[locale] })),
      },
      answer: {
        kind,
        pairs: Object.fromEntries(pairs.map((_, i) => [leftId.get(i)!, rightId.get(i)!])),
        explanation,
      },
    };
  }
  // What is left is an option list: single_choice unless the variant says otherwise.
  const choice = kind === "multi_select" ? "multi_select" : "single_choice";
  const options = shuffled(variant.options ?? [], digest(id));
  return {
    prompt,
    payload: { kind: choice, options: options.map((o) => ({ id: o.id, text: o.text[locale] })) },
    answer: {
      kind: choice,
      optionIds: options.filter((o) => o.correct).map((o) => o.id),
      explanation,
    },
  };
}

function calculation(id: string, raw: RawConfig, locale: Locale): Omit<PrintExercise, "id" | "number" | "type" | "isChart" | "seed"> {
  // The real generator samples the params and formats them into the prompt; a fixed sample is enough
  // to print, and keeps the fixture a pure function of the id.
  const params = Object.fromEntries(
    Object.entries(raw.params ?? {}).map(([name, spec]) => [
      name,
      spec.kind === "choice" ? (spec.values ?? ["long"])[0] : (spec.min ?? 1),
    ]),
  );
  const prompt = (raw.prompt?.[locale] ?? "").replace(
    /\{(\w+)\}/g,
    (_match, name: string) => String(params[name] ?? name),
  );
  const base = 1 + (digest(id) % 900);
  const options: OptionView[] = [0, 1, 2, 3].map((i) => ({
    id: `o${i}`,
    value: (base * (1 + i / 10)).toFixed(2),
  }));
  const correct = options[digest(`c${id}`) % options.length];
  return {
    prompt,
    payload: { kind: "multiple_choice", options, unit: raw.unit ?? null },
    answer: {
      kind: "calculation",
      optionIds: [correct.id],
      numericValue: String(correct.value),
      unit: raw.unit ?? null,
      steps: ["value = base × factor", `      = ${correct.value}`],
      explanation: raw.explanation?.[locale] ?? null,
    },
  };
}

const BARS = 40;

/** A candle series of the right shape — the print renderer needs prices, not a credible market. */
function series(id: string): NonNullable<AttemptPayload["series"]> {
  const time: number[] = [];
  const open: number[] = [];
  const high: number[] = [];
  const low: number[] = [];
  const close: number[] = [];
  const volume: number[] = [];
  let price = 100 + (digest(id) % 50);
  for (let i = 0; i < BARS; i++) {
    const step = ((digest(`${id}:${i}`) % 200) - 100) / 100;
    const openPrice = price;
    price = Math.round((price + step) * 100) / 100;
    time.push(1700000000 + i * 86400);
    open.push(openPrice);
    close.push(price);
    high.push(Math.round((Math.max(openPrice, price) + 0.5) * 100) / 100);
    low.push(Math.round((Math.min(openPrice, price) - 0.5) * 100) / 100);
    volume.push(1000 + (digest(`v${id}:${i}`) % 500));
  }
  return { time, open, high, low, close, volume };
}

function chart(id: string, raw: RawConfig, locale: Locale): Omit<PrintExercise, "id" | "number" | "type" | "isChart" | "seed"> {
  const choices = raw.choices ?? ["none"];
  const label = choices[digest(id) % choices.length];
  const bars = series(id);
  const rsi = bars.close.map((_, i) => 30 + (digest(`r${id}:${i}`) % 40));
  // Anchors are priced OUT of the series above, exactly as the server prices them out of the series
  // it publishes — the join the answer key depends on.
  const anchors = [12, 27].map((index, n) => {
    const kind = label.startsWith("bearish") ? "high" : "low";
    return {
      index,
      time: bars.time[index],
      kind,
      label: String(n + 1),
      price: kind === "high" ? bars.high[index] : bars.low[index],
    };
  });
  return {
    prompt: raw.prompt?.[locale] ?? "",
    payload: { series: bars, rsi, indicator: "rsi", choices },
    answer: {
      kind: "chart",
      label,
      anchors,
      zones: [],
      explanation: raw.explanation?.[locale] ?? null,
    },
  };
}

function printNumber(exerciseId: string): string {
  const match = /^m0*(\d+)-ex-0*(\d+)$/.exec(exerciseId);
  return match ? `${Number(match[1])}.${Number(match[2])}` : exerciseId;
}

const CHART_TYPES = new Set(["synthetic_chart", "fixture_chart", "pattern_chart"]);

export function printExerciseFromContent(
  exerciseId: string,
  type: string,
  locale: Locale,
): PrintExercise {
  const raw = config(exerciseId);
  const isChart = CHART_TYPES.has(type);
  const body = isChart
    ? chart(exerciseId, raw, locale)
    : type === "calculation"
      ? calculation(exerciseId, raw, locale)
      : quiz(exerciseId, raw, locale);
  return {
    id: exerciseId,
    number: printNumber(exerciseId),
    type: type as PrintExercise["type"],
    isChart,
    seed: seedFor(exerciseId),
    ...body,
  };
}

/** The whole print document for one locale, in manifest order; `exclude` drops one as the server would. */
export function printExercisesFromContent(
  locale: Locale,
  exclude: Record<string, string> = {},
): PrintExercises {
  const lessons: PrintLesson[] = [];
  const excluded: PrintExercises["excluded"] = [];
  for (const module of manifestModules()) {
    for (const lesson of module.lessons ?? []) {
      const exercises: PrintExercise[] = [];
      for (const exercise of lesson.exercises ?? []) {
        const reason = exclude[exercise.id];
        if (reason) {
          excluded.push({
            id: exercise.id,
            number: printNumber(exercise.id),
            lessonId: lesson.id,
            type: exercise.type,
            reason,
          });
          continue;
        }
        exercises.push(printExerciseFromContent(exercise.id, exercise.type, locale));
      }
      lessons.push({ lessonId: lesson.id, moduleId: module.id, exercises });
    }
  }
  return { locale, lessons, excluded };
}

/** Every chart exercise's captured PNG, stubbed — the capture itself needs a browser. */
export function stubExerciseCharts(print: PrintExercises, png: string): Map<string, string> {
  const charts = new Map<string, string>();
  for (const lesson of print.lessons) {
    for (const exercise of lesson.exercises) if (exercise.isChart) charts.set(exercise.id, png);
  }
  return charts;
}
