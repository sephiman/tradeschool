import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { LessonMarkdown } from "./markdown";

const md = `# Title

Some **bold** text.

:::note{type=warning}
Be careful here.
:::

::exercise{id=m01-ex-1}

::figure{id=fig-demo}
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
});
