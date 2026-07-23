# TradeSchool — Requirements v1 (EN)

> Interactive crypto futures trading academy, self-hosted, multi-user. Third app in the **Sephilabs** ecosystem. Reuses the SharedLedger/TradeLog infrastructure patterns where applicable, but with a **Python backend** — TradeSchool becomes the Python reference app of the ecosystem.

---

## 1. What it is

A complete crypto futures trading course, from absolute zero to trading with proper risk management, with **server-generated interactive exercises** and **persistent per-user progress**. Content in ES + EN. No gamification: progress is honest information (what you've completed, where you fail), never a reward (no streaks, points, or badges).

- **Name:** TradeSchool
- **Repo:** `trade-school`
- **Brand:** Sephilabs
- **License:** AGPL-3.0-only (full LICENSE + SPDX headers)
- **Product languages:** ES + EN; light/dark/system theme; responsive mobile-first
- **Registration:** open (self-registration)

---

## 2. Stack

### Backend (new Sephilabs Python pattern)

| Component | Technology |
|---|---|
| Language | Python — latest stable (3.14 as of today). General rule: **latest stable versions across all libraries**; do not pin minor versions. |
| Framework | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.x (modern declarative style) |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Auth | **fastapi-users** with **cookie transport** (HttpOnly, Secure, SameSite=Lax) + **database strategy** (opaque token persisted in Postgres, revocable). NO JWT. Argon2 hashing. |
| Rate limiting | slowapi (or equivalent) on login/registration — explicit requirement, not bundled with fastapi-users |
| Dependency manager | uv |
| Tests | pytest + testcontainers-python (real Postgres). **Requirement: integration tests for the entire backend** — every endpoint and every generator covered against real Postgres, not just unit tests. |
| Numerics | Synthetic candle engine with NumPy (float acceptable: scenario data). **Financial formulas always use `decimal.Decimal`** end to end — house rule. |

### Frontend

Usual Sephilabs pattern: React + TypeScript (strict) + Vite + react-router + TanStack Query + axios + Tailwind + react-i18next.

**Specific delta:** **lightweight-charts** (TradingView, open source) for OHLC candles and indicators in chart exercises. Recharts has no native candlestick; do not force it.

### Infrastructure (SharedLedger pattern, unchanged)

- Monorepo `backend/` + `frontend/`, Docker Compose, multi-stage Dockerfiles. The `docker-compose.yml` is copied/adapted directly from the sibling projects (SharedLedger/TradeLog), swapping the backend/frontend services.
- **EXTERNAL Postgres 17** on the shared Docker network (`data`), same as the other Sephilabs apps; one dedicated database and one dedicated user per app, with permissions restricted to its own database.
- Frontend exposed only on `127.0.0.1` (never `0.0.0.0`); backend and db with no host ports. Deployed behind external nginx + Cloudflare DNS.
- Healthchecks, named volumes, `restart: unless-stopped`, json-file logging.
- `TIMESTAMPTZ` timestamps in UTC, rendered in local time.

---

## 3. Exercise architecture (core of the system)

### 3.1 Principle: server-side generation and grading

An exercise's formula/solution **never travels to the client**. Flow:

1. `POST /exercises/{id}/attempts` → the backend generates a **seed**, instantiates the template parameters and returns the statement **without the solution**.
2. The user answers → `POST /attempts/{id}/answer` → the backend evaluates using that seed's parameters, compares within the defined tolerance, persists the attempt and returns correct/incorrect **together with the step-by-step instantiated solution** (the formula with the scenario's real numbers — methodological transparency, always *after* answering).

Rationale: trustworthy statistics (not cheatable by reading the JS), exams honest by construction, and the only possible "exploit" is reimplementing the formula — i.e., having learned the lesson.

### 3.2 Generator contract

`ExerciseGenerator` abstraction (the house connector pattern): a common interface, one implementation per exercise type. Adding a new type = a new implementation, not a core change. Generators are **pure, seed-deterministic functions**: `(template, seed) → instance`. Every past attempt is exactly reproducible from its seed (historical attempt review with its scenario and solution).

