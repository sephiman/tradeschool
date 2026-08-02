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
```

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

There is intentionally **no course catalog, switcher, or `/courses/{id}` routing yet** — the UI stays
single-course until a second course actually exists. This document plus the root `course` entity and
the `courses` table are the structural groundwork so that day is additive, not a migration of ids.

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
