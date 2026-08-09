import { act, type ReactElement } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import en from "@/i18n/en.json";
import type { GlossaryEntry } from "@/api/course";
import { buildTermIndex } from "@/lib/glossary/terms";

/**
 * The marked term on screen: hovered with a mouse, tapped on a touch screen, reachable by keyboard.
 *
 * Rendered through the real `LessonMarkdown`, so what these cover is the whole path — annotator,
 * remark plugin, `data-term-id` span, trigger, panel — rather than a hand-built trigger that could
 * agree with nothing the reader sees.
 */

function lookup(key: string): unknown {
  return key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], en);
}

function translate(key: string, params?: Record<string, unknown>): string {
  const template = lookup(key);
  if (typeof template !== "string") throw new Error(`missing catalog key ${key}`);
  return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(params?.[name]));
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: translate, i18n: { resolvedLanguage: "en" } }),
  initReactI18next: { type: "3rdParty", init: () => {} },
}));

const { GlossaryTerm, TermPopoverHost } = await import("./TermPopover");
const { LessonMarkdown } = await import("@/lib/markdown");

const FUNDING: GlossaryEntry = {
  id: "g-funding",
  term: "funding",
  origin: "m04-l1",
  originTitle: "Perpetual futures",
  definition: "A periodic payment between longs and shorts.",
};

const PREMIUM: GlossaryEntry = {
  id: "g-premium",
  term: "premium",
  origin: null,
  originTitle: null,
  senses: [
    { origin: "m17-l1", originTitle: "The basis", definition: "A perp trading above spot." },
    { origin: "m28-l1", originTitle: "Arbitrage", definition: "The gap between two venues." },
  ],
};

const CHOCH: GlossaryEntry = {
  id: "g-choch",
  term: "CHoCH",
  origin: "m30-l1",
  originTitle: "The SMC dialect",
  aliasOf: { id: "g-funding", term: "funding" },
};

const ENTRIES = [FUNDING, PREMIUM, CHOCH];

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
      <TermPopoverHost entries={new Map(ENTRIES.map((entry) => [entry.id, entry]))}>
        <LessonMarkdown
          markdown={markdown}
          renderExercise={() => null}
          renderFigure={() => null}
          glossary={{ lessonId, terms: buildTermIndex(ENTRIES, "en") }}
          renderTerm={(termId, children) => <GlossaryTerm termId={termId}>{children}</GlossaryTerm>}
        />
      </TermPopoverHost>
    </MemoryRouter>,
  );
}

function marks(): HTMLElement[] {
  return [...document.querySelectorAll<HTMLElement>("[data-glossary-term]")];
}

function panel(): HTMLElement | null {
  return document.querySelector<HTMLElement>('[role="tooltip"]');
}

/**
 * React derives `onPointerEnter`/`Leave` from `pointerover`/`pointerout`, so the test has to speak
 * the events the browser actually sends — and carry the `pointerType` the hover/tap split reads.
 */
function pointer(type: string, target: Element, pointerType: "mouse" | "touch"): void {
  act(() => {
    target.dispatchEvent(
      new PointerEvent(type, { bubbles: true, cancelable: true, relatedTarget: null, pointerType }),
    );
  });
}

