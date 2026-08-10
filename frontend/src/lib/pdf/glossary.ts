import type { Content } from "pdfmake/interfaces";
import type { GlossaryEntry } from "@/api/course";
import { sortGlossary } from "@/lib/glossary";
import { DEST, GLOSSARY_ENTRY_ID, printedId, withId } from "@/lib/pdf/pagination";
import { CROSS_REF } from "@/lib/pdf/page";

/**
 * The glossary as a printed section: alphabetical in the document's locale, one entry per block.
 *
 * The order comes from `sortGlossary` — the same function the app page uses — so the book and the
 * screen list the terms identically. This module deliberately does no sorting of its own.
 */

export interface GlossaryLabels {
  glossary: string;
  glossaryIntro: string;
  /** Renders an alias as a pointer: `CHoCH → cambio de carácter`. */
  alias: (canonical: string) => string;
  /** Names the lesson an entry (or one sense) was distilled from. */
  origin: (lesson: string) => string;
  /** Numbers a sense of a term the course uses in more than one way. */
  sense: (index: number) => string;
}

/**
 * `M19-L1 · The basis` — the pointer back, which is what makes the glossary a reference, and a
 * link to that lesson, because every other pointer in the book is one.
 */
function originContent(
  entry: { origin: string | null; originTitle: string | null },
  labels: GlossaryLabels,
  style: string,
): Content | null {
  if (!entry.origin) return null;
  const id = entry.origin.toUpperCase();
  return {
    text: labels.origin(entry.originTitle ? `${id} · ${entry.originTitle}` : id),
    style,
    linkToDestination: DEST.outline(entry.origin),
    ...CROSS_REF,
  };
}

function entryContent(entry: GlossaryEntry, index: number, labels: GlossaryLabels): Content {
  // The destination every marked term in the prose jumps to. It sits on the TERM's text node, not on
  // the stack around it: pdfmake only writes a destination where a line of text carries the id.
  const body: Content[] = [
    withId({ text: entry.term, style: "glossaryTerm" }, DEST.term(entry.id)),
  ];

  if (entry.aliasOf) {
    // A pointer, never a second copy of the definition — the canonical entry owns the words, and
    // the pointer is a link to them rather than an instruction to go and look.
    body.push({
      text: labels.alias(entry.aliasOf.term),
      style: "glossaryAlias",
      linkToDestination: DEST.term(entry.aliasOf.id),
      ...CROSS_REF,
    });
  } else if (entry.definition) {
    body.push({ text: entry.definition, style: "glossaryDefinition" });
  }

  for (const [i, sense] of (entry.senses ?? []).entries()) {
    body.push({
      text: [
        { text: labels.sense(i + 1), style: "glossarySenseNumber" },
        { text: sense.definition },
      ],
      style: "glossarySense",
    });
    const origin = originContent(sense, labels, "glossarySenseOrigin");
    if (origin) body.push(origin);
  }

  // A homonym's origins are per-sense and already printed above; only a single-sense entry
  // (or an alias, which points into the lesson that uses the second name) prints one here.
  if (!entry.senses?.length) {
    const origin = originContent(entry, labels, "glossaryOrigin");
    if (origin) body.push(origin);
  }

  return withId(
    { stack: body, margin: [0, 0, 0, 10] as [number, number, number, number] },
    printedId(GLOSSARY_ENTRY_ID, entry.id, index),
  );
}

export function glossarySection(
  terms: GlossaryEntry[],
  locale: string,
  labels: GlossaryLabels,
  /** Marks this heading as a top-level section, so the running footer can name it. */
  sectionId: string,
): Content | null {
  if (terms.length === 0) return null;
  const ordered = sortGlossary(terms, locale);
  return {
    stack: [
      withId(
        {
          text: labels.glossary,
          style: "blockTitle",
          headlineLevel: 1,
          tocItem: true,
          tocStyle: "tocBlock",
          // A top-level bookmark, beside the blocks. Its 161 entries stay out of the outline: a
          // bookmark pane listing every term is a second glossary, not a way around the book.
          outline: true,
        },
        sectionId,
      ),
      { text: labels.glossaryIntro, style: "moduleSummary" },
      ...ordered.map((entry, index) => entryContent(entry, index, labels)),
    ],
    pageBreak: "before",
  };
}
