// @vitest-environment node
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  buildLinkReport,
  formatLinkReport,
  type LinkReport,
  type ReportLesson,
} from "@/lib/glossary/report";
import {
  CONTENT_DIR,
  glossaryFromContent,
  lessonMarkdown,
  manifestLessons,
  LOCALES,
  type Locale,
} from "@/test/courseContent";

/**
 * The golden link report: frozen, reviewed by hand, and loud when it moves.
 *
 * Regenerate with `UPDATE_GLOSSARY_LINKS=1 npx vitest run src/lib/glossary/report.test.ts` and READ
 * THE DIFF — it is the only place a false positive is caught before a reader meets it.
 */

const UPDATE = process.env.UPDATE_GLOSSARY_LINKS === "1";
/** Building the report walks 36 lessons twice; under a full parallel run that outlasts the 5s default. */
const SLOW = 120_000;

/** Course reading order, which is what the PDF's "first occurrence in the book" means. */
function courseLessons(locale: Locale): ReportLesson[] {
  return manifestLessons().map((lesson) => ({ id: lesson.id, markdown: lessonMarkdown(locale, lesson.id) }));
}

function goldenPath(locale: Locale): string {
  return resolve(CONTENT_DIR, `glossary-links.${locale}.txt`);
}

/** The whole course, twice per locale, is the expensive part — build it once and read it many times. */
const reports = new Map<Locale, LinkReport>();
function report(locale: Locale): LinkReport {
  const existing = reports.get(locale);
  if (existing) return existing;
  const built = buildLinkReport(courseLessons(locale), glossaryFromContent(locale), locale);
  reports.set(locale, built);
  return built;
}

function generate(locale: Locale): string {
  return formatLinkReport(buildLinkReport(courseLessons(locale), glossaryFromContent(locale), locale));
}

describe.each(LOCALES)("the golden link report (%s)", (locale) => {
  it("matches the committed report", () => {
    const current = generate(locale);
    if (UPDATE) writeFileSync(goldenPath(locale), current, "utf8");
    const committed = readFileSync(goldenPath(locale), "utf8");
    expect(
      current,
      "the links the annotator would draw have moved — review the diff, then regenerate with " +
        "UPDATE_GLOSSARY_LINKS=1",
    ).toBe(committed);
  }, SLOW);

  it("is deterministic: two runs are byte-identical", () => {
    expect(generate(locale)).toBe(generate(locale));
  }, SLOW);

  it("marks something in most lessons, and links a real share of the glossary", () => {
    // A floor, not a fingerprint: if a refactor quietly stopped matching, the report above would
    // still "match" nothing against nothing on the day it is regenerated without being read.
    const built = report(locale);
    expect(new Set(built.rows.map((row) => row.lessonId)).size).toBeGreaterThan(25);
    expect(built.rows.filter((row) => row.flag === "WP").length).toBeGreaterThan(30);
  }, SLOW);

  it("never links a term in a lesson that term points back at", () => {
    const origins = new Map(
      glossaryFromContent(locale).map((entry) => [
        entry.id,
        new Set([entry.origin, ...(entry.senses ?? []).map((sense) => sense.origin)].filter(Boolean)),
      ]),
    );
    const loops = report(locale).rows.filter((row) => origins.get(row.termId)?.has(row.lessonId));
    expect(loops).toEqual([]);
  }, SLOW);

  it("links each term at most once in the whole book", () => {
    // Every `WP` row is a web row by construction; what this pins is that one term never claims two
    // places in the book, which is what the global policy means.
    const linked = report(locale).rows.filter((row) => row.flag === "WP").map((row) => row.termId);
    expect(new Set(linked).size).toBe(linked.length);
  }, SLOW);

  it("shows a moved link as a diff when the prose changes", () => {
    const lessons = courseLessons(locale);
    const entries = glossaryFromContent(locale);
    // A synthetic edit: the same prose with its first two lessons swapped moves every term whose
    // first occurrence lived in either of them.
    const swapped = [lessons[1], lessons[0], ...lessons.slice(2)];
    expect(formatLinkReport(buildLinkReport(swapped, entries, locale))).not.toBe(
      formatLinkReport(report(locale)),
    );
  }, SLOW);
});
