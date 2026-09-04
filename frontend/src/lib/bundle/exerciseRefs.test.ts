// @vitest-environment node
import { describe, expect, it } from "vitest";
import { exerciseRefs, ExerciseRefError } from "@/lib/bundle/exerciseRefs";
import { buildRefRegistry, type RefRegistry } from "@/lib/refs/registry";
import { manifestModules, LOCALES, type Locale } from "@/test/courseContent";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { CONTENT_DIR } from "@/test/courseContent";
import yaml from "js-yaml";

/**
 * The references inside exercise prose, resolved at export time so the app stops detecting them.
 *
 * The load-bearing property is the OFFSET. A lesson's marks need none — its references travel as
 * nodes inside its own mdast, with the text split around them — but an exercise's prose travels as a
 * string, so a mark is a pair of numbers into that string and a wrong pair puts the chip on the
 * wrong word, silently. Every test here reads the offsets back out of the source.
 */

const registry: RefRegistry = buildRefRegistry(
  manifestModules().map((module) => ({
    id: module.id,
    key: module.key ?? module.id,
    title: module.title.en,
    lessons: (module.lessons ?? []).map((lesson) => ({
      id: lesson.id,
      key: lesson.key ?? lesson.id,
      title: lesson.title.en,
    })),
  })),
);

/** What the mark says it found, cut out of the source by the offsets it shipped. */
function cut(text: string): string[] {
  return exerciseRefs(text, registry).map((mark) => text.slice(mark.start, mark.end));
}

describe("references in exercise prose", () => {
  it("marks a mention and its offsets cut exactly that mention out", () => {
    const text = "the spring of m09 is absorbed selling";
    const [mark] = exerciseRefs(text, registry);
    expect(mark).toMatchObject({ mention: "m09", refKind: "module", refId: "m09" });
    expect(text.slice(mark.start, mark.end)).toBe("m09");
  });

  it("counts the markup, because the offsets are into the string the bundle carries", () => {
    // The mdast text node starts AFTER the `**`, which is the whole reason the offset is taken from
    // the node's own source position rather than from a search of the flattened text.
    const text = "**m09** and m13 both";
    expect(cut(text)).toEqual(["m09", "m13"]);
    expect(exerciseRefs(text, registry).map((m) => m.start)).toEqual([2, 12]);
  });

  it("resolves a lesson mention as a lesson and a module mention as a module", () => {
    const marks = exerciseRefs("m08-l1 taught the level, m09 the phase", registry);
    expect(marks.map((m) => [m.mention, m.refKind])).toEqual([
      ["m08-l1", "lesson"],
      ["m09", "module"],
    ]);
  });

  it("skips what the lesson annotator skips, so one detector means one answer", () => {
    expect(cut("a code span `m09` is not a mention")).toEqual([]);
    expect(cut("[m09](https://example.com) is link text")).toEqual([]);
  });

  it("leaves alone what is only id-shaped", () => {
    expect(cut("m01-ex-1 names an exercise")).toEqual([]);
    expect(cut("on the M15 chart")).toEqual([]);
    expect(cut("m99 answers to nothing")).toEqual([]);
  });
});

/** Every localized string in every exercise config, the way the exporter collects them. */
function exerciseStrings(locale: Locale): { where: string; text: string }[] {
  const out: { where: string; text: string }[] = [];
  const walk = (node: unknown, path: string): void => {
    if (Array.isArray(node)) {
      node.forEach((child, index) => walk(child, `${path}[${index}]`));
      return;
    }
    if (node === null || typeof node !== "object") return;
    const record = node as Record<string, unknown>;
    const keys = Object.keys(record).sort();
    if (keys.length === LOCALES.length && keys.every((k, i) => k === [...LOCALES].sort()[i])) {
      if (LOCALES.every((l) => typeof record[l] === "string")) {
        out.push({ where: path, text: record[locale] as string });
        return;
      }
    }
    for (const [key, value] of Object.entries(record)) walk(value, path ? `${path}.${key}` : key);
  };
  for (const id of manifestModules().flatMap((m) => (m.lessons ?? []).flatMap((l) => l.exercises ?? []))) {
    const path = resolve(CONTENT_DIR, "exercises", `${id.id}.yaml`);
    let raw: string;
    try {
      raw = readFileSync(path, "utf8");
    } catch {
      continue; // declared in the manifest but not yet playable
    }
    walk(yaml.load(raw), id.id);
  }
  return out;
}

describe.each(LOCALES)("every exercise string in the course (%s)", (locale: Locale) => {
  it("has offsets that cut their own mention out of it", () => {
    let marked = 0;
    for (const { where, text } of exerciseStrings(locale)) {
      for (const mark of exerciseRefs(text, registry)) {
        expect(text.slice(mark.start, mark.end), `${where}: ${text.slice(0, 60)}`).toBe(mark.mention);
        marked += 1;
      }
    }
    // Not vacuous: the content really does name modules by id, in both shapes.
    expect(marked).toBeGreaterThan(100);
  });
});

describe("an offset that cannot be trusted", () => {
  it("is refused rather than shipped", () => {
    // A character reference makes the mdast value shorter than the source it came from, so an offset
    // taken as `node start + index in value` lands early. The guard reads it back and refuses.
    expect(() => exerciseRefs("&amp;&amp;&amp; m09", registry)).toThrow(ExerciseRefError);
  });
});
