import type { GlossaryEntry } from "@/api/course";

/**
 * The glossary as the annotator sees it: which words to look for, and where they may not be marked.
 *
 * The default surface forms are derived HERE and nowhere else, so the running app and the golden
 * report — which reads `glossary.yaml` straight off disk — cannot disagree about what a term looks
 * like in prose. An entry's authored `match` list replaces the derived pair outright.
 */

export interface TermMatcher {
  id: string;
  /** Every surface form, longest first, so a variant never shadows a longer one. */
  variants: string[];
  /** Lessons this term points back at. An occurrence there SPENDS the term's slot and is not marked. */
  origins: Set<string>;
  /** Lessons where a match is a false friend, so it is not an occurrence of this term at all. */
  notHere: Set<string>;
}

/** One scan finds every term: alternatives ordered longest-first, so the longest match wins. */
export interface CompiledTerms {
  pattern: RegExp;
  /** Matched text, lowercased and whitespace-collapsed, to the term that owns it. */
  byVariant: Map<string, TermMatcher>;
}

/** A word character for boundary purposes: any letter or digit, in any script, plus `_`.
 *  Exported with `NOT_HYPHENATED` so the lesson-reference pattern is built from the SAME boundary
 *  rules as the term pattern — one detection dialect, two mark types. */
export const WORD = "\\p{L}\\p{N}_";

/** Neither end of a match may sit inside a hyphenated compound: `self-custody` is one word, and a
 *  link on its second half reads as a typesetting accident. `50-EMA` still matches — a digit is not
 *  the other half of a compound. */
export const NOT_HYPHENATED = { before: "(?<!\\p{L}-)", after: "(?!-\\p{L})" };

function escape(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** A parenthetical gloss is display sugar: `open interest (OI)` is written `open interest` in prose. */
function head(term: string): string {
  return term.split(" (")[0].trim();
}

/**
 * The naive plural, which is right for most of the list and overridden by `match` where it is not.
 *
 * EN adds `es` after a sibilant and `s` otherwise; ES adds `s` after a vowel and `es` after anything
 * else. Neither rule touches an acronym (`RSI`, `CVD`), which pluralises to itself in this course.
 */
export function derivedVariants(term: string, locale: string): string[] {
  const word = head(term);
  if (!word) return [];
  if (word === word.toUpperCase() && /\p{Lu}/u.test(word)) return [word];
  const plural =
    locale === "es"
      ? `${word}${/[aeiouáéíóú]$/i.test(word) ? "s" : "es"}`
      : `${word}${/(s|x|z|ch|sh)$/i.test(word) ? "es" : "s"}`;
  return plural === word ? [word] : [word, plural];
}

/** An alias links to an entry that points back at the canonical's lesson too — both are loops. */
function originsOf(entry: GlossaryEntry, byId: Map<string, GlossaryEntry>): string[] {
  const own = [entry.origin, ...(entry.senses ?? []).map((sense) => sense.origin)];
  const canonical = entry.aliasOf ? byId.get(entry.aliasOf.id) : undefined;
  const inherited = canonical
    ? [canonical.origin, ...(canonical.senses ?? []).map((sense) => sense.origin)]
    : [];
  return [...own, ...inherited].filter((origin): origin is string => Boolean(origin));
}

function buildMatcher(
  entry: GlossaryEntry,
  locale: string,
  byId: Map<string, GlossaryEntry>,
): TermMatcher | null {
  if (entry.link === false) return null;
  const variants = [...new Set((entry.match ?? derivedVariants(entry.term, locale)).map(head))]
    .filter(Boolean)
    // Longest first: `order block` must win against `order` when both are in the list.
    .sort((a, b) => b.length - a.length || a.localeCompare(b));
  if (variants.length === 0) return null;
  return {
    id: entry.id,
    variants,
    origins: new Set(originsOf(entry, byId)),
    notHere: new Set(entry.linkExcept ?? []),
  };
}

/** How a matched run of prose is looked up: case folded, and the hard wrap flattened back out. */
export function normalize(text: string): string {
  return text.replace(/\s+/g, " ").toLowerCase();
}

/**
 * All the terms as ONE pattern.
 *
 * Internal whitespace matches ANY run of it, because lesson prose is hard-wrapped at ~100 columns and
 * a multi-word term is routinely split across two lines (the never-coins guard has the same trap).
 * Where two entries claim the same word the first in id order keeps it, so the choice is stable.
 */
export function compileTerms(matchers: TermMatcher[]): CompiledTerms {
  const byVariant = new Map<string, TermMatcher>();
  const all: string[] = [];
  for (const matcher of matchers) {
    for (const variant of matcher.variants) {
      const folded = normalize(variant);
      if (byVariant.has(folded)) continue;
      byVariant.set(folded, matcher);
      all.push(variant);
    }
  }
  // Longest first across every term at once: JS alternation takes the first alternative that matches
  // at a position, so this ordering IS the leftmost-longest rule.
  all.sort((a, b) => b.length - a.length || a.localeCompare(b));
  const alternation = all.map((variant) => escape(variant).replace(/\s+/g, "\\s+")).join("|");
  return {
    byVariant,
    pattern: new RegExp(
      `(?<![${WORD}])${NOT_HYPHENATED.before}(?:${alternation})(?![${WORD}])${NOT_HYPHENATED.after}`,
      "giu",
    ),
  };
}

/** Every linkable term, in a stable order — the golden report reads it as the course's link vocabulary. */
export function buildTermIndex(entries: GlossaryEntry[], locale: string): TermMatcher[] {
  const byId = new Map(entries.map((entry) => [entry.id, entry]));
  return entries
    .map((entry) => buildMatcher(entry, locale, byId))
    .filter((matcher): matcher is TermMatcher => matcher !== null)
    .sort((a, b) => a.id.localeCompare(b.id));
}
