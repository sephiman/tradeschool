// @vitest-environment node
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { buildRefReport, formatRefReport, type RefReport, type RefReportLesson } from "@/lib/refs/report";
import {
  CONTENT_DIR,
  lessonMarkdown,
  manifestLessons,
  refModulesFromManifest,
  LOCALES,
  type Locale,
} from "@/test/courseContent";

/**
 * The golden reference report: frozen, reviewed by hand, and loud when it moves — the same
 * discipline as `glossary-links.<locale>.txt`.
 *
 * Regenerate with `UPDATE_LESSON_REFS=1 npx vitest run src/lib/refs/report.test.ts` and READ THE
 * DIFF. The zero-dangling test below is the course's permanent prose-integrity guard: every
 * id-shaped mention in every lesson must name a module or lesson that exists.
 */

const UPDATE = process.env.UPDATE_LESSON_REFS === "1";
const SLOW = 120_000;

function courseLessons(locale: Locale): RefReportLesson[] {
  return manifestLessons().map((lesson) => ({
    id: lesson.id,
    key: lesson.key ?? lesson.id,
    markdown: lessonMarkdown(locale, lesson.id),
  }));
}

function goldenPath(locale: Locale): string {
  return resolve(CONTENT_DIR, `lesson-refs.${locale}.txt`);
}

const reports = new Map<Locale, RefReport>();
function report(locale: Locale): RefReport {
  const existing = reports.get(locale);
  if (existing) return existing;
  const built = buildRefReport(courseLessons(locale), refModulesFromManifest(locale), locale);
  reports.set(locale, built);
  return built;
}

describe.each(LOCALES)("the golden reference report (%s)", (locale) => {
  it("matches the committed report", () => {
    const current = formatRefReport(report(locale));
    if (UPDATE) writeFileSync(goldenPath(locale), current, "utf8");
    const committed = readFileSync(goldenPath(locale), "utf8");
    expect(
      current,
      "the references the annotator would link have moved — review the diff, then regenerate with " +
        "UPDATE_LESSON_REFS=1",
    ).toBe(committed);
  }, SLOW);

  it("is deterministic: two runs are byte-identical", () => {
    const again = buildRefReport(courseLessons(locale), refModulesFromManifest(locale), locale);
    expect(formatRefReport(again)).toBe(formatRefReport(report(locale)));
  }, SLOW);

  it("leaves nothing dangling: every id-shaped mention names a module or lesson that exists", () => {
    expect(report(locale).dangling).toEqual([]);
  }, SLOW);

  it("links a real share of the course, so the guards above are not vacuous", () => {
    // A floor, not a fingerprint — the golden pins the exact set.
    const built = report(locale);
    expect(built.rows.length).toBeGreaterThan(150);
    expect(new Set(built.rows.map((row) => row.lessonKey)).size).toBeGreaterThan(20);
  }, SLOW);

  it("never links a lesson to itself", () => {
    const loops = report(locale).rows.filter(
      (row) => row.kind === "lesson" && row.targetKey === row.lessonKey,
    );
    expect(loops).toEqual([]);
  }, SLOW);
});

describe("the two locales", () => {
  it("carry the same references: the locales adapt together, mention for mention", () => {
    // Contexts differ (they are prose); the reference structure must not. A mention added to one
    // locale and not the other is a translation drifting, and this is where it gets caught.
    const shape = (locale: Locale) =>
      report(locale).rows.map((row) => `${row.lessonKey} ${row.mention} ${row.kind} ${row.targetKey}`);
    expect(shape("es")).toEqual(shape("en"));
  }, SLOW);
});
