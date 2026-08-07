import { act, type ReactElement } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import en from "@/i18n/en.json";

/**
 * What a multi-lesson module page owes the reader: EACH ROW carries its own full estimate, not just the
 * module's aggregate — otherwise a reader cannot tell a 4-minute lesson from a 20-minute one.
 *
 * Rendered rather than computed; the arithmetic is `readingTime.test.ts`'s, the WIRING was what broke.
 */

const MODULE = {
  id: "m09",
  title: "Wyckoff, simplified",
  summary: "Accumulation and distribution as ranges.",
  assumes: [],
  unmetPrereqs: [],
  lessons: [
    { id: "m09-l1", order: 1, title: "The four phases", completed: true, readingSeconds: 9 * 60 },
    { id: "m09-l2", order: 2, title: "Reading the range", completed: false, readingSeconds: 11 * 60 },
  ],
};

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: MODULE, isLoading: false }),
}));

/** The real EN catalog, interpolated: the test asserts the strings a reader actually sees. */
function translate(key: string, params?: Record<string, unknown>): string {
  const template = key
    .split(".")
    .reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], en);
  if (typeof template !== "string") throw new Error(`missing catalog key ${key}`);
  return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(params?.[name]));
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: translate, i18n: { resolvedLanguage: "en" } }),
  // The api client pulls in the i18n bootstrap, which needs this export to exist on the mock.
  initReactI18next: { type: "3rdParty", init: () => {} },
}));

const { ModulePage } = await import("./ModulePage");

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;

function mount(node: ReactElement): void {
  host = document.createElement("div");
  document.body.appendChild(host);
  act(() => {
    createRoot(host).render(node);
  });
}

function rowText(): string[] {
  return [...host.querySelectorAll("a[href^='/lessons/']")].map((row) =>
    (row.textContent ?? "").replace(/\s+/g, " ").trim(),
  );
}

beforeEach(() => {
  document.body.innerHTML = "";
  mount(
    <MemoryRouter initialEntries={["/modules/m09"]}>
      <Routes>
        <Route path="/modules/:moduleId" element={<ModulePage />} />
      </Routes>
    </MemoryRouter>,
  );
});

describe("the module page of a multi-lesson module", () => {
  it("prints every lesson's own estimate on its row", () => {
    const rows = rowText();
    expect(rows).toHaveLength(2);
    expect(rows[0]).toContain("~9 min");
    expect(rows[1]).toContain("~11 min");
  });

  it("keeps a completed lesson's estimate on screen, next to its badge", () => {
    // A lesson you have read still costs what it costs — a re-read is not free, and blanking the row
    // would leave the only completed lesson as the one with no time on it.
    const [read] = rowText();
    expect(read).toContain("Completed");
    expect(read).toContain("~9 min");
  });

  it("still shows the module's REMAINING total in the header, not the sum of the rows", () => {
    // 9 + 11 = 20 minutes of lessons, 11 of them left. The header is the aggregate; the rows are not.
    const header = host.querySelector("h1")?.parentElement?.textContent ?? "";
    expect(header).toContain("~11 min");
    expect(header).not.toContain("~20 min");
  });
});
