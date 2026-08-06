import type { LayoutNode } from "@/lib/pdf/pagination";

/**
 * Which top-level section a page belongs to, for the running footer.
 *
 * pdfmake hands the footer callback a page number and nothing else — no notion of what is printed on
 * the page — and the page a block starts on is not known until the document has been laid out. So the
 * two halves are split: the document *declares* its sections while it is being built, the layout
 * *observes* where each one landed, and the footer *asks* which section a page falls in.
 *
 * The observation rides on the `pageBreakBefore` hook, which pdfmake calls once per node with its
 * final position. That is complete only once a whole render has finished, which is why the export
 * renders twice — see `generate.ts`. Until then `at()` simply answers nothing, and the footer prints
 * what it always printed.
 */

/** Id prefix for a section heading, in the `<kind>-<source>-<ordinal>` scheme the print ids use. */
export const SECTION_ID = "section";

export interface ResolvedSection {
  id: string;
  title: string;
  /** First page the section's content appears on. */
  page: number;
}

export interface SectionTracker {
  /** Called while the document is built: this heading opens a top-level section. */
  declare(id: string, title: string): void;
  /** Called during layout for every node; records where a declared section landed. */
  observe(node: LayoutNode): void;
  /** The section a page belongs to, or undefined for the pages before the first one (cover, contents). */
  at(page: number): string | undefined;
  /** Every section that has been located, in page order. Empty before the first render completes. */
  resolved(): ResolvedSection[];
}

export function createSectionTracker(): SectionTracker {
  const titles = new Map<string, string>();
  const pages = new Map<string, number>();

  return {
    declare(id, title) {
      titles.set(id, title);
    },

    observe(node) {
      const id = typeof node.id === "string" ? node.id : undefined;
      if (id === undefined || !titles.has(id)) return;
      pages.set(id, node.startPosition.pageNumber);
    },

    resolved() {
      return [...pages]
        .map(([id, page]) => ({ id, title: titles.get(id) as string, page }))
        .sort((a, b) => a.page - b.page);
    },

    at(page) {
      // The section a page belongs to is the last one that had started by then. A block always opens
      // a page of its own, so its first page answers with its own name rather than the one before.
      let found: string | undefined;
      for (const section of this.resolved()) {
        if (section.page > page) break;
        found = section.title;
      }
      return found;
    },
  };
}
