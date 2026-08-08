import type { GlossaryEntry } from "@/api/course";

/**
 * The ONE collation for the glossary, shared by the app page and the PDF.
 *
 * Both surfaces sort through `sortGlossary`, so the printed order and the on-screen order cannot
 * drift: the PDF never re-sorts on its own terms. `Intl.Collator` is the authority — it is the only
 * thing that gets Spanish right (`ñ` after `n`, accents folding onto their base letter) without the
 * app carrying a table of its own.
 *
 * The two LOCALES are expected to disagree with each other. ES sorts `apalancamiento` near the top
 * where EN sorts `leverage` mid-list, and roughly a third of the ES terms are English pass-throughs
 * (`funding`, `spot`, `spring`, `order block`) that interleave with the Spanish ones. That is
 * correct: an entry is looked up by the word the reader actually met.
 */

/** `base` sensitivity folds case and accents, so `emisión` sorts under E rather than after Z. */
export function glossaryCollator(locale: string): Intl.Collator {
  return new Intl.Collator(locale, { sensitivity: "base" });
}

export function sortGlossary(terms: GlossaryEntry[], locale: string): GlossaryEntry[] {
  const collator = glossaryCollator(locale);
  return [...terms].sort((a, b) => collator.compare(a.term, b.term));
}

/** An alias points at its canonical entry instead of repeating the definition. */
export function isAlias(entry: GlossaryEntry): boolean {
  return entry.aliasOf !== undefined;
}
