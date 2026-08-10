import { act, type ReactElement } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import es from "@/i18n/es.json";
import type { Glossary } from "@/api/course";
import { coursePath } from "@/components/layout/nav";

/**
 * What the glossary page owes the reader, asserted on the rendered DOM rather than on the data:
 * an alias must be a POINTER (never a second copy of the definition), a homonym must show its
 * numbered senses each with its own origin, and every origin must be a link into that lesson.
 */

const GLOSSARY: Glossary = {
  locale: "es",
  terms: [
    {
      id: "g-change-of-character",
      term: "cambio de carácter",
      origin: "m08-l1",
      originTitle: "Estructura de precio",
      definition: "La primera rotura de la secuencia de una tendencia.",
    },
    {
      id: "g-choch",
      term: "CHoCH",
      origin: "m34-l1",
      originTitle: "El dialecto SMC",
      aliasOf: { id: "g-change-of-character", term: "cambio de carácter" },
    },
    {
      id: "g-premium",
      term: "prima",
      origin: null,
      originTitle: null,
      senses: [
        { origin: "m19-l1", originTitle: "Datos de derivados", definition: "Perpetuo sobre el spot." },
        { origin: "m32-l1", originTitle: "La prima entre exchanges", definition: "Entre plataformas." },
      ],
    },
    {
      id: "g-emision",
      term: "emisión",
      origin: "m20-l1",
      originTitle: "Leer la tokenómica",
      definition: "El ritmo al que entran tokens nuevos.",
    },
  ],
};

function lookup(key: string): unknown {
  return key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], es);
}

/** The real ES catalog, interpolated, with i18next's `_one`/`_other` plural suffixes resolved. */
function translate(key: string, params?: Record<string, unknown>): string {
  let template = lookup(key);
  if (typeof template !== "string" && typeof params?.count === "number") {
    template = lookup(`${key}_${params.count === 1 ? "one" : "other"}`);
  }
  if (typeof template !== "string") throw new Error(`missing catalog key ${key}`);
  return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(params?.[name]));
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: translate, i18n: { resolvedLanguage: "es" } }),
  initReactI18next: { type: "3rdParty", init: () => {} },
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: GLOSSARY, isPending: false, isError: false }),
}));

const { GlossaryPage } = await import("./GlossaryPage");

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;

function mount(node: ReactElement): void {
  host = document.createElement("div");
  document.body.appendChild(host);
  act(() => {
    createRoot(host).render(node);
  });
}

function terms(): string[] {
  return [...host.querySelectorAll("h2")].map((h) => (h.textContent ?? "").trim());
}

/** The card a term's heading belongs to. */
function card(term: string): HTMLElement {
  const heading = [...host.querySelectorAll("h2")].find((h) => h.textContent?.trim() === term);
  if (!heading) throw new Error(`no entry for ${term}`);
  return heading.parentElement as HTMLElement;
}

function links(within: HTMLElement): { text: string; href: string }[] {
  return [...within.querySelectorAll("a")].map((a) => ({
    text: (a.textContent ?? "").replace(/\s+/g, " ").trim(),
    href: a.getAttribute("href") ?? "",
  }));
}

beforeEach(() => {
  document.body.innerHTML = "";
  mount(
    <MemoryRouter>
      <GlossaryPage />
    </MemoryRouter>,
  );
});

describe("arriving from a term's tooltip", () => {
  it("scrolls to the entry named in the fragment, which the router does not do by itself", () => {
    // `/glossary#g-premium` is what a lesson tooltip's "full entry" link navigates to. React Router
    // performs no fragment scrolling, and on a cold load the entry is not on the page yet.
    const scrolled: string[] = [];
    Element.prototype.scrollIntoView = function scrollIntoView(this: Element) {
      scrolled.push(this.id);
    };
    document.body.innerHTML = "";
    mount(
      <MemoryRouter initialEntries={[`${coursePath("/glossary")}#g-premium`]}>
        <GlossaryPage />
      </MemoryRouter>,
    );
    expect(scrolled).toEqual(["g-premium"]);
  });
});

describe("the glossary page", () => {
  it("lists entries alphabetically in the reader's locale", () => {
    expect(terms()).toEqual(["cambio de carácter", "CHoCH", "emisión", "prima"]);
  });

  it("links an entry's origin into the lesson that teaches it", () => {
    const found = links(card("cambio de carácter"));
    expect(found).toContainEqual({
      text: "M08-L1 · Estructura de precio",
      href: coursePath("/lessons/m08-l1"),
    });
  });

  it("renders an alias as a pointer, and the definition is not duplicated", () => {
    // An in-glossary jump to the canonical entry, not a lesson link and not a repeated definition.
    expect(links(card("CHoCH"))).toContainEqual({
      text: "cambio de carácter",
      href: "#g-change-of-character",
    });
    const definition = "La primera rotura de la secuencia de una tendencia.";
    const occurrences = (host.textContent ?? "").split(definition).length - 1;
    expect(occurrences).toBe(1);
  });

  it("numbers a homonym's senses and links each sense's own origin", () => {
    const entry = card("prima");
    const text = (entry.textContent ?? "").replace(/\s+/g, " ");
    expect(text).toContain("1. Perpetuo sobre el spot.");
    expect(text).toContain("2. Entre plataformas.");
    const found = links(entry).map((l) => l.href);
    expect(found).toContain(coursePath("/lessons/m19-l1"));
    expect(found).toContain(coursePath("/lessons/m32-l1"));
  });

  it("gives every entry an anchor id, so an alias pointer has somewhere to land", () => {
    for (const term of GLOSSARY.terms) {
      expect(host.querySelector(`#${term.id}`), term.id).not.toBeNull();
    }
  });
});
