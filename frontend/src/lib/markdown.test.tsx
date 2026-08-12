import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { LessonMarkdown } from "./markdown";
import { buildRefRegistry } from "@/lib/refs/registry";

const md = `# Title

Some **bold** text.

:::note{type=warning}
Be careful here.
:::

::exercise{id=m01-ex-1}

::figure{id=fig-demo}

| Estilo | Contexto |
|---|---|
| **Scalper** | 15m – 1h |
`;

describe("LessonMarkdown", () => {
  const html = renderToStaticMarkup(
    <LessonMarkdown
      markdown={md}
      renderExercise={(id) => <span>EXERCISE:{id}</span>}
      renderFigure={(id) => <span>FIGURE:{id}</span>}
    />,
  );

  it("renders prose and bold", () => {
    expect(html).toContain("Title");
    expect(html).toContain("<strong");
    expect(html).toContain("bold");
  });

  it("renders a :::note callout with tone styling", () => {
    expect(html).toContain("Be careful here");
    expect(html).toContain("border-l-4");
  });

  it("renders ::exercise via the injected renderer", () => {
    expect(html).toContain("EXERCISE:m01-ex-1");
  });

  it("renders ::figure via the injected renderer", () => {
    expect(html).toContain("FIGURE:fig-demo");
  });

  it("renders a GFM table as a styled table inside a scroll wrapper", () => {
    expect(html).toContain("<table");
    expect(html).toContain("<th");
    expect(html).not.toContain("|---|");
    expect(html).toContain("overflow-x-auto");
  });
});

describe("LessonMarkdown lesson references", () => {
  const registry = buildRefRegistry([
    { id: "m22", title: "Gestión del riesgo", lessons: [{ id: "m22-l1", title: "Gestionar el riesgo" }] },
    {
      id: "m19",
      title: "Datos de derivados",
      lessons: [
        { id: "m19-l1", title: "Datos de derivados y liquidez" },
        { id: "m19-l2", title: "Mapas de liquidez" },
      ],
    },
  ]);

  const render = (markdown: string) =>
    renderToStaticMarkup(
      <LessonMarkdown
        markdown={markdown}
        renderExercise={() => null}
        renderFigure={() => null}
        refs={{ lessonId: "m19-l2", registry }}
        renderLessonRef={(kind, refId, children) => (
          <a href={`REF:${kind}:${refId}`}>{children}</a>
        )}
      />,
    );

  it("turns a module mention into a link through the injected renderer", () => {
    const html = render("Una costura limpia con **m22**, como en m19-l1.");
    expect(html).toContain('href="REF:module:m22"');
    expect(html).toContain('href="REF:lesson:m19-l1"');
  });

  it("leaves a self-mention, a code span and an unresolvable id as plain text", () => {
    const html = render("Esto es m19-l2, no `m22`, y m99 no existe.");
    expect(html).not.toContain("REF:");
    expect(html).toContain("m99");
  });

  it("is plain text when no registry is wired, exactly as before the feature", () => {
    const html = renderToStaticMarkup(
      <LessonMarkdown markdown={"Ver m22."} renderExercise={() => null} renderFigure={() => null} />,
    );
    expect(html).not.toContain("<a");
    expect(html).toContain("Ver m22.");
  });
});
