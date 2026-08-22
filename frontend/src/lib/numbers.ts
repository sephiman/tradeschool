/**
 * Reading back a number the server formatted for a locale.
 *
 * The course has exactly one number FORMATTER, and it lives on the backend
 * (`tradeschool/content/numbers.py`): prompts, option labels and worked solutions arrive already
 * printed for the reader's locale, and the app and the PDF render those strings untouched. This is
 * the inverse, and the only reason it exists: the inline calculator hands back a raw JS number and
 * has to find which option it matches. Nothing here may print a number — that would be a second
 * formatter, and the two would drift.
 */

/** Separators the backend formatter uses. EN is the fallback, matching `LocalizedText.get`. */
function separators(locale: string): { group: string; decimal: string } {
  return locale.startsWith("es") ? { group: ".", decimal: "," } : { group: ",", decimal: "." };
}

/** A server-formatted label back to a number, or `NaN` if it is not one. */
export function parseLocalizedNumber(text: string, locale: string): number {
  const { group, decimal } = separators(locale);
  const cleaned = text.trim().split(group).join("").replace(decimal, ".");
  if (cleaned === "" || !/^[+-]?\d*\.?\d+$/.test(cleaned)) return NaN;
  return Number(cleaned);
}

/**
 * Which option a calculator result lands on, or null if none is close enough.
 *
 * Closest-match rather than first-match: option values can sit as little as four display quanta
 * apart (the friendly-numbers guard's floor), and on a four-decimal exercise that is under the
 * tolerance — so "the first one within tolerance" could pick the neighbour of the real answer.
 */
export function matchOptionValue<T extends { id: string; value?: string | number }>(
  options: readonly T[],
  result: number,
  locale: string,
  tolerance = 0.001,
): T | null {
  let best: T | null = null;
  let bestGap = Infinity;
  for (const option of options) {
    const value = parseLocalizedNumber(String(option.value ?? ""), locale);
    if (Number.isNaN(value)) continue;
    const gap = Math.abs(value - result);
    if (gap < bestGap) {
      best = option;
      bestGap = gap;
    }
  }
  return bestGap <= tolerance ? best : null;
}
