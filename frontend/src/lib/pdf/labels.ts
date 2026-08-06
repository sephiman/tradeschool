import { COURSE_AUTHOR, type PdfLabels } from "@/lib/pdf/document";

/**
 * Every word the PDF prints that is not course content, resolved from the app's catalogs in ONE place.
 *
 * `lib/pdf/` deliberately knows nothing about i18next — that is what makes the document buildable for
 * either locale in a test — so the chrome has to be handed in. Building it here rather than inside the
 * button means the tests print the same strings the reader gets, and the font's glyph coverage can be
 * checked against exactly this set instead of a guess at it.
 */

/** i18next's `t`, narrowed to what the PDF needs (interpolation, `count` plurals, `defaultValue`). */
export type Translate = (key: string, vars?: Record<string, unknown>) => string;

export function pdfLabels(t: Translate, generated: string): PdfLabels {
  return {
    contents: t("course.pdfContents"),
    author: t("course.pdfAuthor", { name: COURSE_AUTHOR }),
    generated,
    page: (current, total) => t("course.pdfPage", { current, total }),
    exercises: t("course.pdfExerciseHeading"),
    exercise: (number) => t("course.pdfExerciseNumber", { number }),
    excluded: (count) => t("course.pdfExerciseExcluded", { count }),
    answerKey: t("course.pdfAnswerKey"),
    answerKeyIntro: t("course.pdfAnswerKeyIntro"),
    working: t("course.pdfWorking"),
    why: t("course.pdfWhy"),
    trueLabel: t("exercise.true"),
    falseLabel: t("exercise.false"),
    trueFalseHint: t("course.pdfTrueFalse"),
    selectAllHint: t("exercise.selectAllThatApply"),
    // Print gets its own two: the app's hints tell you to tap things and to use arrow buttons.
    orderingHint: t("course.pdfOrderingHint"),
    matchingHint: t("course.pdfMatchingHint"),
    // The app's own label chains, so a printed answer names a pattern exactly as the screen does.
    chartChoice: (label, isDivergence) => t(`${isDivergence ? "divergence" : "chartLabel"}.${label}`),
    marker: (raw) => t(`chartMarker.${raw}`, { defaultValue: raw }),
    zone: (label, kind) =>
      t(`band.${label}`, { defaultValue: t(`band.${kind}`, { defaultValue: label }) }),
  };
}
