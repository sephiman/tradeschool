<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Course content

The canonical source of the course. Structure lives in the manifest; prose and generator configs
live in parallel trees, all keyed by stable IDs.

```
course.yaml        the manifest: course → blocks → modules → lessons → exercises (order = list position)
en/lessons/*.md    lesson prose (English)      — one file per lesson id
es/lessons/*.md    lesson prose (Spanish)      — one file per lesson id
exercises/*.yaml   generator config per exercise id (server-generated + server-graded)
figures/*.yaml     lesson figure specs embedded via ::figure{id=…}
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
