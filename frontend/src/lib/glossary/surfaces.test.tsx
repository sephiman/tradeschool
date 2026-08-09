import { act, type ReactElement } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";
import type { Content } from "pdfmake/interfaces";
import { LessonMarkdown } from "@/lib/markdown";
import { lessonToContent } from "@/lib/pdf/markdown";
import { annotateLesson } from "@/lib/glossary/annotate";
import { buildTermIndex } from "@/lib/glossary/terms";
import { DEST } from "@/lib/pdf/pagination";
import { glossaryFromContent, lessonMarkdown, manifestLessons, LOCALES, type Locale } from "@/test/courseContent";

/**
 * The two surfaces mark the same words. This is the drift test.
 *
 * They share the annotator but not the parser — the app renders through react-markdown's own remark
 * pipeline, the book through `lib/pdf/markdown`'s. Both are given real lessons here, and their marks
 * are compared term for term, so a divergence in either pipeline fails rather than shipping a book
 * that links words the screen does not.
 */

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

/** A handful of real lessons, spread across the course rather than clustered at the front. */
const SAMPLE = ["m03-l2", "m09-l1", "m17-l1", "m24-l1", "m30-l1"];

function mount(node: ReactElement): HTMLElement {
  const host = document.createElement("div");
  document.body.appendChild(host);
  act(() => {
    createRoot(host).render(node);
  });
  return host;
}

/** The term ids the app marks, in reading order. */
function webMarks(markdown: string, lessonId: string, locale: Locale): string[] {
  document.body.innerHTML = "";
  const host = mount(
    <LessonMarkdown
      markdown={markdown}
      renderExercise={() => null}
      renderFigure={() => null}
      glossary={{ lessonId, terms: buildTermIndex(glossaryFromContent(locale), locale) }}
      renderTerm={(termId, children) => <span data-term-id={termId}>{children}</span>}
    />,
  );
  return [...host.querySelectorAll("[data-term-id]")].map((node) => node.getAttribute("data-term-id") ?? "");
}

/** The term ids the book links, in reading order. */
function printMarks(markdown: string, lessonId: string, locale: Locale): string[] {
  const terms = buildTermIndex(glossaryFromContent(locale), locale);
  const marked = new Set<string>();
  const content = lessonToContent(markdown, { figure: () => ({ text: "" }) }, lessonId, (tree) => {
    annotateLesson(tree, { lessonId, terms, marked });
  });
  const found: string[] = [];
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) return node.forEach(walk);
    if (typeof node !== "object" || node === null) return;
    const run = node as { linkToDestination?: string };
    if (typeof run.linkToDestination === "string" && run.linkToDestination.startsWith("gdest-")) {
      found.push(run.linkToDestination.slice(DEST.term("").length));
    }
    for (const value of Object.values(node)) walk(value);
  };
  walk(content as Content[]);
  return found;
}

/** What the export endpoint serves the PDF: the same prose with the exercise directives removed. */
function theoryOnly(markdown: string): string {
  return markdown.replace(/^::exercise\{[^}]*\}[ \t]*$/gm, "").replace(/\n{3,}/g, "\n\n").trim();
}

describe.each(LOCALES)("the app and the book mark the same words (%s)", (locale) => {
  it.each(SAMPLE)("agrees on %s, term for term and in the same order", (lessonId) => {
    const markdown = lessonMarkdown(locale, lessonId);
    const web = webMarks(markdown, lessonId, locale);
    expect(web.length, `${lessonId} marks nothing, so agreeing is meaningless`).toBeGreaterThan(3);
    expect(printMarks(markdown, lessonId, locale)).toEqual(web);
  }, 60_000);

  it("is unchanged by the export stripping the exercise directives out", () => {
    // The book is built from theory-only prose and the app from the full lesson. Annotation is a
    // presentation layer over the same words, so removing a directive must move no mark.
    for (const lesson of manifestLessons()) {
      const markdown = lessonMarkdown(locale, lesson.id);
      expect(
        printMarks(theoryOnly(markdown), lesson.id, locale),
        `${lesson.id} marks differently once its exercises are stripped`,
      ).toEqual(printMarks(markdown, lesson.id, locale));
    }
  }, 120_000);
});
