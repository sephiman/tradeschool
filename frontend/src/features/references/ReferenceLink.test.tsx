import { act, type ReactElement } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildRefRegistry } from "@/lib/refs/registry";

/**
 * A lesson reference on screen: a real link, titled on hover, silent on touch.
 *
 * Rendered through the real `LessonMarkdown` — annotator, remark plugin, `data-ref-id` span, link,
 * panel — so what these cover is the same path a reader's `m22` takes, not a hand-built anchor.
 */

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { resolvedLanguage: "en" },
  }),
  initReactI18next: { type: "3rdParty", init: () => {} },
}));

const { TermPopoverHost } = await import("@/features/glossary/TermPopover");
const { ReferenceLink } = await import("./ReferenceLink");
const { LessonMarkdown, Prose } = await import("@/lib/markdown");
const { ReferenceProvider } = await import("./ReferenceProvider");

const REGISTRY = buildRefRegistry([
  {
    id: "m19",
    title: "Derivatives data and liquidity",
    summary: "Open interest read with price, and funding as a crowding gauge.",
    lessons: [
      {
        id: "m19-l1",
        title: "Derivatives data and liquidity",
        summary: "What OI and funding say.",
      },
      {
        id: "m19-l2",
        title: "Liquidity maps and squeezes",
        summary: "Where stops pile up, and how a sweep becomes a cascade.",
      },
    ],
  },
  {
    id: "m22",
    title: "Risk management",
    summary: "Size from the stop, and cap the correlated cluster.",
    lessons: [
      {
        id: "m22-l1",
        title: "Managing risk",
        summary: "Risk a fixed small fraction.",
      },
    ],
  },
]);

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;

function mount(node: ReactElement): void {
  host = document.createElement("div");
  document.body.appendChild(host);
  act(() => {
    createRoot(host).render(node);
  });
}

function lesson(markdown: string, lessonId = "m05-l1"): void {
  document.body.innerHTML = "";
  mount(
    <MemoryRouter>
      <TermPopoverHost entries={new Map()}>
        <LessonMarkdown
          markdown={markdown}
          renderExercise={() => null}
          renderFigure={() => null}
          refs={{ lessonId, registry: REGISTRY }}
          renderLessonRef={(_kind, refId, children) => {
            const target = REGISTRY.resolve(refId);
            return target ? (
              <ReferenceLink target={target}>{children}</ReferenceLink>
            ) : (
              children
            );
          }}
        />
      </TermPopoverHost>
    </MemoryRouter>,
  );
}

function links(): HTMLAnchorElement[] {
  return [...host.querySelectorAll<HTMLAnchorElement>("a")];
}

function panel(): HTMLElement | null {
  return document.getElementById("glossary-term-popover");
}

function click(target: Element, init: MouseEventInit = {}): void {
  act(() => {
    target.dispatchEvent(
      new MouseEvent("click", { bubbles: true, cancelable: true, ...init }),
    );
  });
}

function goAction(): HTMLAnchorElement | null {
  return (
    panel()?.querySelector<HTMLAnchorElement>("[data-reference-go]") ?? null
  );
}

function pointer(
  type: string,
  target: Element,
  pointerType: "mouse" | "touch",
): void {
  act(() => {
    target.dispatchEvent(
      new PointerEvent(type, {
        bubbles: true,
        cancelable: true,
        relatedTarget: null,
        pointerType,
      }),
    );
  });
}

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("a lesson reference in prose", () => {
  it("links a lesson mention to that lesson, course-scoped", () => {
    lesson("As **m19-l2** showed.");
    expect(links().map((a) => a.getAttribute("href"))).toEqual([
      "/courses/crypto-futures/lessons/m19-l2",
    ]);
    expect(links()[0].textContent).toBe("m19-l2");
  });

  it("links a multi-lesson module to its module page, a single-lesson one straight to the lesson", () => {
    lesson("See m19 and then m22.");
    expect(links().map((a) => a.getAttribute("href"))).toEqual([
      "/courses/crypto-futures/modules/m19",
      "/courses/crypto-futures/lessons/m22-l1",
    ]);
  });

  it("does not link the lesson to itself", () => {
    lesson("This is m19-l2, which builds on m19-l1.", "m19-l2");
    expect(links().map((a) => a.textContent)).toEqual(["m19-l1"]);
  });

  it("shows the target's title on hover and takes it away when the pointer leaves", () => {
    lesson("A clean seam with m22.");
    pointer("pointerover", links()[0], "mouse");
    expect(panel()).toHaveTextContent("M22 · Risk management");
    pointer("pointerout", links()[0], "mouse");
    expect(panel()).toBeNull();
  });

  it("opens no preview from touch — the tap navigates, it does not peek", () => {
    lesson("A clean seam with m22.");
    pointer("pointerover", links()[0], "touch");
    expect(panel()).toBeNull();
  });

  it("opens on focus and announces itself, so the title is not mouse-only", () => {
    lesson("A clean seam with m22.");
    act(() => links()[0].focus());
    expect(panel()).not.toBeNull();
    expect(links()[0].getAttribute("aria-describedby")).toBe(panel()?.id);
  });

  it("dresses the link like a term mark — dotted rule, no colour of its own, in every theme", () => {
    lesson("A clean seam with m22.");
    const className = links()[0].className;
    expect(className).toContain("border-dotted");
    expect(className).toContain("dark:border-gray-500");
    expect(className).toContain("oled:border-oled-line-strong");
    expect(className).not.toContain("text-primary");
  });
});

