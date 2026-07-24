/**
 * Ordering logic — reorder a list by swapping an item with its neighbour.
 *
 * Extracted from the `Ordering` component so the move rules are unit-testable
 * independently of the arrow-button layout.
 */

/**
 * Swap the item at `index` with its neighbour in direction `dir`
 * (-1 = up, +1 = down). Moves past either edge are a no-op. Returns a new
 * array; the input is never mutated.
 */
export function moveItem<T>(items: T[], index: number, dir: -1 | 1): T[] {
  const j = index + dir;
  const next = items.slice();
  if (j < 0 || j >= items.length) return next;
  [next[index], next[j]] = [next[j], next[index]];
  return next;
}
