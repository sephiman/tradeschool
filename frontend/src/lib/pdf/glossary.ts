import type { Content } from "pdfmake/interfaces";
import type { GlossaryEntry } from "@/api/course";
import { sortGlossary } from "@/lib/glossary";
import { GLOSSARY_ENTRY_ID, printedId, withId } from "@/lib/pdf/pagination";

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

/** `M17-L1 · The basis` — the pointer back, which is what makes the glossary a reference. */
function originLabel(entry: { origin: string | null; originTitle: string | null }): string | null {
  if (!entry.origin) return null;
  const id = entry.origin.toUpperCase();
  return entry.originTitle ? `${id} · ${entry.originTitle}` : id;
}

function entryContent(entry: GlossaryEntry, index: number, labels: GlossaryLabels): Content {
  const body: Content[] = [{ text: entry.term, style: "glossaryTerm" }];

  if (entry.aliasOf) {
    // A pointer, never a second copy of the definition — the canonical entry owns the words.
    body.push({ text: labels.alias(entry.aliasOf.term), style: "glossaryAlias" });
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
    const origin = originLabel(sense);
    if (origin) body.push({ text: labels.origin(origin), style: "glossarySenseOrigin" });
  }

  // A homonym's origins are per-sense and already printed above; only a single-sense entry
  // (or an alias, which points into the lesson that uses the second name) prints one here.
  if (!entry.senses?.length) {
    const origin = originLabel(entry);
    if (origin) body.push({ text: labels.origin(origin), style: "glossaryOrigin" });
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
        },
        sectionId,
      ),
      { text: labels.glossaryIntro, style: "moduleSummary" },
      ...ordered.map((entry, index) => entryContent(entry, index, labels)),
    ],
    pageBreak: "before",
  };
}
