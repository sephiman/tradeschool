<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Cleanup lote — handoff

Everything from the four-block cleanup lote, the two follow-ups that arrived after it, and the m15
recapture that closed the one debt the lote opened. **Nothing is committed.** The file list is at the
end.

Companion documents, all written by this pass:

* `verification-blind-spots.md` — the three lessons the Android port surfaced, and what was added.
* `bundle-format-changelog.md` — what moved in bundle v1 → v2 and why.
* `bundle-v2-app-spec.md` — the checklist the Android side works from.

---

## Block A — verification blind spots

**The multiset text diff was blind twice.** It splits on `/\s+/`, so whitespace cannot appear in its
answer, and it is a bag, so order is not in it either. Worse, its reference was the web's own mdast of
the same markdown off the *same parser* as the bundle's, so a parser change moved both sides together.

Added `bundleBlocks` / `renderedBlocks` / `blockDiff` in `frontend/src/lib/bundle/verify.ts`: per
lesson, block for block, in order, whitespace kept as information (runs collapse — HTML collapses them
too — but a hard break survives as a newline). The reference is the HTML `LessonMarkdown` actually
paints, via `rendered.tsx`, which shares no code with the bundle's serialization.

*Red-first:* swapping two paragraphs in a written bundle changes no text node, so the multiset reports
`0 differing` while the block check names the lesson, the block index and both texts, and
`export_bundle.py --verify-only` exits 2.

**The exporter had no quantization vaccine.** Every chart series is rounded where it is built, which
makes it a convention across a dozen injectors rather than a rule — and `levels`, `bands` and
`diagonals` are copied out of an injector verbatim, so a forgotten `round(..., 2)` reached a digest.
`PAYLOAD_SCALES` in `export_generation_goldens.py` now declares the scale of all 24 float paths; a
value off its scale, or a float at an undeclared path, stops the export before anything is written.

*Red-first:* wrapping an injector so one level price loses its rounding exits 2 with nothing written.

It found a live one on its first green run — see the m15 recapture below.

**Docs:** `verification-blind-spots.md`, three lessons — a whitespace-tokenized diff cannot see
whitespace bugs; an oracle derived from the code under test agrees with its bugs; a convention no one
enforces is not a rule.

## Block B — bundle v2

**`params` order was a live, silent bug.** `calculation._sample_params` draws one value per parameter
from ONE seeded rng in declaration order, so the order *is* the question asked. The bundle's serializer
sorts every key it writes, and **9 of the 18** calculation YAMLs declare a non-alphabetical order — so
the app has been generating a different scenario from the same seed. `m23-ex-5` differs in four of its
seven parameters at seed 0, `style` among them. Nothing on either side would have caught it: the app
pins hand-built fixtures and sweeps the distractor pipeline, and there is no cross-language golden over
*sampled scenarios*.

`params` now leaves as an ordered list of `{name, …}`. Deliberately breaking rather than an added
`paramOrder` field: a port that ignores an added field keeps the bug silently, one that meets a list
where it expected a map fails to parse and gets fixed.

**44 lesson summaries, both locales**, authored as final content against each locale's own prose rather
than translated. Bound by a **never-coins** rule one level down from the glossary's: a summary may not
use a glossary term its own lesson's prose never uses, enforced at content load
(`registry._check_summaries_never_coin`) and asserted over the real course. Two real violations were
caught while writing and fixed. Exported in the bundle manifest, the `/export` document and the course
tree (the popover needs it in the same frame the reader hovers).

**`exercises/references.json`** — 242 module/lesson references in exercise prose, resolved at export
time by the same annotator that marks a lesson's, as offsets into the exact string the bundle ships.
Both halves of the export read those offsets back before writing.

**`REF_PATTERN` is now lowercase-only.** `M15` in trading prose is a fifteen-minute timeframe — an
idiom this course teaches in m23-l2 — not module 15. No content is written that way, so the frozen
reports are byte-identical and the 242 marks unchanged. The Android port reached the same rule
independently, which is what surfaced it.

`bundleFormatVersion` is **2**. Bundle fingerprint `275886702c4ed051…`.

## Block C — wording and exam parity

* **`exerciseType.quiz` in ES:** `Test` → `Cuestionario`. The app's A7 device pass read "Test" as an
  untranslated English word in a Spanish UI, and the reader's reading is the one that counts.
