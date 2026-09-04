<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Bundle format changelog

`bundleFormatVersion` in `dist/bundle/manifest.json`. It moves when the bundle's **shape** changes in
a way a shipped app would misread; content changes move `contentFingerprint` instead. An app pins the
format it can parse and the fingerprint it last saw, so a bump is always a coordinated release.

Producer: `backend/scripts/export_bundle.py` (and its TypeScript half,
`frontend/scripts/export-ast.mjs`).

---

## v2 — 2026-09-04

Three changes. One is breaking, and it is the reason this is a version bump rather than an additive
release.

### 1. `params` on a calculation config is now an ordered list — **BREAKING**

**Was** (v1), in `exercises/configs.json`:

```json
"params": { "avg_loss": {…}, "avg_win": {…}, "win_rate": {…} }
```

**Is** (v2):

```json
"params": [
  { "name": "win_rate", "kind": "choice", "values": ["0.45", "0.55"] },
  { "name": "avg_win",  "kind": "int_range", "min": 120, "max": 200, "step": 40 },
  { "name": "avg_loss", "kind": "int_range", "min": 320, "max": 400, "step": 40 }
]
```

**Why.** `calculation._sample_params` draws one value per parameter from ONE seeded rng, walking them
in declaration order — so **the order is the question asked**. The bundle's serializer sorts every key
it writes (that is what makes the fingerprint reproducible), which silently rewrote the order for the
**9 of 18** calculation exercises whose YAML order is not alphabetical. A port reading the sorted map
sampled a different exercise from the same seed: `m23-ex-5` changed four of its seven parameters that
way, `style` among them, so the learner was shown a different scenario entirely.

A list survives key sorting. It is also why this is deliberately breaking rather than an added
`paramOrder` field beside the map: a port that ignores an added field keeps the bug silently, while a
port that meets a list where it expected a map fails to parse and gets fixed.

Affected exercises (YAML order ≠ alphabetical): `m05-ex-1`, `m05-ex-2`, `m07-ex-1`, `m07-ex-2`,
`m20-ex-1`, `m20-ex-2`, `m23-ex-5`, `m25-ex-1`, `m25-ex-2`.

### 2. Per-lesson `summary` in `manifest.json` — additive

Every lesson under `blocks[].modules[].lessons[]` now carries:

```json
"summary": { "en": "…", "es": "…" }
```

Two or three sentences of what the lesson teaches, authored as final content in each locale against
that locale's own prose — not a translation of the other. Bound by the same **never-coins** rule as
the glossary: a summary may not use a glossary term its own lesson's prose never uses, enforced at
content load (`registry._check_summaries_never_coin`) and asserted in
`tests/test_content_manifest.py`.

The app asked for this: `ExerciseReferences.kt` prints the *module's* summary under a tapped lesson's
title, labelled as the module's because a lesson had none of its own.

### 3. `exercises/references.json` — new file, additive

The module and lesson references inside exercise prose, resolved at export time:

```json
{
  "kind": "exercise-references",
  "detector": "lib/glossary/annotate.ts REF_PATTERN over lib/refs/registry.ts",
  "references": {
    "m11-ex-4": {
      "en": { "variants[5].explanation": [
        { "start": 65, "end": 68, "mention": "m10", "refKind": "module", "refId": "m10" }
      ] }
    }
  }
}
```

242 marks across 29 exercises. `start`/`end` are character offsets into the **exact string** at that
path in `exercises/configs.json`, verified on both sides of the export: the TypeScript half reads them
back against its input, and `export_bundle._check_exercise_refs` reads them back against the file that
shipped.

**Why.** A lesson's references already arrived pre-marked; an exercise's did not, so the app carried a
second detector of its own (`ExerciseReferences.kt`'s `ReferenceTokens`). Two detectors are two
opinions about which words a reader may tap.

### Behaviour note: the reference detector is now lowercase-only

`REF_PATTERN` dropped its `i` flag. `M15` in trading prose is a fifteen-minute timeframe — an idiom
this course teaches in m23-l2 — not module 15, so a case-insensitive `m\d{2}` would link a chart
timeframe to a module inside the sentence explaining timeframes. Nothing in the course is written that
way today, so this moved no golden and no mark: `content/lesson-refs.{en,es}.txt` are byte-identical
and the 242 exercise marks are unchanged. The Android port reached the same rule independently, which
is what surfaced it.

---

## v1 — initial

The bundle as first exported: `manifest.json`, `ast/` (per-locale annotated mdast per lesson),
`glossary/`, `exercises/configs.json`, `figures/specs.json`, `reading-seconds.json`,
`error-phrases.json`, `figure-coupling.yaml`.
