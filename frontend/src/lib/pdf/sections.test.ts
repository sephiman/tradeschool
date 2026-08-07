import { describe, expect, it } from "vitest";
import type { LayoutNode } from "@/lib/pdf/pagination";
import { createSectionTracker, type SectionTracker } from "@/lib/pdf/sections";
import { runningTitle } from "@/lib/pdf/document";

/** Which section a page belongs to. The interesting cases are the boundaries. */

/** A laid-out section heading, as pdfmake hands it to the layout hook. */
function heading(id: string, page: number): LayoutNode {
  return {
    id,
    text: "irrelevant",
    pageNumbers: [page],
    pages: 1,
    stack: false,
    startPosition: {
      pageNumber: page,
      left: 56,
      top: 54,
      verticalRatio: 0,
      horizontalRatio: 0,
      pageInnerHeight: 726,
      pageInnerWidth: 483,
      pageOrientation: "portrait",
    },
  } as LayoutNode;
}

/** The real book's shape: three blocks and the answer key, at the pages they actually landed on. */
function tracked(): SectionTracker {
  const sections = createSectionTracker();
  sections.declare("section-block-a-0", "Fundamentos");
  sections.declare("section-block-b-0", "El instrumento");
  sections.declare("section-block-c-0", "Análisis técnico");
  sections.declare("section-answer-key-0", "Solucionario");
  sections.observe(heading("section-block-a-0", 5));
  sections.observe(heading("section-block-b-0", 23));
  sections.observe(heading("section-block-c-0", 40));
  sections.observe(heading("section-answer-key-0", 195));
  return sections;
}

describe("the section a page belongs to", () => {
  const sections = tracked();

  it("is nothing on the pages before the first block", () => {
    // The cover and the table of contents belong to no section, and must not borrow the first one.
    expect(sections.at(1)).toBeUndefined();
    expect(sections.at(4)).toBeUndefined();
  });

  it("is the new block on the very page it starts", () => {
    expect(sections.at(5)).toBe("Fundamentos");
    expect(sections.at(23)).toBe("El instrumento");
    expect(sections.at(40)).toBe("Análisis técnico");
  });

  it("is still the old block on the page before the next one starts", () => {
    expect(sections.at(22)).toBe("Fundamentos");
    expect(sections.at(39)).toBe("El instrumento");
  });

  it("holds through the middle of a block", () => {
    expect(sections.at(10)).toBe("Fundamentos");
    expect(sections.at(100)).toBe("Análisis técnico");
  });

  it("is the answer key from its first page to the end of the book", () => {
    expect(sections.at(194)).toBe("Análisis técnico");
    expect(sections.at(195)).toBe("Solucionario");
    expect(sections.at(9_999)).toBe("Solucionario");
  });

  it("lists what it found in page order", () => {
    expect(sections.resolved().map((s) => `${s.title}@${s.page}`)).toEqual([
      "Fundamentos@5",
      "El instrumento@23",
      "Análisis técnico@40",
      "Solucionario@195",
    ]);
  });
});

describe("a tracker that has seen nothing", () => {
  it("names no section rather than guessing", () => {
    // What a single render would leave behind: the export renders twice precisely so the mapping is
    // resolved before the file is written, and the footer degrades to the plain course title.
    const sections = createSectionTracker();
    sections.declare("section-block-a-0", "Fundamentos");
    expect(sections.at(50)).toBeUndefined();
    expect(sections.resolved()).toEqual([]);
  });

  it("ignores nodes that are not declared sections", () => {
    const sections = createSectionTracker();
    sections.declare("section-block-a-0", "Fundamentos");
    sections.observe(heading("note-m08-l1-0", 12));
    sections.observe(heading("figure-m08-l1-1", 13));
    expect(sections.resolved()).toEqual([]);
  });
});

describe("what the footer prints on the left", () => {
  it("is the book, then where in it the reader is", () => {
    expect(runningTitle("Futuros de cripto, desde cero", "Fundamentos")).toBe(
      "Futuros de cripto, desde cero · Fundamentos",
    );
  });

  it("is the book alone before the first block", () => {
    expect(runningTitle("Crypto Futures, from Zero", undefined)).toBe("Crypto Futures, from Zero");
  });
});
