import { renderToStaticMarkup } from "react-dom/server";
import { LessonMarkdown } from "@/lib/markdown";

/**
 * One lesson as the web actually paints it — the reference the bundle's blocks are checked against.
 *
 * `LessonMarkdown` itself, not a re-derivation of it: this is the whole point of the check. The
 * markdown goes through the app's own plugin list, `mdast-util-to-hast` and the `components` map,
 * none of which `bundle/ast.ts` touches, so the two ends of the pipeline are independent enough for
 * one to be evidence about the other.
 *
 * Nothing is annotated. Glossary and reference marks are inline spans that must not change a single
 * character of the prose, and the cheapest way to say so is to compare an annotated bundle against
 * an un-annotated page and require them equal.
 */
export function lessonHtml(markdown: string): string {
  // The two generated slots render as nothing on this side, which is what they carry in the bundle:
  // a `leafDirective` with no text. A chart or an exercise player would be text the AST never had.
  return renderToStaticMarkup(
    <LessonMarkdown markdown={markdown} renderExercise={() => null} renderFigure={() => null} />,
  );
}
