import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act, type ReactElement } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { coursePath, HOME_PATH } from "@/components/layout/nav";
import { manifestLessons, manifestModules } from "@/test/courseContent";

/**
 * Page URLs are course-scoped, and the pre-scoping URLs still land somewhere.
 *
 * The redirect table is reproduced here rather than imported from App.tsx, which drags in the whole
 * app (auth, query client, charts). What is asserted is the RULE the app implements: an old path
 * becomes the same path under the course, and `/course` becomes the course root.
 */

function LegacyCourseRedirect() {
  const { pathname, search } = useLocation();
  const rest = pathname === "/course" ? "" : pathname;
  return <Navigate to={`${coursePath(rest)}${search}`} replace />;
}

function Where() {
  const { pathname, search } = useLocation();
  return <p data-testid="where">{pathname + search}</p>;
}

let host: HTMLDivElement;

function mountAt(entry: string): string {
  host = document.createElement("div");
  document.body.appendChild(host);
  const tree: ReactElement = (
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path={`${coursePath()}/*`} element={<Where />} />
        <Route path="/course" element={<LegacyCourseRedirect />} />
        <Route path="/modules/:moduleId" element={<LegacyCourseRedirect />} />
        <Route path="/lessons/:lessonId" element={<LegacyCourseRedirect />} />
        <Route path="/glossary" element={<LegacyCourseRedirect />} />
        <Route path="/stats" element={<LegacyCourseRedirect />} />
        <Route path="/exams/*" element={<LegacyCourseRedirect />} />
        <Route path="/" element={<Navigate to={HOME_PATH} replace />} />
      </Routes>
    </MemoryRouter>
  );
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  act(() => {
    createRoot(host).render(tree);
  });
  return host.querySelector('[data-testid="where"]')?.textContent ?? "";
}

describe("page URLs carry the course", () => {
  it("home is the course root, not a bare /course", () => {
    expect(HOME_PATH).toBe("/courses/crypto-futures");
    expect(coursePath("/glossary")).toBe("/courses/crypto-futures/glossary");
  });

  it.each([
    ["/course", "/courses/crypto-futures"],
    ["/glossary", "/courses/crypto-futures/glossary"],
    ["/stats", "/courses/crypto-futures/stats"],
    ["/lessons/m03-l1", "/courses/crypto-futures/lessons/m03-l1"],
    ["/modules/m09", "/courses/crypto-futures/modules/m09"],
    ["/exams", "/courses/crypto-futures/exams"],
    ["/exams/abc/review", "/courses/crypto-futures/exams/abc/review"],
  ])("a bookmark of %s lands on %s", (old, scoped) => {
    expect(mountAt(old)).toBe(scoped);
  });

  it("keeps the query string across a redirect", () => {
    expect(mountAt("/glossary?q=funding")).toBe("/courses/crypto-futures/glossary?q=funding");
  });

  it("sends the bare root to home", () => {
    expect(mountAt("/")).toBe(HOME_PATH);
  });
});

/** The module/lesson routes as App.tsx declares them — reproduced, not imported, as above. */
function mountContent(entry: string): string {
  host = document.createElement("div");
  document.body.appendChild(host);
  const tree: ReactElement = (
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path={coursePath("/modules/:moduleId")} element={<Where />} />
        <Route path={coursePath("/lessons/:lessonId")} element={<Where />} />
      </Routes>
    </MemoryRouter>
  );
  act(() => {
    createRoot(host).render(tree);
  });
  return host.querySelector('[data-testid="where"]')?.textContent ?? "";
}

describe("a display id names its current holder", () => {
  /** Both renumbering outcomes: an id reused by the permutation, and the four re-issued by append. */
  it.each([
    "/modules/m17", // reused by the permutation: old m17 (derivatives) is m19 now, macro owns m17
    "/modules/m31", // re-issued by append: old m31 (trendlines) is m15 now, the order book owns m31
    "/modules/m32",
    "/modules/m33",
    "/modules/m34",
    "/lessons/m31-l1",
    "/lessons/m32-l1",
    "/lessons/m33-l1",
    "/lessons/m34-l1",
  ])("%s serves its page and is not redirected away", (path) => {
    expect(mountContent(coursePath(path))).toBe(coursePath(path));
  });

  /** The grep-level half, like `api/urls.test.ts`: the cases above can only name ids that exist today. */
  it("App.tsx hard-codes no content id, which a static route would shadow", () => {
    const source = readFileSync(resolve(__dirname, "App.tsx"), "utf8");
    // Any id, not just a live one: ids are append-only, so today's vacant id is tomorrow's module.
    const hardCoded = [...source.matchAll(/\bm\d\d(-(l|ex-)\d+)?\b/g)].map((m) => m[0]);
    const live = new Set([...manifestModules(), ...manifestLessons()].map((entry) => entry.id));
    expect(hardCoded.map((id) => (live.has(id) ? `${id} (live)` : id))).toEqual([]);
  });
});