describe("the reference popover", () => {
  it("shows the module's own summary for a module mention", () => {
    lesson("A clean seam with m22.");
    click(links()[0]);
    expect(panel()).toHaveTextContent(
      "Size from the stop, and cap the correlated cluster.",
    );
    expect(panel()).toHaveTextContent("reference.kindModule");
  });

  it("shows the lesson's own summary for a lesson mention, attributed to its module", () => {
    lesson("As **m19-l2** showed.");
    click(links()[0]);
    expect(panel()).toHaveTextContent(
      "Where stops pile up, and how a sweep becomes a cascade.",
    );
    expect(panel()).toHaveTextContent("reference.kindLesson");
    // Attribution: a lesson title means little without the module it sits in.
    expect(panel()).toHaveTextContent("M19 · Derivatives data and liquidity");
    // ...and never the module's summary in place of the lesson's.
    expect(panel()).not.toHaveTextContent("Open interest read with price");
  });

  it("carries the navigation as an action rather than performing it on the tap", () => {
    lesson("A clean seam with m22.");
    click(links()[0]);
    // A single-lesson module lands on its only lesson, but the reader asked for the MODULE, so that
    // is what the action offers to open.
    expect(goAction()?.getAttribute("href")).toBe(
      "/courses/crypto-futures/lessons/m22-l1",
    );
    expect(goAction()?.textContent).toContain("reference.goToModule");

    lesson("As **m19-l2** showed.");
    click(links()[0]);
    expect(goAction()?.getAttribute("href")).toBe(
      "/courses/crypto-futures/lessons/m19-l2",
    );
    expect(goAction()?.textContent).toContain("reference.goToLesson");
  });

  it("moves focus to the action when opened, so it is reachable by keyboard", () => {
    lesson("A clean seam with m22.");
    click(links()[0]);
    expect(document.activeElement).toBe(goAction());
  });

  it("closes on Escape and hands focus back to the mention", () => {
    lesson("A clean seam with m22.");
    click(links()[0]);
    act(() => {
      document.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Escape", bubbles: true }),
      );
    });
    expect(panel()).toBeNull();
    expect(document.activeElement).toBe(links()[0]);
  });

  it("lets a modified click through to the browser, so open-in-new-tab still works", () => {
    lesson("A clean seam with m22.");
    const event = new MouseEvent("click", {
      bubbles: true,
      cancelable: true,
      metaKey: true,
    });
    act(() => {
      links()[0].dispatchEvent(event);
    });
    expect(event.defaultPrevented).toBe(false);
    expect(panel()).toBeNull();
  });

  it("is announced as a dialog once pinned, and stays a tooltip while merely hovered", () => {
    lesson("A clean seam with m22.");
    pointer("pointerover", links()[0], "mouse");
    expect(panel()?.getAttribute("role")).toBe("tooltip");
    click(links()[0]);
    expect(panel()?.getAttribute("role")).toBe("dialog");
    expect(panel()?.getAttribute("aria-labelledby")).toBe(
      "glossary-term-popover-title",
    );
  });
});

/** Exercise prose: no lesson, no directives — the same mark, through `Prose` and the provider. */
function prompt(markdown: string): void {
  document.body.innerHTML = "";
  mount(
    <MemoryRouter>
      <TermPopoverHost entries={new Map()}>
        <ReferenceProvider registry={REGISTRY}>
          <Prose markdown={markdown} />
        </ReferenceProvider>
      </TermPopoverHost>
    </MemoryRouter>,
  );
}

describe("a reference inside exercise prose", () => {
  it("is the same affordance as one in the lesson body", () => {
    prompt("Which of these is **m19-l2**'s liquidity pocket?");
    expect(links().map((a) => a.getAttribute("href"))).toEqual([
      "/courses/crypto-futures/lessons/m19-l2",
    ]);
    click(links()[0]);
    expect(panel()).toHaveTextContent("Where stops pile up, and how a sweep becomes a cascade.");
    expect(goAction()?.textContent).toContain("reference.goToLesson");
  });

  it("marks a mention of the lesson it is read in, because an exam has no page to be self-referential to", () => {
    prompt("As m19-l2 showed, and m22 too.");
    expect(links().map((a) => a.textContent)).toEqual(["m19-l2", "m22"]);
  });

  it("renders plain text with no provider above it, rather than failing", () => {
    document.body.innerHTML = "";
    mount(
      <MemoryRouter>
        <Prose markdown="As m19-l2 showed." />
      </MemoryRouter>,
    );
    expect(links()).toEqual([]);
    expect(host.textContent).toContain("m19-l2");
  });
});