Types in v1:

- **Quiz** — multiple choice / true-false. Variability: option shuffling and a per-concept variant bank.
- **Parametric calculation** — the template defines the ES/EN statement with placeholders, parameter ranges/sets, and the solution formula with numeric tolerance. `Decimal` always.
- **Synthetic chart** — see 3.3.
- **Fixture chart** — a `FixtureGenerator` drawing from a curated bank of frozen scenarios (OHLC candles in files). Fallback for concepts that are hard to synthesize (e.g., volume absorption).

### 3.3 Synthetic chart generator (high priority, must be reliable)

Two-layer composition:

- **Base price engine:** random walk with drift + volatility regimes, believable proportional wicks, correlated volume. Correlated auxiliary series when the exercise requires them (open interest, funding).
- **Pattern injectors:** force the didactic feature onto the base series — a clean RSI divergence, a level respected N times, a breakout with volume, a full Wyckoff scheme with a spring, a liquidation cluster that price sweeps. The injector **knows where it planted the pattern**, so the exercise solution is exact and comes for free, with no manual labeling.

Quality requirement: charts must be **credible and valid** — realistic candles (no sawtooth), patterns that don't scream, and coherence across series (price/volume/OI/funding when they coexist). Calibration is part of the acceptance criteria of every chart module, not a separate phase.

### 3.4 Statistical anti-abuse

- An attempt opened but not answered is recorded as abandoned but **does not count** toward the accuracy rate.
- Statistics highlight **first-attempt accuracy**, the metric that is hard to inflate.

---

## 4. Content and course manifest

### 4.1 Content as versioned data

- **Lessons:** MDX/Markdown in the repo, parallel `content/es/` and `content/en/` trees sharing stable IDs (switching language never affects progress).
- **Exercises:** structured files (YAML/JSON) per template: type, per-language statement, parameters/ranges, formula and tolerance (calculation) or generator configuration (chart), explained solution.
- **Manifest** (`course.yaml` or equivalent): declares the blocks → modules → lessons → exercises tree, the **canonical order** and the **advisory prerequisites** per module (`assumes: [...]`, not necessarily linear).

### 4.2 Reconciliation and stable IDs

- The backend ingests the manifest (at startup or via a sync command) and reconciles against the DB by stable ID.
- Progress references **IDs, never content**: inserting a module between two existing ones breaks nothing (order is a manifest attribute, not a key).
- Compatibility rules: IDs are never reused or renumbered; removing content = marking it inactive (historical progress survives); a substantial change to an exercise = **new ID** + retire the old one (never pollute statistics with two populations under the same ID).

### 4.3 Advisory order without gating

The whole course is navigable from day one. The UI marks the "suggested next" according to the canonical order and shows a **soft notice** when entering a module whose prerequisites haven't been touched ("this assumes you know X"). Informative, never a barrier.

---

## 5. Progress and statistics

### 5.1 Data

- Per-lesson completion.
- `attempts`: (user, exercise_id, seed, given answer, correct, timestamps, abandoned/answered state, nullable `exam_session_id`).

Everything else is derived; no precomputed aggregate columns in v1.

### 5.2 Per-user statistics

- Accuracy rate per module and block; average attempts until success; first-attempt accuracy.
- **"Your costliest sections"**: where failures and attempts pile up.

### 5.3 Global statistics (aggregated and anonymous)

- Which exercises and modules have the worst first-attempt rate.
- Dual use: information for the learner and **authoring feedback** (an exercise 90% of people fail may be badly worded).

### 5.4 Exams (modeled yes, UI no)

The schema models exams from v1 to avoid a later migration: `exam_sessions` + `attempts` hanging off them via `exam_session_id`. A future exam = a selection of N exercises per module with fresh seeds and its own rules (no solution until finished, one attempt per question, optional timing). **Exam UI is out of scope for v1.**

---

## 6. Syllabus v1 — 23 modules in 5 blocks (full content in v1)

