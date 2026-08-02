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
            content trees + figures + figure-coupling.yaml (the lesson numbers that are rounded
            values of a figure's generated output); see content/README.md for the stable-ID /
            namespacing convention and the worked-numbers-follow-the-figure rule
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

- **29 modules across 6 blocks, 35 lessons** (six modules carry a second lesson), through a
  capstone (m24) that assembles everything into a **complete trading plan** — one worked trade end to
  end (top-down protocol, sizing from the stop, live management, and the **daily stop** that closes a
  losing day), then the journal, the risk tiers that only a journal can earn, validation and the step
  to real money — and on into **order flow** (block F). Each lesson is bilingual (ES + EN)
  with server-generated, server-graded exercises, end to end: lesson → attempt → answer → grading
  with the instantiated solution → progress & statistics.
- **Order flow and microstructure** (block F, m25–m29): what a candle hides — maker/taker, the
  aggressor, and delta as the number OHLCV throws away; **CVD** (cumulative volume delta) with
  **CVD divergence as absorption made visible** rather than inferred, which is the confirmation m09's
  Wyckoff spring was missing; the **order book** (depth, walls, spoofing vs icebergs, and the
  mechanism behind m15's book thinning before a scheduled release); **premium between venues**
  (regional demand vs transfer friction, and why arbitrage caps a premium rather than erasing it); and
  **footprint charts and volume profile**. Where a credible generated exercise isn't possible — a
  depth ladder and a footprint are an instant snapshot and a distribution-inside-a-bar, not the time
  series this engine builds — the lesson **says so and names the real tools** instead of faking a
  chart, the same honest-frontier stance as m08's candle-pattern dictionary.
- **The conditions, not only the chart:** open interest read with price, funding as positioning, and
  the **basis** (perp vs spot) as a leverage-mania thermometer whose violent dislocations mark
  squeeze exhaustion; liquidity maps; the **session map inside the 24/7 clock** (where liquidity
  actually is, the weekend range and the Monday sweep that takes it); and a head-on demonstration
  that **leverage is not risk** — the same trade at 5× and 20× carries identical size and identical
  monetary risk, differing only in collateral posted and in where liquidation sits relative to the
  stop, which is the one criterion for choosing it.
- **Exercise variety:** quizzes in five sub-kinds (single-choice, true/false, multi-select, ordering,
  matching), mixed inside every bank rather than bolted on — **721 hand-written variants across 75
  quiz banks** (8–11 per bank, ~46% of them non-single-choice), so repeating a concept keeps asking a
  different question about it rather than the same one mirrored;
  multiple-choice **calculations** whose distractors are instantiated common mistakes
  (`Decimal` end to end); and **chart-reading** exercises — divergences plus fakeouts, Wyckoff,
  moving averages, oscillator readings, **MACD crossovers** (signal-line vs zero-line vs whipsaw in a
  range), Fibonacci, volume, open interest, **CVD divergence** (price makes a new extreme; does the
  aggression underneath refuse to follow it, or make its own with it?), and **candle reactions**
  (rejection/overrun/indecision, where location is 90% of the signal). Every detection chart is
  guarded by a statistical anti-leak
  test (the last candles cannot predict the answer); every classification chart is guarded by the
  credibility test (the final candles are ambient noise, never a synthetic spike) plus a
  structure-matches-label test asserting the on-screen geometry really encodes the answer.
- **Drawn levels are corroborated, not decorative:** on a chart whose question is "did this level
  break?", a horizontal line is the thing being measured, so it may not sit where price never went. An
  injector plants a level together with a `LevelGuard` — the bars that must *test* the line and the
  spans where it may not be breached — and one shared step applies it to exercises and lesson figures
  alike, so the two can never disagree about what a level means. Statistical tests over hundreds of
  seeds lock the invariants: the drawn price is the planted level exactly, every level is touched
  before the decision, the decision engages it, a level is breached only where its own guard allows
  (wicks included), and no unlabeled or duplicate line renders alongside. A **`plan`** line — an entry,
  a stop, a target, a stop-limit's trigger and limit — is the one kind those rules do *not* apply to,
  because a stop the price action reached is a stop that got hit; each is pinned instead to a specific
  feature of the planted geometry (the entry *is* the entry bar's close, the target *is* the prior high,
  the stop sits under a rejection wick nothing else trades below).
- **Markers are held to the same standard:** a label reading "HH" on a bar that is not the higher high
  teaches the wrong reading off a chart that looks fine, so every annotation is checked against the
  geometry it names — the marked bar is the extreme of its own swing, a CHoCH is *the first* lower low,
  the sweep marker is the only bar that traded below the shelf, an "order unfilled" marker sits on a bar
  the limit never reached.
- **Lesson figures:** lessons embed didactic charts via a `::figure{id}` directive — server-generated
  from a frozen seed (so each illustration is stable), reusing the exact chart renderer students see,
  with the pattern annotated and its resolution shown. Multi-panel and mobile-responsive; served by
  `GET /api/figures/{id}` (auth + locale-aware, cached). 25 figures across the course, including the
  labelled HH/HL staircase and the swing that breaks it (m08), a liquidity sweep read as a shelf being
  taken (m17) and as a liquidation wick (m06), a stop-limit that gaps past its own limit and never fills
  (m21), and one complete trade with its level, entry, stop and target drawn (m24). Every reference is
  checked to resolve in both languages, and no spec may sit unembedded.
- **Exams** (`/exams`): a sampled, graded run over the exercise bank — one question per module,
  **global** (every module) or **per-block**, each instantiated with a fresh seed. One attempt per
  question, free navigation, **no feedback until submission**; everything (your answer, the correct
  answer, the worked solution) is revealed together at the end, with an overall + per-block/per-module
  breakdown (no pass/fail). Sessions are resumable and their seeds persist, so old reviews reproduce
  exactly. **Exam attempts are a separate lane** — they never touch practice statistics or course
  mastery. Sampling, seeds and grading are server-side; no solution reaches the client mid-session.
- **Progress** (`/stats`) informs and routes; it never rewards. Two rules keep it honest when there
  is barely any data yet. **Below ten observations a rate is a fraction, not a percentage** — "2/3 at
  first attempt", never "67%" — because one data point below ten moves a percentage by more than ten
  points, so the digits would claim a resolution the sample cannot support; counts over a known total
  (lessons marked, exercises passed) are censuses and stay as they are. And **"your costliest
  sections" refuses to rank a module until you have answered at least three of its distinct
  exercises** (or all of them, in the three modules that carry only two): fourteen attempts at one
  exercise are still one exercise. Below that the panel is empty and says why — an empty panel that
  admits it beats a confident ranking built on one data point.
  Every rate carries its own denominator, because two of them are counted over different populations:
  **accuracy is over answered attempts, first-attempt accuracy is over distinct exercises**, which is
  how "1 wrong · 100% first attempt" used to be printed as one self-contradicting line.
  Each failure links straight to the exercise that produced it — `/lessons/{lesson}#ex-{exercise}`,
  the exercise inside its lesson, outlined on arrival. It is the ordinary practice player, so a
  re-attempt started there is an ordinary practice attempt; **exam failures can never appear**, since
  the whole page is computed from practice attempts only. Modules with nothing in them collapse into
  one expandable "N modules not started" row, and each fraction carries a small neutral bar (no
  colour semantics — a half-finished module is a fact, not a grade).
  The reading counter measures the **"mark lesson as read" button and nothing else** — it is named
  that way ("lessons marked as read"), and the lesson footer says so. There is no implicit
  read-tracking: no scroll heuristics, no dwell time.
- Toggle **ES ↔ EN** (progress is unchanged) and **light/dark**; check mobile widths.
- The **chart-credibility gallery** at <http://localhost:5173/dev/charts> renders grids of the
  generated charts with their ground-truth labels — the exact renderer students see. The exercise-id
  box accepts any chart exercise, e.g. `m12-ex-1` (divergences), `m08-ex-1` (fakeouts),
  `m09-ex-1` (Wyckoff), `m10-ex-1` (moving averages), `m11-ex-1` (RSI), `m11-ex-5` (MACD crossovers),
  `m13-ex-1` (Fibonacci), `m14-ex-1` (volume), `m17-ex-1` (open interest), `m26-ex-1` (CVD
  divergence); CSV export per seed on each
  card.

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