function hover(target: Element): void {
  pointer("pointerover", target, "mouse");
}
function unhover(target: Element): void {
  pointer("pointerout", target, "mouse");
}
/** A tap: the pointerdown the dismissal listens for, then the click React turns into a toggle. */
function tap(target: Element): void {
  pointer("pointerdown", target, "touch");
  act(() => {
    target.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("a marked term in a lesson", () => {
  it("marks the first occurrence only, and leaves the prose itself untouched", () => {
    lesson("The funding is paid hourly.\n\nMore funding follows.\n");
    expect(marks().map((mark) => mark.textContent)).toEqual(["funding"]);
    expect(host.textContent).toContain("The funding is paid hourly.");
    expect(host.textContent).toContain("More funding follows.");
  });

  it("marks nothing in the lesson the term is taught in", () => {
    lesson("The funding is paid hourly.", "m04-l1");
    expect(marks()).toEqual([]);
  });

  it("is a real button, so a keyboard reader can reach it", () => {
    lesson("The funding is paid hourly.");
    expect(marks()[0].tagName).toBe("BUTTON");
    expect(marks()[0]).toHaveAttribute("type", "button");
  });

  it("shows the definition on hover and takes it away when the pointer leaves", () => {
    lesson("The funding is paid hourly.");
    hover(marks()[0]);
    expect(panel()).toHaveTextContent("A periodic payment between longs and shorts.");
    unhover(marks()[0]);
    expect(panel()).toBeNull();
  });

  it("points at the full entry and at the lesson that teaches the term", () => {
    lesson("The funding is paid hourly.");
    hover(marks()[0]);
    const links = [...(panel()?.querySelectorAll("a") ?? [])].map((a) => a.getAttribute("href"));
    expect(links.some((href) => href?.endsWith("/glossary#g-funding"))).toBe(true);
    expect(links.some((href) => href?.endsWith("/lessons/m04-l1"))).toBe(true);
  });

  it("summarises a homonym's senses rather than choosing one", () => {
    lesson("The premium is wide.");
    hover(marks()[0]);
    expect(panel()).toHaveTextContent("A perp trading above spot.");
    expect(panel()).toHaveTextContent("The gap between two venues.");
  });

  it("shows an alias's canonical definition, not a second hop", () => {
    lesson("A CHoCH prints here.");
    hover(marks()[0]);
    expect(panel()).toHaveTextContent("Another name for");
    expect(panel()).toHaveTextContent("A periodic payment between longs and shorts.");
  });

  it("opens on focus and announces itself, so the definition is not mouse-only", () => {
    lesson("The funding is paid hourly.");
    act(() => marks()[0].focus());
    expect(panel()).not.toBeNull();
    expect(marks()[0].getAttribute("aria-describedby")).toBe(panel()?.id);
  });

  it("marks the term discreetly — a dotted rule, no colour of its own, in every theme", () => {
    lesson("The funding is paid hourly.");
    const className = marks()[0].className;
    expect(className).toContain("border-dotted");
    expect(className).toContain("dark:border-gray-500");
    expect(className).toContain("oled:border-oled-line-strong");
    // Inherits the prose's own weight and colour; the mark must not repaint the word.
    expect(className).toContain("text-[inherit]");
    expect(className).toContain("font-[inherit]");
  });
});

describe("on a touch screen, where hover does not exist", () => {
  it("opens on tap and stays open, since there is no pointer to move away", () => {
    lesson("The funding is paid hourly.");
    tap(marks()[0]);
    expect(panel()).toHaveTextContent("A periodic payment between longs and shorts.");
    // A stray pointer-leave must not take a tapped panel away.
    unhover(marks()[0]);
    expect(panel()).not.toBeNull();
  });

  it("closes on a second tap", () => {
    lesson("The funding is paid hourly.");
    tap(marks()[0]);
    tap(marks()[0]);
    expect(panel()).toBeNull();
  });

  it("closes on Escape", () => {
    lesson("The funding is paid hourly.");
    tap(marks()[0]);
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    expect(panel()).toBeNull();
  });

  it("closes on a tap outside it", () => {
    lesson("The funding is paid hourly.");
    tap(marks()[0]);
    pointer("pointerdown", document.body, "touch");
    expect(panel()).toBeNull();
  });

  it("carries its own dismiss control, which a hovered panel never needs", () => {
    lesson("The funding is paid hourly.");
    hover(marks()[0]);
    expect(panel()?.querySelector("button")).toBeNull();

    tap(marks()[0]);
    const close = panel()?.querySelector("button");
    expect(close).toHaveAttribute("aria-label", en.glossary.closeDefinition);
    act(() => {
      close?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(panel()).toBeNull();
  });
});
