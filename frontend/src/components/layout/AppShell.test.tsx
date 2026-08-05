import { act, useEffect, type ReactElement } from "react";
import { createRoot } from "react-dom/client";
import { createMemoryRouter, Outlet, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import en from "@/i18n/en.json";
import { HOME_PATH } from "@/components/layout/nav";

/**
 * The header wordmark is the way back to the start of the course from any depth.
 *
 * Two properties are easy to get wrong and are the reason this file exists. First, the click must be
 * **intercepted** — a wordmark wrapped in a bare `<a href>` looks identical and works, by throwing the
 * whole SPA away and re-fetching it. Second, the history must stay honest in *both* directions: from a
 * lesson the visit has to PUSH, or Back no longer returns to the lesson you left; on the course page
 * itself it has to REPLACE, or a reader who taps the logo twice has to press Back twice to escape.
 * Those two pull in opposite directions, which is why the link passes no `replace` prop at all and
 * leans on react-router's same-path rule — a rule worth pinning, since it is not ours to change.
 */

const USER = { username: "juanjo", locale: "en" as const };

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({ user: USER, logout: async () => {} }),
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
  initReactI18next: { type: "3rdParty", init: () => {} },
}));

const { AppShell } = await import("./AppShell");

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let courseMounts = 0;

function CoursePageProbe() {
  useEffect(() => {
    courseMounts += 1;
  }, []);
  return <p>course page</p>;
}

/** The shell nested over the two routes this test needs — the app wires the same shell over the same
 * paths through an inner `<Routes>`; what the wordmark does depends only on the router context. */
function mountAt(entry: string): ReturnType<typeof createMemoryRouter> {
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: (
          <AppShell>
            <Outlet />
          </AppShell>
        ),
        children: [
          { path: "course", element: <CoursePageProbe /> },
          { path: "lessons/:lessonId", element: <p>lesson page</p> },
        ],
      },
    ],
    { initialEntries: [entry] },
  );
  render(<RouterProvider router={router} />);
  return router;
}

function render(node: ReactElement): void {
  host = document.createElement("div");
  document.body.appendChild(host);
  act(() => {
    createRoot(host).render(node);
  });
}

function logo(): HTMLAnchorElement {
  const el = host.querySelector<HTMLAnchorElement>(`header a[href="${HOME_PATH}"]`);
  if (!el) throw new Error("the header has no link to home");
  return el;
}

/** A real left-click, so react-router's own guards (button, modifiers, target) apply as in a browser.
 * The event is returned: whether it was default-prevented is what tells us the SPA kept the page. */
function click(el: HTMLElement): MouseEvent {
  const event = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 });
  act(() => {
    el.dispatchEvent(event);
  });
  return event;
}

beforeEach(() => {
  document.body.innerHTML = "";
  courseMounts = 0;
});

describe("the header wordmark", () => {
  it("takes a reader from a deep page back to the start of the course", () => {
    const router = mountAt("/lessons/m09-l2");
    expect(host.textContent).toContain("lesson page");

    click(logo());

    expect(router.state.location.pathname).toBe(HOME_PATH);
    expect(host.textContent).toContain("course page");
  });

  it("navigates client-side, without handing the click to the browser", () => {
    mountAt("/lessons/m09-l2");
    expect(click(logo()).defaultPrevented).toBe(true);
  });

  it("leaves the lesson on the stack, so Back returns to it", () => {
    const router = mountAt("/lessons/m09-l2");
    click(logo());
    expect(router.state.historyAction).toBe("PUSH");
  });

  it("adds no history entry when the reader is already home", () => {
    const router = mountAt(HOME_PATH);
    click(logo());
    // Same path → react-router replaces rather than pushes, so one tap needs one Back, not two.
    expect(router.state.historyAction).toBe("REPLACE");
    expect(router.state.location.pathname).toBe(HOME_PATH);
  });

  it("does not remount the page it is already showing", () => {
    mountAt(HOME_PATH);
    expect(courseMounts).toBe(1);
    click(logo());
    // Re-navigating home is not a reset: the matched route is the same one, so whatever state the
    // page was holding (an open module, a scrolled position) survives the click.
    expect(courseMounts).toBe(1);
  });

  it("is reachable and named for the keyboard and for screen readers", () => {
    mountAt(HOME_PATH);
    const el = logo();
    // A real anchor with an href: focusable in tab order and activated by Enter natively, which is
    // why the component adds no key handler of its own (jsdom cannot synthesize that activation).
    expect(el.tagName).toBe("A");
    expect(el.hasAttribute("tabindex")).toBe(false);
    const label = el.getAttribute("aria-label") ?? "";
    expect(label).toBe("TradeSchool — home");
    // WCAG 2.5.3: the accessible name contains the visible text, so "TradeSchool" spoken at a voice
    // control matches the word on screen.
    expect(label).toContain((el.textContent ?? "").trim());
  });

  it("keeps the wordmark's own type, adding only interaction affordances", () => {
    mountAt(HOME_PATH);
    const classes = logo().className.split(/\s+/);
    // No layout shift: the wordmark reads exactly as it did as an inert span…
    expect(classes).toEqual(expect.arrayContaining(["shrink-0", "text-lg", "font-semibold", "text-primary"]));
    // …and gains no box of its own around it.
    expect(classes.filter((c) => /^-?[pm][xytrbl]?-/.test(c))).toEqual([]);
    // Hover and focus are visible, and the focus ring's offset works on the dark header too.
    expect(classes).toEqual(
      expect.arrayContaining(["hover:opacity-90", "focus:ring-2", "dark:focus:ring-offset-gray-900"]),
    );
  });
});
