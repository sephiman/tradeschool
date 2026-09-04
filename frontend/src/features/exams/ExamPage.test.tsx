import { act, type ReactElement } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import en from "@/i18n/en.json";

/**
 * Starting an exam when one is already open.
 *
 * The server abandons an open sitting of the SAME scope and block when a new one starts, and says
 * nothing about it. That is a destructive act performed on a button press meant to be constructive,
 * so the page asks first — and only for the sitting that would actually be lost. A different scope or
 * a different block touches nothing, so it must not ask: a confirmation that fires when nothing is at
 * stake is one readers learn to dismiss without reading.
 */

const GLOBAL_SITTING = {
  id: "exam-global",
  scope: "global" as const,
  blockId: null,
  blockTitle: null,
  status: "open" as const,
  createdAt: "2026-09-01T10:00:00Z",
  finishedAt: null,
  result: null,
  questions: Array.from({ length: 34 }, (_, index) => ({ answered: index < 3 })),
};

const BLOCK_A_SITTING = {
  ...GLOBAL_SITTING,
  id: "exam-block-a",
  scope: "block" as const,
  blockId: "block-a",
  blockTitle: "Foundations",
  questions: Array.from({ length: 8 }, (_, index) => ({ answered: index < 1 })),
};

const COURSE = {
  blocks: [
    { id: "block-a", title: "Foundations", modules: [{ id: "m01", exercisesTotal: 2 }] },
    { id: "block-b", title: "Instruments", modules: [{ id: "m04", exercisesTotal: 2 }] },
  ],
};

let openSittings: unknown[] = [];
const startMutate = vi.fn();
const navigate = vi.fn();

vi.mock("@tanstack/react-query", () => ({
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    const which = queryKey[1];
    if (which === "open") return { data: openSittings, isLoading: false };
    if (which === "history") return { data: [], isLoading: false };
    return { data: COURSE, isLoading: false };
  },
  useMutation: () => ({ mutate: startMutate, isPending: false }),
  useQueryClient: () => ({ invalidateQueries: () => {} }),
}));

vi.mock("react-router-dom", async (original) => ({
  ...(await original<typeof import("react-router-dom")>()),
  useNavigate: () => navigate,
}));

function translate(key: string, params?: Record<string, unknown>): string {
  const template = key
    .split(".")
    .reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], en);
  if (typeof template !== "string") throw new Error(`missing catalog key ${key}`);
  return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(params?.[name]));
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: translate, i18n: { resolvedLanguage: "en" } }),
  initReactI18next: { type: "3rdParty", init: () => {} },
}));

const { ExamPage } = await import("./ExamPage");

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;

function mount(node: ReactElement): void {
  host = document.createElement("div");
  document.body.appendChild(host);
  act(() => {
    createRoot(host).render(node);
  });
}

function page(): void {
  document.body.innerHTML = "";
  mount(
    <MemoryRouter>
      <ExamPage />
    </MemoryRouter>,
  );
}

function button(label: string): HTMLButtonElement {
  const found = [...document.querySelectorAll("button")].find((b) => b.textContent?.trim() === label);
  if (!found) throw new Error(`no button labelled "${label}"`);
  return found as HTMLButtonElement;
}

function dialog(): HTMLElement | null {
  return document.querySelector<HTMLElement>('[role="alertdialog"]');
}

function click(el: Element): void {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

beforeEach(() => {
  openSittings = [];
  startMutate.mockClear();
  navigate.mockClear();
  document.body.innerHTML = "";
});

describe("starting an exam that would abandon an open one", () => {
  it("asks first, naming the sitting and how far into it the reader is", () => {
    openSittings = [GLOBAL_SITTING];
    page();
    click(button(translate("exam.startGlobal")));

    expect(startMutate).not.toHaveBeenCalled();
    expect(dialog()).not.toBeNull();
    expect(dialog()).toHaveTextContent(translate("exam.global"));
    expect(dialog()).toHaveTextContent(translate("exam.conflictAnswered", { done: 3, total: 34 }));
  });

  it("offers continuing as the primary action, and starting over as the destructive one", () => {
    openSittings = [GLOBAL_SITTING];
    page();
    click(button(translate("exam.startGlobal")));

    const resume = button(translate("exam.conflictResume"));
    const fresh = button(translate("exam.conflictStartNew"));
    expect(resume.className).toContain("bg-primary");
    expect(fresh.className).toContain("text-red");

    click(resume);
    expect(navigate).toHaveBeenCalledWith("/courses/crypto-futures/exams/exam-global");
    expect(startMutate).not.toHaveBeenCalled();
  });

  it("dismisses without starting anything and without moving the reader", () => {
    openSittings = [GLOBAL_SITTING];
    page();
    click(button(translate("exam.startGlobal")));
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });

    expect(dialog()).toBeNull();
    expect(startMutate).not.toHaveBeenCalled();
    // Escape is not the primary action: it must not navigate to the open sitting either.
    expect(navigate).not.toHaveBeenCalled();
  });

  it("starts the new one only when that is explicitly chosen", () => {
    openSittings = [GLOBAL_SITTING];
    page();
    click(button(translate("exam.startGlobal")));
    click(button(translate("exam.conflictStartNew")));

    expect(startMutate).toHaveBeenCalledWith({ scope: "global", blockId: undefined });
    expect(dialog()).toBeNull();
  });
});

describe("starting an exam that would abandon nothing", () => {
  it("does not ask when the open sitting is a different scope", () => {
    openSittings = [GLOBAL_SITTING];
    page();
    click(button("Foundations"));

    expect(dialog()).toBeNull();
    expect(startMutate).toHaveBeenCalledWith({ scope: "block", blockId: "block-a" });
  });

  it("does not ask when the open sitting is a different block of the same scope", () => {
    openSittings = [BLOCK_A_SITTING];
    page();
    click(button("Instruments"));

    expect(dialog()).toBeNull();
    expect(startMutate).toHaveBeenCalledWith({ scope: "block", blockId: "block-b" });
  });

  it("does ask when it is the same block", () => {
    openSittings = [BLOCK_A_SITTING];
    page();
    click(button("Foundations"));

    expect(startMutate).not.toHaveBeenCalled();
    expect(dialog()).toHaveTextContent("Foundations");
    expect(dialog()).toHaveTextContent(translate("exam.conflictAnswered", { done: 1, total: 8 }));
  });

  it("does not ask when nothing is open at all", () => {
    page();
    click(button(translate("exam.startGlobal")));
    expect(dialog()).toBeNull();
    expect(startMutate).toHaveBeenCalledWith({ scope: "global", blockId: undefined });
  });
});
