import { act, type ReactElement } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { coursePath, HOME_PATH } from "@/components/layout/nav";

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

/** Same reproduction rule as above: the vacated-id table App.tsx implements, not App.tsx itself. */
function mountRenumbered(entry: string): string {
  host = document.createElement("div");
  document.body.appendChild(host);
  const modules: Record<string, string> = { m31: "m15", m32: "m16", m33: "m28", m34: "m21" };
  const lessons: Record<string, string> = { "m31-l2": "m15-l2", "m34-l2": "m21-l2" };
  const tree: ReactElement = (
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        {Object.entries(modules).map(([old, now]) => (
          <Route
            key={old}
            path={coursePath(`/modules/${old}`)}
            element={<Navigate to={coursePath(`/modules/${now}`)} replace />}
          />
        ))}
        {Object.entries(lessons).map(([old, now]) => (
          <Route
            key={old}
            path={coursePath(`/lessons/${old}`)}
            element={<Navigate to={coursePath(`/lessons/${now}`)} replace />}
          />
        ))}
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

describe("the 2026-08-10 renumbering's vacated ids", () => {
  it.each([
    ["/modules/m31", "/modules/m15"],
    ["/modules/m34", "/modules/m21"],
    ["/lessons/m31-l2", "/lessons/m15-l2"],
    ["/lessons/m34-l2", "/lessons/m21-l2"],
  ])("a bookmark of %s lands on %s", (old, now) => {
    expect(mountRenumbered(coursePath(old))).toBe(coursePath(now));
  });

  it("a REUSED old id is a live page, not a redirect (the permutation makes it ambiguous)", () => {
    // Old m17 (derivatives) was renumbered to m19, and macro now owns m17: the URL stays.
    expect(mountRenumbered(coursePath("/modules/m17"))).toBe(coursePath("/modules/m17"));
  });
});
