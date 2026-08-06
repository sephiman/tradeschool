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