### Block A — Foundations

1. **What crypto is** — blockchain at user level, Bitcoin vs altcoins vs stablecoins, what confers value and what doesn't. *(quiz)*
2. **Exchanges and custody** — CEX vs DEX, spot, basic orders, order book, custody and "not your keys". Security: 2FA, read-only API keys. *(quiz)*
3. **Reading the market** — OHLC candles, timeframes, volume, trend/range, support and resistance without mysticism. *(quiz + basic chart)*

### Block B — The instrument

4. **Perpetual futures** — contract, not possession; long/short; mark vs last price; funding and who pays whom. *(quiz + calculation: funding paid/received over a period)*
5. **Leverage and margin** — initial/maintenance margin, cross vs isolated, what leverage truly amplifies. *(calculation: position size, required margin)*
6. **Liquidation** — liquidation price calculation, why isolated saves your account, cascades. *(intensive calculation)*
7. **Real PnL** — realized/unrealized, maker/taker fees, accumulated funding, the true net of a trade. *(calculation)*

### Block C — Technical analysis

8. **Price structure** — properly drawn support/resistance, breakouts and fakeouts, pullbacks, HH/HL–LH/LL, change of character. *(intensive chart: mark levels, identify structure)*
9. **Wyckoff: accumulation and distribution** — accumulation → markup → distribution → markdown cycle, phases A–E, spring and upthrust, signs of strength/weakness, the range as the footprint of big money. *(intensive chart: identify phase, locate spring/upthrust, distinguish accumulation from distribution)*
10. **Moving averages and trend** — SMA/EMA, crosses, MA as dynamic support, why they lag by construction. *(quiz + chart)*
11. **Oscillators: RSI and MACD** — what they actually compute, the big overbought/oversold lie in strong trends, histogram and crosses. *(conceptual quiz + chart)*
12. **Divergences** — regular and hidden, on RSI/MACD, why they're reliable and still fail; confirmation with structure. *(intensive chart: detect the divergence, distinguish it from noise)*
13. **Fibonacci** — retracements and extensions, how to draw them, the honest why (partial self-fulfilling prophecy), confluence with structure. *(chart)*
14. **Volume and confirmation** — volume on breakouts, absorption, price/volume divergence. Block closer: structure + indicator + volume = confluence. *(chart)*

### Block D — Market context

15. **Macro and capital flow** — BTC dominance, ETH/BTC as thermometer, BTC → ETH → alts rotation, alt season as a flow phenomenon, correlation with traditional macro (DXY, rates, risk-on/off). *(quiz + chart: read the market moment and decide where capital sits)*
16. **Mass sentiment** — Fear & Greed index: its components and what each measures, extreme sentiment as a contrarian zone indicator (not timing), "extreme greed lasts months in a bull market", observable euphoria and capitulation. *(quiz + scenario)*
17. **Derivatives data and liquidity** — open interest read alongside price, funding as positioning sentiment, liquidation zones and the liquidity map as a magnet, long and short squeezes. *(quiz + chart: price + OI + funding scenarios)*
18. **Tokenomics** — emission and inflation, low float vs FDV, unlock calendars (cliff, vesting), how a large unlock invalidates the current technicals, where to check calendars. *(quiz + calculation: dilution, estimated sell pressure of an unlock vs daily volume)*

### Block E — The craft

19. **Risk management** — risk per trade as % of account, sizing from the stop, R-multiples, drawdown and loss asymmetry (−50% requires +100%); **portfolio risk**: position correlation (three shitcoin longs = one bet), correlations going to 1 when BTC moves hard, total directional exposure. *(intensive calculation + chart)*
20. **Trading styles: scalping, day trading, swing** — what changes between 1-5m, intraday and multi-day in crypto: funding weight per style, fees eating the edge in scalping, 24/7 market, volatility by session, analysis timeframes per style, time and mental demands. *(quiz + calculation: same setup across three styles → net of each)*
21. **Execution** — stop-market vs stop-limit, TP/SL, reduce-only, slippage (critical in scalping), why a stop-limit may not fill. *(quiz + scenario chart)*
22. **Expectancy and statistics** — win rate vs payoff, expectancy, losing streaks as normal and computable, variance and sample size. *(calculation + quiz)*
23. **Psychology and classic mistakes** — revenge trading, moving the stop, over-leveraging after a win, FOMO; mistakes mapped per style (overtrading in scalping, holding losers in swing). *(scenario quiz + chart)*

