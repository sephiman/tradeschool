/**
 * Matching pairing logic — a partial, injective map from a left id to a right id.
 *
 * Extracted from the `Matching` component so the interaction rules (assign,
 * reassign, unassign, steal, complete) are unit-testable independently of the
 * visual layout: the UI can be redesigned without touching these tests.
 */
export type Pairs = Record<string, string>;

/**
 * Assign `rightId` to `leftId`, keeping the map injective.
 *
 * - Reassigning a left replaces its previous right.
 * - If `rightId` was already held by a *different* left, it moves here (steal)
 *   rather than being held by two lefts at once — a right may pair with only
 *   one left. Returns a new map; the input is never mutated.
 */
export function assignPair(pairs: Pairs, leftId: string, rightId: string): Pairs {
  const next: Pairs = {};
  for (const [left, right] of Object.entries(pairs)) {
    // Drop the left we're reassigning and any left already holding this right.
    if (left !== leftId && right !== rightId) next[left] = right;
  }
  next[leftId] = rightId;
  return next;
}

/** Remove `leftId`'s assignment, if any. No-op for an unpaired left. */
export function unassignPair(pairs: Pairs, leftId: string): Pairs {
  const next = { ...pairs };
  delete next[leftId];
  return next;
}

/** The set of right ids currently consumed by some left. */
export function usedRights(pairs: Pairs): Set<string> {
  return new Set(Object.values(pairs));
}

/** True only when there is at least one left and every left is paired. */
export function isComplete(pairs: Pairs, leftIds: string[]): boolean {
  return leftIds.length > 0 && leftIds.every((id) => pairs[id] != null);
}
