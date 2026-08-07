/** Matching pairing logic — a partial, injective map from a left id to a right id. */
export type Pairs = Record<string, string>;

/** Assign `rightId` to `leftId`, keeping the map injective: a held right MOVES here. Never mutates. */
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
