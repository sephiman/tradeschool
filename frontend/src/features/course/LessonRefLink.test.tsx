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
  useTranslation: () => ({ t: (key: string) => key, i18n: { resolvedLanguage: "en" } }),
  initReactI18next: { type: "3rdParty", init: () => {} },
}));

const { TermPopoverHost } = await import("@/features/glossary/TermPopover");
const { LessonRefLink } = await import("./LessonRefLink");
const { LessonMarkdown } = await import("@/lib/markdown");

const REGISTRY = buildRefRegistry([
  {
    id: "m19",
    title: "Derivatives data and liquidity",
    lessons: [
      { id: "m19-l1", title: "Derivatives data and liquidity" },
      { id: "m19-l2", title: "Liquidity maps and squeezes" },
    ],
  },
  { id: "m22", title: "Risk management", lessons: [{ id: "m22-l1", title: "Managing risk" }] },
]);

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

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
            return target ? <LessonRefLink target={target}>{children}</LessonRefLink> : children;
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
  return document.querySelector<HTMLElement>('[role="tooltip"]');
}

function pointer(type: string, target: Element, pointerType: "mouse" | "touch"): void {
  act(() => {
    target.dispatchEvent(
      new PointerEvent(type, { bubbles: true, cancelable: true, relatedTarget: null, pointerType }),
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
