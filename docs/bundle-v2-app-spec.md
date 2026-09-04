<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Consuming bundle v2 — what the Android app has to change

Companion to `bundle-format-changelog.md`, written so the port can be scheduled. Every file path
below is in `tradeschool-android`. Nothing here needs the web repo again; the bundle is the contract.

**Do not ship this piecemeal.** The app gates on `bundleFormatVersion`, so it reads a v1 bundle or a
v2 bundle and never both. All four items land in one release.

---

## 0. The gate

`content/src/main/kotlin/…/content/BundleFormat.kt`

```kotlin
const val SUPPORTED_BUNDLE_FORMAT_VERSION: Int = 1   // → 2
```

`ContentBundle.kt:216` already refuses a bundle whose version is not the supported one, and
`BundleOpensTest.kt` already asserts that refusal by rewriting the version in a fixture — that test
keeps working, it just swaps which number is the accepted one.

---

## 1. `params` becomes an ordered list — **the breaking one, and it fixes a live bug**

`content/src/main/kotlin/…/content/ExerciseConfigs.kt:99`

```kotlin
val params: Map<String, CalculationParam>      // v1
```

becomes a list that carries its own name:

```kotlin
@Serializable
data class CalculationParam(val name: String, /* …existing kind/min/max/step/values… */)

val params: List<CalculationParam>             // v2
```

`exercises/src/main/kotlin/…/exercises/CalculationExercises.kt:41`

```kotlin
return spec.params.entries.associate { (name, param) -> name to sampleOne(param, rng) }   // v1
return spec.params.associate { param -> param.name to sampleOne(param, rng) }             // v2
```

Everything downstream keys params by name (`displayParams`, `percentArgs`) and is unaffected.

**Why this is urgent rather than cosmetic.** `sampleOne` is called once per parameter off ONE seeded
rng, so the iteration order decides which parameter receives which draw. kotlinx.serialization decodes
a JSON object into a `LinkedHashMap`, i.e. **the order the bundle wrote** — and the v1 bundle wrote
them sorted, because the bundle's serializer sorts every key. For the nine exercises whose YAML order
is not alphabetical, the app has been generating a **different scenario from the same seed** than the
web does. `m23-ex-5` differs in four of its seven parameters at seed 0, `style` among them.

**Nothing on either side would have caught this.** The app's `CalculationExerciseTest` pins
hand-constructed `CalculationSpec` fixtures and sweeps the distractor pipeline for behaviour; there is
no cross-language golden over *sampled scenarios*. Worth adding one with this change: for a handful of
seeds on each of the nine, assert the sampled parameter map equals the web's. The web side is now
guarded by `test_export_bundle.py::test_a_calculation_s_params_reach_the_bundle_in_the_order_the_yaml_declares`.

Affected: `m05-ex-1`, `m05-ex-2`, `m07-ex-1`, `m07-ex-2`, `m20-ex-1`, `m20-ex-2`, `m23-ex-5`,
`m25-ex-1`, `m25-ex-2`.

---

## 2. Per-lesson `summary` — the field the app asked for

`manifest.json`, every lesson: `"summary": { "en": "…", "es": "…" }`.

`content/src/main/kotlin/…/content/Manifest.kt` — add `val summary: LocalizedText` to the lesson
model (non-null; the export refuses to write a bundle without one).

`exercises/src/main/kotlin/…/exercises/ui/ExerciseReferences.kt:130-157`, `ReferenceSheetBody`, is
where it pays off. The comment there records the workaround:

> The summary is the MODULE's, from the manifest, and it is labelled as such on a lesson's sheet — a
> lesson carries no summary of its own in the bundle (recorded as a web cleanup-lote item) …

So: for `RefKind.LESSON`, show the **lesson's** summary and drop the "this is the module's" label;
keep the module's summary for `RefKind.MODULE`. `RefTarget` needs the lesson summary plumbed through
from `content/…/Refs.kt`.

Two or three sentences, authored in each locale against that locale's own prose, and bound by a
never-coins rule — no summary uses a glossary term its own lesson's prose does not.

---

## 3. `exercises/references.json` — delete the app's second detector

New file. Shape:

```json
{ "kind": "exercise-references",
  "detector": "…",
  "references": { "<exerciseId>": { "<locale>": { "<path>": [
      { "start": 65, "end": 68, "mention": "m10", "refKind": "module", "refId": "m10" } ] } } } }
```

`start`/`end` are character offsets into the **exact string** at `<path>` in
`exercises/configs.json` — `variants[5].explanation`, `variants[0].options[2].text`, and so on,
addressing the exported config directly. The export verifies every offset against the shipped string
before it writes the bundle, twice, on both sides of the language boundary.

What changes in the app:

- **`ui/ExerciseReferences.kt`** — delete `object ReferenceTokens` entirely. That regex is the second
  opinion; the marks now arrive resolved.
- **`ui/InlineMarkdown.kt:85`** — `prose(run, references)` currently calls
  `ReferenceTokens.findAll(run)` on a *substring* of the source. It needs the marks for the string
  being rendered plus the **base offset** of `run` within it, so a mark can be matched to its
  position. `InlineMarkdown` already walks the raw text with an `at` index while stripping `**`/`*`;
  thread that index into `prose` and compare against `mark.start`.
- **`ExerciseReferenceCensusTest.kt`** — its census (`found > 200`) becomes an assertion that the
  bundle's marks are the ones rendered, rather than that a local regex finds them. Its resolution
  half stays: every `refId` must resolve through `RefRegistry`.

Expect **242 marks across 29 exercises**. The app's own detector finds the same set today, so nothing
a reader can tap should change — this removes the duplication, not a feature.

### One behavioural difference to know about

The web detector was case-insensitive and is now lowercase-only, matching the rule the app already
had (`M15` is a fifteen-minute timeframe, not module 15). The app's regex additionally rejects any
preceding `-`, where the web's rejects only a *letter*-hyphen — so `50-m09` would be a mark on the web
and not in the app. No content triggers it, and after this change the app has no detector at all, so
the difference disappears rather than needing a fix.

---

## Checklist

1. `SUPPORTED_BUNDLE_FORMAT_VERSION = 2`.
2. `CalculationSpec.params` → `List<CalculationParam>` with `name`; fix the sampling call; add a
   cross-language golden over sampled scenarios for the nine affected exercises.
3. Lesson `summary` in the manifest model; use it in `ReferenceSheetBody` for a lesson reference.
4. Read `exercises/references.json`; delete `ReferenceTokens`; thread a base offset through
   `InlineMarkdown`; repoint the census test.
5. Re-run the app's contract suite. The generation goldens and PRNG vectors are **unchanged** by v2 —
   verified byte-identical against the committed copy in `contracts/` — so nothing in `:generation`
   should move.