Syllabus notes: advisory prerequisites declared in the manifest, not strictly linear (e.g., 9 assumes 8; 15 assumes 3 but not all of block C). Taxation explicitly out of scope. Cross-cutting didactic stance: indicators are taught as tools with known mechanics (what they compute, when they lie), never as oracles; every derived figure shows its formulation.

---

## 7. Delivery plan — two phases with an explicit split

> **Note:** the phase split below is indicative — the builder owns the final phasing. What is mandatory is the **human verification checkpoint** it encodes: the complete exercise pipeline reviewed end to end (including visual credibility of synthetic charts) with at least one real module per exercise type, before any mass content authoring.

### Phase 1 — Complete platform + pipeline trial by fire

The entire application, functional end to end, with 3 modules of real content.

**Backend (complete):**
- Auth with fastapi-users (cookie + database strategy), open registration, rate limiting on login/registration.
- Course manifest ingestion and reconciliation by stable IDs.
- `ExerciseGenerator` contract and its **four implementations**: quiz, parametric calculation, synthetic chart, fixture chart.
- Base synthetic candle engine (price + volume) and the **divergence injector** (RSI/MACD) — the only injector in phase 1.
- Seeded attempts, server-side grading with instantiated solutions, abandoned-attempt rule.
- Progress, per-user and anonymous global statistics, exam modeling (`exam_sessions`, no UI).
- Integration tests for all endpoints and generators.

**Frontend (complete):**
- Registration/login, course navigation with advisory order and prerequisite notices, lesson view, all three exercise flows (quiz, calculation, chart with lightweight-charts), historical attempt review by seed, progress and statistics panel ("your costliest sections"), ES/EN i18n, light/dark/system theme, responsive.

**Content:** modules **1** (quiz), **6 — Liquidation** (parametric calculation) and **12 — Divergences** (synthetic chart), complete in ES and EN.

**Done criterion:** the 3 modules work end to end (lesson → server-generated attempt → answer → grading with instantiated solution → progress and statistics updated) in both languages, both themes, desktop and mobile; integration tests green; divergence charts pass a visual credibility review. **No further content is authored until this is verified.**

### Phase 2 — Full content + remaining injectors

The remaining 20 modules, in batches per block (rest of A and B → C → D → E), each batch reviewable.

- Each module: complete ES/EN lesson + 4–6 good exercises, with "trap" variants where applicable.
- **Additional pattern injectors** required by the content (phase 2 is not authoring only — it includes generation code): levels/structure and fakeouts (m8), Wyckoff schemes with spring/upthrust (m9), moving-average context (m10), RSI/MACD readings in context (m11), Fibonacci retracements (m13), volume on breakouts (m14), correlated price + OI + funding series and liquidation clusters (m17). Curated fixtures as fallback wherever synthesis falls short (e.g., absorption, m14).
- Calibration (visual credibility, conceptual correctness, ES/EN coherence) is an acceptance criterion of every batch, not a separate phase.

**Global done criterion:** all 23 modules complete and functional under the same standard as phase 1.

---

## 8. Non-negotiable

- An exercise's solution never travels to the client before answering.
- `Decimal` end to end in every financial formula; float only in scenario-data generation.
- Stable content IDs: never reused or renumbered; progress is never lost to syllabus reorganization.
- No engagement mechanisms: no streaks, points, badges, or return pressure.
- Progress shared across languages: switching ES↔EN changes nothing.
- External Postgres on the shared network; frontend only on `127.0.0.1`; one DB and one user per app.
- Server-revocable sessions (cookie + database strategy); no JWT.