* **The EN calculation diagnosis printed the mistake twice.** The cause is grammar, not sloppiness:
  every EN phrase is a bare verb phrase, so "result of forget the maintenance-margin term" is broken
  English and the trailing "(what you get if you …)" was the repair. Both locales' sentences are now
  named in `MISTAKE_SENTENCES` and exported in `error-phrases.json`, and they are different shapes on
  purpose — ES phrases are infinitives, which "resultado de" takes and "si" does not. The app's EN
  wording is already the right shape; **its ES is not** ("eso es lo que sale si olvidar…" is
  ungrammatical) and should follow the exported sentence.
* **Exam question order is frozen at assembly** in the `rules` JSONB the session already has, so no
  migration. It was re-derived from today's manifest at every render, which meant a display
  renumbering — which this repo supports on purpose — reordered an exam already sitting in review, and
  the `index` the UI paginates by moved under it. `_attempts_of` also gained an `ORDER BY`, because
  the tie-break was the database's row order.
* **`GET /exams/current` → `GET /exams/open`.** Starting an exam closes an open one of the *same*
  scope and block only, so a global and a block exam can be open at once — and `/current` answered
  with the newest alone, leaving the other unreachable: it could be neither resumed nor abandoned.
  Listing beats closing orphans, which silently destroys work the learner never asked to discard.

## Block D — retirements

* **`Exercise.content_hash`** retired from the ORM model with a note. Declared, never written, never
  read: every row in every database has held NULL since the table was created, and the drift it was
  going to catch is caught by the frozen configs and the bundle fingerprint instead. The physical
  column is **left in place** — dropping it is a one-line migration and this pass was scoped to
  additive ones. `RETIRED_EXERCISE_COLUMNS` keeps it off the model.
* **`charts/numerics.py` docstrings** trimmed to the house rule. The summation-order contract and the
  closed-form formula stay in the docstring — that is the rule's own exception, and ruff's RUF003
  independently refuses the minus sign in a comment. Provenance and the degenerate-input behaviour
  moved to `#` comments at the exact lines. Comments only: zero golden movement.

---

## Reference popovers

The `M14 · Volumen y confirmación` tooltip is now a card: kind, `M19 · title`, the target's own
summary — the module's for a module, the **lesson's** for a lesson with its module named above it —
and a "Go to module/lesson" action. One component (`features/references/ReferenceLink.tsx`) for both
mark kinds and for exercise prose.

The mention stays a real `<a href>`, so ⌘-click, middle-click, "copy link address" and the status bar
all survive, and a modified click falls straight through to the browser. A **plain** activation opens
the card instead of navigating: the same mention appears inside an exam question, where an accidental
tap that yanks the learner off the question costs them the answer. The Android app made the same call
for the same reason.

Keyboard: focus moves into the action when the card opens, Escape closes it and hands focus back
without re-opening it as a hover tooltip. A pinned panel is now `role="dialog"` rather than a
`tooltip` containing focusable children — which also fixed a latent bug in the glossary card, whose
links have always been inside that `role="tooltip"`.

`Prose` marks references through a context, so `lib/` never imports from `features/` and the six prose
call sites needed no prop of their own. Exam pages get it via `ProseReferenceHost`.

## Exam start conflict

Starting an exam that would abandon an open one of the same scope **and block** asks first, naming the
sitting and how far into it the reader is. Primary is *Continue the open exam*; *Start a new one* is
the quiet destructive one — a red fill there would read as the recommendation. A different scope or
block asks nothing, because a confirmation that fires when nothing is at stake is one readers learn to
dismiss unread. `ConfirmDialog` separates dismiss (Escape, backdrop) from the safe answer, because
here the safe answer navigates and dismissing must never move the reader.

Server parity is pinned by `test_a_different_block_of_the_same_scope_abandons_nothing`: the dialog's
predicate and the server's abandon rule are the same rule, asserted on both sides.

## m15 recapture — the one debt this pass opened, and closed

`diagonals.extended()` re-anchors a drawn line to a figure's right edge and took the new `end_price`
from `price_at`, an **interpolation**. Every injector rounds the anchors it draws to 2dp; this one did
not, so nine raw doubles reached four figure digests. Only the figure path calls `extended`, which is
why `exercise-mode.tsv` never carried it.

`extended()` now rounds to `ANCHOR_SCALE`. Recaptured, with the note naming the four figures and the
cause in `figures.tsv`'s own header, as that file's contract asks:

