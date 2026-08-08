<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Course content

The canonical source of the course. Structure lives in the manifest; prose and generator configs
live in parallel trees, all keyed by stable IDs.

```
course.yaml           the manifest: course → blocks → modules → lessons → exercises (order = list position)
en/lessons/*.md       lesson prose (English)      — one file per lesson id
es/lessons/*.md       lesson prose (Spanish)      — one file per lesson id
exercises/*.yaml      generator config per exercise id (server-generated + server-graded)
figures/*.yaml        lesson figure specs embedded via ::figure{id=…}
figure-coupling.yaml  which lesson numbers are approximations of which figure's generated values
glossary.yaml         the bilingual term list: one or two sentences per term, plus its origin lesson
```

## The glossary

`glossary.yaml` **refers, it does not teach.** Every entry distils the lesson that teaches the term
into one or two sentences and points back at it; anything longer belongs in the lesson. Glossary ids
join the same permanent, globally-unique namespace as everything above (`g-funding`, `g-premium`), and
the loader rejects a collision.

Three shapes: a plain `definition`; `senses` for a term the course genuinely uses in more than one
sense (`premium` has three), optionally under a lead `definition` for the "one mechanic, several
instruments" case (`absorption`); and `alias_of` for a second name the course uses for something it
already defines (`CHoCH` → `change of character`, `order block` → `origin zone`), which defers the
definition rather than repeating it.

The hard rule is that **the glossary never coins**: startup fails if a term does not appear in the
prose of its own locale. So a term is added to the glossary only after the prose uses it — and where
the two locales disagreed on a term, the prose was unified first (see the canonical forms in
`GLOSSARY-PROPOSAL.md` at the repo root).

The manifest's root is a single **course** (`course: { id, title, description }`); its blocks follow at
the top level. There is one course today — `crypto-futures` — and the structure is ready for more.

## ID convention (read before adding content)

**Content IDs are globally unique across the entire repository** — not per-course. The manifest
validator rejects any duplicate id at any level (course, block, module, lesson, exercise), and figure
ids share the same namespace. Reconciliation and all progress/attempts data key on these ids, so they
are permanent.

Rules:

- **Existing un-prefixed ids belong to `crypto-futures` forever.** `m01`, `m06-l1`, `m12-ex-2`,
  `fig-m09-accumulation`, `block-a` — never rename or reuse them. Renaming an id orphans a learner's
  progress.
- **Any future course must namespace all of its ids** with a short course prefix, e.g. a spot-trading
  course uses `spot-m01`, `spot-m01-l1`, `spot-m01-ex-3`, `fig-spot-m01-…`, `spot-block-a`. This keeps
  the global namespace collision-free without ever touching the crypto-futures ids.
- The course id itself is also globally unique (`crypto-futures`, `spot`, …) and is likewise permanent.
- **Ids are never renumbered, and display order is list position — not the id.** So new content either
  **appends to its block** or arrives as a **new trailing block**; it is never inserted mid-sequence,
  because that would leave the id badge on the course page reading `M14 → M30 → M15`. The id is a
  permanent label, the position is the order, and the two are allowed to disagree only where nothing
  renders them side by side (`m17-ex-4` sits out of numeric sequence inside its lesson, with the reason
  on file in the manifest). `block-g` (one module, `m30`) is the first block added under this rule.

### Ids are globally unique — confirmed, and permanent

The rule above is the decision, restated because course-scoped URLs are an obvious moment to reopen
it: **content ids are unique across the whole repository, not per course.** A second course
self-namespaces (`spot-m01`, `g-spot-funding`) rather than relying on its directory to disambiguate.

The reason it cannot change now: `attempts.exercise_id` and `lesson_completions.lesson_id` store the
bare id. Per-course uniqueness would mean adding a course column to every id reference and migrating
existing learner progress — for no gain, since the namespace has room for every course we will write.

The one place a course id IS stored alongside is `exam_sessions.course_id`, which exists so a
course-scoped by-id route can answer "does this exam belong to this course?" as a field comparison
rather than by joining through the exam's attempts.

### What a second course would touch

The API is already course-scoped (`/api/courses/{course}/…`, see the root README), so URLs are not in
the way. What is still single-course:

- **This directory.** Today `course.yaml`, `glossary.yaml` and `es/`/`en/` sit at the top; a second
  course means `content/courses/{slug}/…` with today's tree moving under `crypto-futures/`.
- **`load_registry(dir) -> CourseRegistry`** becomes `load_registries(dir) -> dict[slug, CourseRegistry]`.
- **Three spots in app state**: `app.state.registry` (→ keyed by slug), the print cache keyed by
  locale (→ by course + locale), and `reconcile(app.state.registry.manifest, …)` (→ per course).
- **`current_course`** stops resolving an absent slug to "the only course", which is the moment the
  deprecated unscoped aliases must be removed rather than merely discouraged.

Both the API and the SPA are already course-scoped (`/api/courses/{course}/…` and
`/courses/{course}/…`), so a bookmarked lesson survives the arrival of a second course. What is
deliberately **not** built yet is a course catalog or switcher, and the SPA declares its routes with
the literal slug rather than a `:course` param — the UI stays single-course until a second course
actually exists. This document plus the root `course` entity and the `courses` table are
the structural groundwork so that day is additive, not a migration of ids.

## Worked numbers next to a figure

Where a lesson teaches with worked numbers beside a generated figure, **the figure is the source of
truth.** Figures keep their frozen seeds and exact generated prices; the prose quotes rounded,
human-readable approximations of those values ("cerca de 25.900" for a shelf drawn at 25911.85),
introduced as approximations (*cerca de*, *en torno a*, `~`). Any arithmetic the prose performs on
them — widths, distances, ratios — is recomputed from the adapted numbers, and `es/` and `en/` always
adapt together in the same change.

Two escape hatches, both deliberate:

- **Exception figures.** Where the prose's own numbers *are* the teaching — a ratio, a sizing chain
  chosen to divide cleanly, a separation the figure exaggerates on purpose — the prose keeps them and
  gains a lead-in **before** the figure telling the reader it is a generated instance carrying its own
  prices.
- **Panels that share a seed.** When a two-panel figure exists to say "identical chart, one
  difference" (m08's breakout vs fakeout, m14's volume read, m17's OI read), both panels run the *same*
  seed, so the comparison is literally true rather than merely suggestive. The duplicate-level-price
  test exempts panels within one figure precisely for this.

`figure-coupling.yaml` declares every coupled number and every exception, and
`backend/tests/test_figure_prose_coupling.py` enforces both directions of the deal: a figure that
moves fails the test with the list of lessons needing a prose pass, and prose edited away from its
figure fails it too. **Reseeding a coupled figure, or changing an injector that feeds one, means
re-running the worked-number pass for the lessons the manifest names** — the test will not let that
step be skipped.
