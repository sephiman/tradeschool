<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# TradeSchool

Interactive crypto-futures trading academy — self-hosted, multi-user, from absolute zero to trading
with proper risk management. Third app in the **Sephilabs** ecosystem, and its **Python reference app**.

Content is bilingual (ES + EN); progress is honest information, never a reward — no streaks, points or
badges. Exercises are **generated and graded on the server**, so a solution never reaches the client
before you answer: statistics are trustworthy by construction.

- **License:** AGPL-3.0-only
- **Backend:** Python 3.14 · FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic v2 · fastapi-users
  (username identity, cookie + database strategy, Argon2, no JWT) · slowapi · NumPy · `decimal.Decimal`
  for every financial formula · pytest + testcontainers (real Postgres)
- **Frontend:** React 19 · TypeScript (strict) · Vite · react-router · TanStack Query · axios · Tailwind ·
  react-i18next · lightweight-charts · react-markdown (+ remark-gfm, remark-directive)
- **Infrastructure:** Docker Compose, external Postgres 17 on a shared Docker network, multi-stage builds,
  frontend published on `127.0.0.1` only, behind external nginx + Cloudflare.

## Repository layout

```
backend/    FastAPI service (see backend/README.md)
frontend/   React SPA served by nginx, /api proxied to the backend
content/    course.yaml manifest (course → blocks → modules → lessons → exercises) + es/ and en/
            content trees + figures; see content/README.md for the stable-ID / namespacing convention
docker-compose.yml  .env.example  LICENSE
```

## Local development

Backend (needs a reachable Postgres; tests bring their own via testcontainers):

```bash
cd backend
uv sync
uv run pytest          # integration tests against a real Postgres
uv run ruff check . && uv run mypy src
uv run uvicorn tradeschool.main:app --reload   # http://localhost:8000
```

Frontend (proxies `/api` → `http://localhost:8000`):

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
npm run build && npm test
```

## Reviewing locally

A throwaway Postgres on `localhost` (no shared network needed), then the two dev servers:

```bash
# 1) a throwaway Postgres on localhost (credentials match the backend defaults)
docker run --rm -d --name tradeschool-dev-db -p 5432:5432 \
  -e POSTGRES_DB=tradeschool -e POSTGRES_USER=tradeschool -e POSTGRES_PASSWORD=change-me postgres:17

# 2) backend on :8000 — DEV_MODE exposes /api/docs and the chart gallery endpoint
cd backend && uv sync
DEV_MODE=true COOKIE_SECURE=false uv run uvicorn tradeschool.main:app --reload --port 8000

# 3) frontend on :5173 (proxies /api → :8000)
cd frontend && npm install && npm run dev
```

Open <http://localhost:5173>, register an account, and review the full course:

- **23 modules across 5 blocks, 27 lessons** (four modules — m03, m09, m17, m19 — carry a second
  lesson), each lesson bilingual (ES + EN) with 4–6 server-generated, server-graded exercises, end to
  end: lesson → attempt → answer → grading with the instantiated solution → progress & statistics.
- **Exercise variety:** quizzes in five sub-kinds (single-choice, true/false, multi-select, ordering,
  matching); multiple-choice **calculations** whose distractors are instantiated common mistakes
  (`Decimal` end to end); and **chart-reading** exercises — divergences plus fakeouts, Wyckoff,
  moving averages, oscillator readings, Fibonacci, volume, and open interest. Every detection chart
  is guarded by a statistical anti-leak test (the last candles cannot predict the answer).
- **Lesson figures:** lessons embed didactic charts via a `::figure{id}` directive — server-generated
  from a frozen seed (so each illustration is stable), reusing the exact chart renderer students see,
  with the pattern annotated and its resolution shown. Multi-panel and mobile-responsive; served by
  `GET /api/figures/{id}` (auth + locale-aware, cached).
- **Exams** (`/exams`): a sampled, graded run over the exercise bank — one question per module,
  **global** (every module) or **per-block**, each instantiated with a fresh seed. One attempt per
  question, free navigation, **no feedback until submission**; everything (your answer, the correct
  answer, the worked solution) is revealed together at the end, with an overall + per-block/per-module
  breakdown (no pass/fail). Sessions are resumable and their seeds persist, so old reviews reproduce
  exactly. **Exam attempts are a separate lane** — they never touch practice statistics or course
  mastery. Sampling, seeds and grading are server-side; no solution reaches the client mid-session.
- Toggle **ES ↔ EN** (progress is unchanged) and **light/dark**; check mobile widths.
- The **chart-credibility gallery** at <http://localhost:5173/dev/charts> renders grids of the
  generated charts with their ground-truth labels — the exact renderer students see. The exercise-id
  box accepts any chart exercise, e.g. `m12-ex-1` (divergences), `m08-ex-1` (fakeouts),
  `m09-ex-1` (Wyckoff), `m10-ex-1` (moving averages), `m11-ex-1` (RSI), `m13-ex-1` (Fibonacci),
  `m14-ex-1` (volume), `m17-ex-1` (open interest); CSV export per seed on each card.

## Exporting the course theory

A logged-in user can pull the entire course as one JSON document — every block → module → lesson
with its prose (localized; exercise directives stripped, theory only):

```
GET /api/course/export            # inline JSON
GET /api/course/export?lang=es    # localized (en|es; defaults to the user's locale)
GET /api/course/export?download=true   # served as a file attachment (tradeschool-course-<locale>.json)
```

Auth (session cookie) is required, like the rest of the content API.

## Accounts

Accounts are **username + password** — no email is collected (self-hosted, no SMTP, no notifications).
Usernames are 3–32 characters (lowercase letters, numbers, `-`, `_`) and case-insensitive.

Because there is no email, password reset is an **admin action** on the server rather than self-service:

```bash
cd backend
uv run tradeschool reset-password <username>   # prompts twice for the new password (Argon2-hashed)
```

## Deployment

Copy `.env.example` to `.env` and fill it in (create the dedicated Postgres DB + user first, on the shared
network). Then:

```bash
docker compose up -d --build
```

The backend applies migrations and reconciles the course manifest on startup. The frontend is published on
`127.0.0.1:${FRONTEND_PORT}`; put your external nginx / Cloudflare in front.
