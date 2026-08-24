<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# TradeSchool — backend

Python / FastAPI backend for TradeSchool, the Sephilabs interactive crypto-futures trading academy.
It is the Python reference app of the ecosystem: clear domain separation, seed-deterministic exercise
generators behind a common abstraction, server-side generation and grading.

## Layout

```
src/tradeschool/
  main.py       app factory + lifespan (migrate + manifest sync)
  config.py     pydantic-settings
  db.py         async SQLAlchemy engine/session
  auth/         fastapi-users (cookie + database strategy, Argon2), rate limiting
  content/      manifest + content registry loader, validation, reconciliation, CLI sync,
                print_export.py (the printed book's frozen exercise instances + their answer key —
                the one place a solution leaves the server before a learner has answered)
  exercises/    ExerciseGenerator ABC + registry + generators + Decimal formulas + chart engine + lesson figures
                + reveal.py (read an instance's ground truth, verified by re-grading it)
  attempts/     seeded attempts, server-side grading, abandoned rule
  progress/     lesson completion
  stats/        per-user + anonymous global statistics
  exams/        sampled global/per-block exams over the exercise bank (deferred grading, own lane)
  dev/          dev-only bulk chart generation for the credibility gallery
scripts/        numeric-determinism measurement tooling (not part of the app) — see below
```

## Development

```bash
uv sync                       # install deps (incl. dev group)
uv run pytest                 # integration tests against real Postgres (testcontainers)
uv run ruff check .           # lint
uv run mypy src               # types
uv run tradeschool sync       # reconcile the course manifest into the DB
uv run tradeschool reset-password <username>   # admin password reset (prompts for the new one)
uv run uvicorn tradeschool.main:app --reload   # dev server (needs a reachable Postgres)
```

See the repo root `.env.example` for configuration.

## scripts/ — numeric-determinism tooling

Standalone measurement scripts, not part of the app and not imported by it. They exist because the
chart generators are float maths that a Kotlin port has to reproduce bit for bit, and the questions
that raises are answered by measuring rather than by reading the source. The full reasoning and every
result is in the repo root's `phase-w1-numeric-sanitization.md`.

```bash
uv run python scripts/generation_workload.py       # print the workload's shape (documents per mode)
uv run python scripts/verify_golden_stability.py    # cross-machine digest + all 90 committed pins
uv run python scripts/measure_libm_parity.py        # what reaches np.exp/np.log, + the libm values
uv run python scripts/probe_ulp_sensitivity.py      # does a 1-ulp exp/log difference reach the output?
cd scripts/kotlin_side && java LibmParityCheck.java ../artifacts/libm-parity-sample.tsv
```

* `generation_workload.py` is the shared definition of "the whole generation path, swept" — the seed
  list, the per-injector configs, the figure panels. The other scripts import it so they cannot drift
  into measuring different things, and it reuses the golden suite's own fingerprint function rather
  than re-deriving the recipe.
* `artifacts/` holds the committed measurement output. The one file that is NOT committed is
  `libm-parity-full.tsv` (~120 MB); `measure_libm_parity.py --full` regenerates it, and the summary's
  SHA-256 digests are what make the committed sample a bounded view of it rather than a substitute.
* `kotlin_side/` is the JVM half of the measurements: `LibmParityCheck.java` for `exp`/`log`,
  `DoubleReprCheck.java` for `Double.toString` vs CPython's `repr`. Both are runnable references, so
  the Android repo can re-measure against its own toolchain rather than trust a number written here.

## scripts/ — the Android bundle and contract export

Phase W2. Build-time exporters for everything the native app consumes. Not part of the app either, and
they write to the repo root's git-ignored `dist/`. Full reasoning in
`phase-w2-bundle-and-contracts.md`.

```bash
uv run python scripts/export_bundle.py               # dist/bundle/ — the course as the app reads it
uv run python scripts/export_bundle.py --verify-only # re-check a bundle without rewriting it
uv run python scripts/export_bundle.py --skip-ast    # the Python half only (no node/npm needed)
uv run python scripts/export_prng_vectors.py         # dist/contracts/prng-vectors/
uv run python scripts/export_generation_goldens.py   # dist/contracts/generation-goldens/
uv run python scripts/export_generation_goldens.py --dump-id <id>   # one document's canonical JSON
uv run python scripts/export_contracts_to_android.py --target <path>
```

* `export_bundle.py` is the ONE command, and it drives the frontend for the half it cannot own: the
  lesson ASTs come from `frontend/scripts/export-ast.mjs`, because the parser dialect and the
  glossary/reference annotator are TypeScript and a Python re-derivation would be a second opinion
  about which words a reader may tap. It refuses to write a bundle whose ASTs leave `BLOCK_INVENTORY`
  (the closed set of node kinds the app can render) or whose text does not match the web's, word
  multiset for word multiset, per locale.
* `export_prng_vectors.py` writes the two random streams per primitive — NumPy's PCG64 for the charts,
  CPython's Mersenne Twister for the exercise machinery — including the `has_uint32` buffer semantics
  and, per `normal()` draw, which ziggurat path produced it (measured, not inferred).
* `export_generation_goldens.py` hashes 3 948 documents with the committed goldens' own recipe, so a
  line's first 16 hex digits are the committed fingerprint where one exists. It instruments the three
  retry loops to find the seeds that go round more than once, and pins how a double becomes text.
* `export_contracts_to_android.py` is the only sanctioned transfer path. It never creates the target,
  refuses one that is not a git repo, replaces `bundle/`+`contracts/` rather than merging, touches
  nothing else, and records the source commit with a dirty flag listing every uncommitted path.
