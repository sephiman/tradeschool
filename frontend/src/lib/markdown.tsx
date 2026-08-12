import { type ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkDirective from "remark-directive";
import type { Root } from "mdast";
import { annotateLesson } from "@/lib/glossary/annotate";
import type { TermMatcher } from "@/lib/glossary/terms";
import { cn } from "@/lib/cn";

/** Turn remark-directive nodes into plain elements carrying data-* hints for the `components` map. */
interface DirectiveNode {
  type: string;
  name?: string;
  attributes?: Record<string, string | null | undefined>;
  data?: { hName?: string; hProperties?: Record<string, unknown> };
  children?: unknown[];
}

function transform(node: DirectiveNode): void {
  if (node.type === "containerDirective" || node.type === "leafDirective" || node.type === "textDirective") {
    const attrs = node.attributes ?? {};
    const data = (node.data ??= {});
    if (node.name === "note") {
      data.hName = "div";
      data.hProperties = { "data-note-type": attrs.type ?? "info" };
    } else if (node.name === "exercise") {
      data.hName = "div";
      data.hProperties = { "data-exercise-id": attrs.id ?? "" };
    } else if (node.name === "figure") {
      data.hName = "div";
      data.hProperties = { "data-figure-id": attrs.id ?? "" };
    } else {
      data.hName = "div";
      data.hProperties = {};
    }
  }
  if (Array.isArray(node.children)) {
    for (const child of node.children) transform(child as DirectiveNode);
  }
}

function remarkDirectiveToHast() {
  return (tree: unknown) => transform(tree as DirectiveNode);
}

const NOTE_TONES: Record<string, string> = {
  info: "border-indigo-300 bg-indigo-50 text-indigo-900 dark:border-indigo-800 dark:bg-indigo-950/50 dark:text-indigo-100",
  warning: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-100",
  tip: "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-100",
};

function Callout({ tone, children }: { tone: string; children: ReactNode }) {
  return (
    <div className={cn("my-4 rounded-md border-l-4 px-4 py-3 text-sm [&>p]:my-1", NOTE_TONES[tone] ?? NOTE_TONES.info)}>
      {children}
    </div>
  );
}

function buildComponents(
  renderExercise: (exerciseId: string) => ReactNode,
  renderFigure: (figureId: string) => ReactNode,
  renderTerm: (termId: string, children: ReactNode) => ReactNode,
): Components {
  return {
    span: (props) => {
      const attrs = props as Record<string, unknown> & { children?: ReactNode };
      const termId = attrs["data-term-id"];
      // Planted by the glossary annotator; anything else is a span the markdown itself asked for.
      if (typeof termId === "string") return <>{renderTerm(termId, attrs.children)}</>;
      return <span>{attrs.children}</span>;
    },
    h1: ({ children }) => <h1 className="mt-2 mb-4 text-2xl font-bold">{children}</h1>,
    h2: ({ children }) => <h2 className="mt-6 mb-3 text-xl font-semibold">{children}</h2>,
    h3: ({ children }) => <h3 className="mt-4 mb-2 text-lg font-semibold">{children}</h3>,
    p: ({ children }) => <p className="my-3 leading-relaxed text-gray-700 dark:text-gray-300">{children}</p>,
    ul: ({ children }) => <ul className="my-3 list-disc space-y-1 pl-6 text-gray-700 dark:text-gray-300">{children}</ul>,
    ol: ({ children }) => <ol className="my-3 list-decimal space-y-1 pl-6 text-gray-700 dark:text-gray-300">{children}</ol>,
    li: ({ children }) => <li className="leading-relaxed">{children}</li>,
    strong: ({ children }) => <strong className="font-semibold text-gray-900 dark:text-gray-100">{children}</strong>,
    code: ({ children }) => (
      <code className="rounded bg-gray-100 px-1 py-0.5 font-mono text-[0.85em] text-gray-800 dark:bg-gray-800 dark:text-gray-200">
        {children}
      </code>
    ),
    a: ({ href, children }) => (
      <a href={href} className="font-medium text-primary hover:underline" target="_blank" rel="noreferrer">
        {children}
      </a>
    ),
    // GFM tables. Same rule as the PDF's tables and SharedLedger's data tables: horizontal rules
    // only, the header rule a step stronger than the row rules. The wrapper scrolls so a wide table
    // never widens the page on phone widths.
    table: ({ children }) => (
      <div className="my-4 overflow-x-auto">
        <table className="w-full text-sm">{children}</table>
      </div>
    ),
    thead: ({ children }) => (
      <thead className="border-b border-gray-300 text-gray-500 dark:border-gray-700 dark:text-gray-400 oled:border-oled-line-strong">
        {children}
      </thead>
    ),
    tbody: ({ children }) => (
      <tbody className="divide-y divide-border dark:divide-gray-800 oled:divide-oled-line">{children}</tbody>
    ),
    // `align` carries a `|:---:|` column marker; left is the default only while none is set.
    th: ({ align, children }) => (
      <th align={align} className={cn("py-2 pr-4 last:pr-0", !align && "text-left")}>
        {children}
      </th>
    ),
    td: ({ align, children }) => (
      <td align={align} className="py-2 pr-4 align-top text-gray-700 last:pr-0 dark:text-gray-300">
        {children}
      </td>
    ),
    div: (props) => {
      const attrs = props as Record<string, unknown> & { children?: ReactNode };
      const exerciseId = attrs["data-exercise-id"];
      if (typeof exerciseId === "string") return <>{renderExercise(exerciseId)}</>;
      const figureId = attrs["data-figure-id"];
      if (typeof figureId === "string") return <>{renderFigure(figureId)}</>;
      const noteType = attrs["data-note-type"];
      if (typeof noteType === "string") return <Callout tone={noteType}>{attrs.children}</Callout>;
      return <div>{attrs.children}</div>;
    },
  };
}

/**
 * A lesson's prose.
 *
 * `glossary` is the ONE annotator, run as a remark plugin over the same mdast the print renderer
 * annotates: the app never detects a term on its own. Its `marked` set is created per run, which is
 * exactly the web's policy — first occurrence of each term in THIS lesson.
 */
export function LessonMarkdown({
  markdown,
  renderExercise,
  renderFigure,
  renderTerm = (_id, children) => children,
  glossary,
}: {
  markdown: string;
  renderExercise: (exerciseId: string) => ReactNode;
  renderFigure: (figureId: string) => ReactNode;
  renderTerm?: (termId: string, children: ReactNode) => ReactNode;
  glossary?: { lessonId: string; terms: TermMatcher[] };
}) {
  const annotate = () => (tree: Root) => {
    if (glossary) annotateLesson(tree, { ...glossary, marked: new Set<string>() });
  };
  return (
    <Markdown
      remarkPlugins={[remarkGfm, remarkDirective, annotate, remarkDirectiveToHast]}
      components={buildComponents(renderExercise, renderFigure, renderTerm)}
    >
      {markdown}
    </Markdown>
  );
}

/** Inline prose (e.g. an exercise prompt) with the same styling but no directives. */
export function Prose({ markdown }: { markdown: string }) {
  return (
    <Markdown
      remarkPlugins={[remarkGfm]}
      components={buildComponents(() => null, () => null, (_id, children) => children)}
    >
      {markdown}
    </Markdown>
  );
}
