/** Ordering logic — reorder a list by swapping an item with its neighbour. */

/** Swap `index` with its neighbour (-1 up, +1 down). Edges are a no-op. Never mutates. */
export function moveItem<T>(items: T[], index: number, dir: -1 | 1): T[] {
  const j = index + dir;
  const next = items.slice();
  if (j < 0 || j >= items.length) return next;
  [next[index], next[j]] = [next[j], next[index]];
  return next;
}