| moved | unchanged |
| --- | --- |
| `frozen:fig-m15-channel`, `frozen:fig-m15-trendline`, `frozen:fig-m15-triangle`, `frozen:fig-m15-wedge` | every other line of `figures.tsv` |
| | `exercise-mode.tsv` — byte-identical, 3915 documents |
| | the 90 committed fingerprints — `verify_golden_stability.py` exit 0 |
| | `test_figure_prose_coupling.py` — no lesson quotes a value that moved |

`KNOWN_UNQUANTIZED` is now **empty**: the vaccine holds with no exceptions. The mechanism stays,
tested with a synthetic pin, because it is what makes a pin temporary — a key that stops firing fails
the export with `retire the note`, so paying a debt forces the note to be retired in the same change.

**The whole-workload digest moved, and that is expected:** it hashes figure documents too, four of
which changed. `6999679392b682a2…` is the new one to compare a second machine against.

---

## Two things for whoever picks this up

**Prettier is not this project's tooling.** No config, not in `package.json`. Running
`prettier --write` on a file reformats it wholesale — it turned a 40-line edit into a 161-line diff
before I noticed and reverted. Do not reach for it.

**`contracts/generation-goldens/` in the Android repo is now stale** by those four `figures.tsv` lines.
Re-copying it is `export_contracts_to_android.py`, and it is deliberately **not** done here.

---

## Android round 2, item 1 — a spec, not work done here

The exam start-conflict dialog for the app. The **behaviour** already matches: `Exams.start` abandons
the open sitting of the same scope and block and only that one, and `ExamStateMachineTest`'s
`starting an exam of the same scope and block abandons the open one, and only that one` asserts both
branches. What is missing is the confirmation UI — and it needs a storage change first, which is the
part worth agreeing before anyone writes it.

**The problem.** The dialog line is `Examen global · 3 de 34 respondidas`. `OpenExam`
(`exams/ExamModel.kt`) carries `id, scope, blockId, blockTitle, startedAt` — no counts. `ExamStore`'s
`openSessions()` returns `RecordedExamSession`, which has none either.

**The cheapest honest route** reuses the aggregate that already exists rather than adding a parallel
one. `ExamSessionDao.tallies()` groups `exercise_attempt` by `examSessionId` for *all* sessions and
yields `ExamTally(sessionId, total, correct)`. `correct` is null until a sitting is graded, so it is
useless for an open one — but **answered** is one more `SUM` in the same query:

```sql
SUM(CASE WHEN answerJson IS NOT NULL THEN 1 ELSE 0 END) AS answered
```

Then:

1. `ExamTally` gains `answered: Int`; the `@Query` gains that column. No schema change — it is an
   aggregate over an existing table, so no Room migration.
2. `openSessions()` combines with `tallies()` exactly as `submittedHistory()` already does, yielding
   a new `OpenExamEntry(session, answered, total)` — the mirror of the existing `ExamHistoryEntry`.
3. `OpenExam` gains `answered` and `total`; `Exams.openSittings` maps them through.
4. `InMemoryExams` (the test double) implements the same.

**Then the UI.** `ExamsScreen.begin(scope, blockId)` becomes a request that first looks for
`open.firstOrNull { it.scope == scope && it.blockId == blockId }` — note **both**, matching the store's
own rule — and shows the dialog when it finds one. `ExamChrome.ConfirmDialog` exists but takes only
`strings.confirm` / `strings.cancel`; it needs explicit action labels, because the two answers here are
named verbs rather than OK and Cancel. A5 §9's convention (`window.confirm` becomes an `AlertDialog`,
plurals written out) applies.

**Strings** (`ExamStrings`, EN + ES) — the web's, already written, so the two platforms say the same
thing:

| key | en | es |
| --- | --- | --- |
| `conflictTitle` | An exam is already open | Ya tienes un examen abierto |
| `conflictBody` | Starting a new one abandons it. It will not be graded or saved. | Empezar uno nuevo lo abandona. No se calificará ni se guardará. |
| `conflictAnswered` | {done} of {total} answered | {done} de {total} respondidas |
| `conflictResume` | Continue the open exam | Continuar el examen abierto |
| `conflictStartNew` | Start a new one | Empezar uno nuevo |

**Hierarchy, and it is the point of the dialog:** the safe answer (*continue*) is the primary and
holds focus; *start a new one* is the quiet destructive one. A dialog whose destructive answer is the
prominent one trains people to press the prominent one.

**Both branches must be asserted** — same scope+block shows the dialog and starts nothing until it is
chosen; a different scope, or a different block of the same scope, shows nothing and starts
immediately. The web's `ExamPage.test.tsx` is the shape to copy.
