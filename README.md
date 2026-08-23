<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# TradeSchool

Interactive crypto-futures trading academy — self-hosted, multi-user, from absolute zero to trading
with proper risk management. Third app in the **Sephilabs** ecosystem, and its **Python reference app**.

Content is bilingual (ES + EN); progress is honest information, never a reward — no streaks, points or
badges. Exercises are **generated and graded on the server**, so a solution never reaches the client
before you answer: statistics are trustworthy by construction. (The one deliberate exception is the
printed book's answer key — see [the print endpoint](#the-printed-exercises-and-the-one-endpoint-that-reveals-solutions);
grading stays server-side, so what the statistics measure is unchanged.)

- **License:** AGPL-3.0-only
- **Backend:** Python 3.14 · FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic v2 · fastapi-users
  (username identity, cookie + database strategy, Argon2, no JWT) · slowapi · NumPy · `decimal.Decimal`
  for every financial formula · pytest + testcontainers (real Postgres)
- **Frontend:** React 19 · TypeScript (strict) · Vite · react-router · TanStack Query · axios · Tailwind ·
  react-i18next · lightweight-charts · react-markdown (+ remark-gfm and a block-only directive
  dialect) · pdfmake
  (whole-course PDF, lazy-loaded on demand)
- **Infrastructure:** Docker Compose, external Postgres 17 on a shared Docker network, multi-stage builds,
  frontend published on `127.0.0.1` only, behind external nginx + Cloudflare.

## Repository layout

```
backend/    FastAPI service (see backend/README.md)
frontend/   React SPA served by nginx, /api proxied to the backend
            (course PDF export lives in frontend/src/lib/pdf/ — see "Printing the course")
content/    course.yaml manifest (course → blocks → modules → lessons → exercises) + es/ and en/
            content trees + figures + figure-coupling.yaml (the lesson numbers that are rounded
            values of a figure's generated output) + glossary.yaml (the bilingual term list, which
            refers into the lessons and never coins); see content/README.md for the stable-ID /
            namespacing convention, the worked-numbers-follow-the-figure rule and the doc-comment rule
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

- **35 modules across 7 blocks, 44 lessons** (nine modules carry a second lesson), through a
  capstone (m27) that assembles everything into a **complete trading plan** — one worked trade end to
  end (top-down protocol, sizing from the stop, live management, and the **daily stop** that closes a
  losing day), then the journal, the risk tiers that only a journal can earn, validation and the step
  to real money — and on into **order flow** (block F) and a closing **epilogue** (block G, m35).
  Each lesson is bilingual (ES + EN) with server-generated, server-graded exercises, end to end:
  lesson → attempt → answer → grading with the instantiated solution → progress & statistics.
- **The arc closes: read → size → verify → execute.** Three late modules finish it, each placed where
  its material belongs — and since the one-time 2026-08-10 renumbering (see `content/README.md`) the
  ids read in that same order, while permanent identity lives on each entity's `key`.
  **m23-l2** is multi-timeframe analysis: *a chart has no
  opinion, it has its frame's opinion* — one 4h candle **is** sixteen 15m candles, so a timeframe change
  is aggregation and never new information, levels do not move between frames (only the noise around
  them does), and the hierarchy is a mechanism rather than a rank (a daily level outweighs a 15m one
  because more participants watched it for longer, so more orders rest there). Its figure and both of
  its chart exercises draw **two linked panels of one generated series**, the upper one aggregated out
  of the lower to the cent. **m28** (after m25) is validation: m25's expectancy is a *claim*, and the
  lesson is the trading version of red-first — rules written before you look, bar-by-bar with no
  scrolling back, the arithmetic of why twenty trades cannot tell a system from a coin (a fair coin
  shows 60%+ one time in four), overfitting as the cardinal sin, and an abandonment criterion fixed
  **before** the drawdown that would make you want one. **m21** (after m19) is the market around the
  chart: the **cash-and-carry**, sold as free money and actually a thin-margin business whose short leg
  can be liquidated in a rally its own spot leg is winning — *delta-neutral is not margin-neutral*, m06
  unchanged — and the **calendar** of unlocks, listings, expiries and venue outages, which is m19's
  "conditions, never direction" mould for the third and last time.
- **Order flow and microstructure** (block F, m29–m34): what a candle hides — maker/taker, the
  aggressor, and delta as the number OHLCV throws away; **CVD** (cumulative volume delta) with
  **CVD divergence as absorption made visible** rather than inferred, which is the confirmation m09's
  Wyckoff spring was missing; the **order book** (depth, walls, spoofing vs icebergs, and the
  mechanism behind m17's book thinning before a scheduled release); **premium between venues**
  (regional demand vs transfer friction, and why arbitrage caps a premium rather than erasing it); and
  **footprint charts and volume profile**. Where a credible generated exercise isn't possible — a
  depth ladder and a footprint are an instant snapshot and a distribution-inside-a-bar, not the time
  series this engine builds — the lesson **says so and names the real tools** instead of faking a
  chart, the same honest-frontier stance as m08's candle-pattern dictionary. The block closes with
  **the SMC dialect** (m34, below) — the lexicon that renames everything the block just taught.
- **The rest of the classic canon, with its weak spots named** (block C, m15–m16): the two modules that
  close the technical-analysis block. **m15** is diagonal geometry — trendlines, channels, wedges and
  triangles — and it is taught with the honest problem stated in the prose rather than in a footnote:
  no order can rest at a price that moves, so a diagonal is *the weakest instrument in the course*, and
  two competent traders will draw two different ones on the same chart. That does not exclude it; it
  obliges the drawing discipline (two touches propose, the third validates; declare wicks or bodies and
  keep it), and it obliges reading a break with m08-l1's body-close and m14's participation, which
  matter **more** here than at a horizontal level. On the wedge's textbook directional bias, the lesson
  splits the sentence: the exhaustion half has a mechanism, the "therefore it breaks down" half is
  statistics without one. **m16** takes m08-l2's compression candle up to a market regime — volatility
  clustering, Bollinger (how far the closes scatter) against Keltner (how far a bar travels), and the
  squeeze between them, with the squeeze-momentum oscillator presented as *a repackaging of the two
  envelopes above it* rather than as a signal. It also carries a **mandatory disambiguation**: the
  volatility squeeze here and m19-l2's liquidity squeeze are unrelated mechanisms sharing a word, and
  the glossary entry for `squeeze` is a homonym with numbered senses because of it.
- **The SMC dialect, mapped onto mechanics** (m34, block F's closing module — a block of its own until
  the 2026-08-10 merge, which is where the block-g letter now free for the epilogue came from; its
  whole thesis is mapping SMC vocabulary onto the mechanics block F just taught, so it reads as F's
  coda): learners arrive from fintwit knowing *order block*, *FVG*, *BOS*, *liquidity grab*,
  *premium/discount* — vocabulary the course never named though
  it already taught most of the substance. This closing module does for that lexicon what m08-l2's candle
  dictionary does for named candle patterns: each term is mapped onto a mechanic plus a location, never
  as a standalone signal. An **order block** is the origin zone of an impulse — m08-l1's shelf of resting
  orders and m09's absorbing buyer, renamed — and it only exists once a close has broken structure, which
  is the step that makes the difference between a zone and an ordinary pullback. An **FVG** is a span
  crossed inside one candle, which is m08-l2's *liquidity void* taught as a zone rather than only as a
  warning. **BOS** is the twin m08-l1 never named (the break that *continues* the ladder, against the
  CHoCH that ends it), and m08-l1 now names it where the ladder lives. **Premium/discount** is a range
  midline and is deflated to exactly that. The **honest boundary is load-bearing**: no engineered-intent
  narratives, because "smart money did this" is contradicted by no observation and so predicts nothing;
  no zones fitted in hindsight; no retracement numerology past what m13 already allows. The stance is
  that the dialect is worth reading because the crowd speaks it, not because it predicts — the same
  focal-point logic m13 and m10-l1 use, with the same expiry date.
- **The coda: an epilogue that hands back the pen** (m35, *After this book* — block G, the one block
  in the course that holds a single module on purpose, because an epilogue is an island by nature).
  Four movements. An **honest inventory** of what the reader now has, up to the most valuable
  possession of the lot — telling a claim with a mechanism from one without — beside the equally
  honest limit that **no page gave them experience**, only the criteria to accumulate it without
  ruining themselves. **The default path, which is to deepen here**: screen time, m27's journal
  growing the sample m28 demands, re-reading (which is what un-completing a lesson is for), and the
  structural warning that protects everything before it — the temptation after a course is *more
  tactics*, and more tactics over the same sample is m28's overfitting in human form. **The two
  ladders that exist and are not this one**: the quantitative one (modelled transaction costs,
  fractional sizing, measured microstructure, statistical arbitrage, walk-forward validation, regime
  classification — each one line, each glossed, each the industrialized form of something this book
  taught by eye) closed with the honesty that it is *another profession, not level two of this one*,
  and the other-instruments one (options, the natural neighbour m21-l2 already named, with the same
  frontier sentence still standing). And **what the reader will be swimming against**: signals, VIP
  channels, the course that *does* promise — read with the tool the book gave them, *ask for the
  mechanism*, plus the one mechanism always readable even when the strategy's is hidden, namely the
  incentive of whoever is selling it. It carries **no exercises and no figures**, declared in its own
  prose and in the manifest rather than left to be noticed (everything else is examined because
  everything else can be checked), and its cross-references act as a farewell index. The last
  sentence quotes m26 back at the reader: *may the only closing bell you get remain the one you build
  yourself*.
- **The conditions, not only the chart:** open interest read with price, funding as positioning, and
  the **basis** (perp vs spot) as a leverage-mania thermometer whose violent dislocations mark
  squeeze exhaustion; liquidity maps; the **session map inside the 24/7 clock** (where liquidity
  actually is, the weekend range and the Monday sweep that takes it); and a head-on demonstration
  that **leverage is not risk** — the same trade at 5× and 20× carries identical size and identical
  monetary risk, differing only in collateral posted and in where liquidation sits relative to the
  stop, which is the one criterion for choosing it.
- **Conventions are named as conventions:** the periods everyone quotes — 9/21 intraday, 20/50 for
  swing, 50/200 on the daily, which is where the golden and death crosses got their names — are
  taught in m10-l1 as exactly that, with the mechanism m13 gives Fibonacci levels: enough people
  watch the same line that resting orders pile up around it, so it works while it is crowded rather
  than because the number is right. What the parameters change is the **horizon a signal talks
  about**, never how it is read — the three EMA signatures (order, slope, price relative to the pair)
  are self-similar across timeframes, which is why m23's style ↔ timeframe choice picks the periods
  as a side effect.
- **Exercise variety:** quizzes in five sub-kinds (single-choice, true/false, multi-select, ordering,
  matching), mixed inside every bank rather than bolted on — **867 hand-written variants across 99
  quiz banks** (3–11 per bank, ~46% of them non-single-choice), so repeating a concept keeps asking a
  different question about it rather than the same one mirrored;
  multiple-choice **calculations** whose distractors are instantiated common mistakes
  (`Decimal` end to end); and **chart-reading** exercises — divergences plus fakeouts, Wyckoff,
  moving averages, oscillator readings, **MACD crossovers** (signal-line vs zero-line vs whipsaw in a
  range), Fibonacci, volume, open interest, **CVD divergence** (price makes a new extreme; does the
  aggression underneath refuse to follow it, or make its own with it?), **candle reactions**
  (rejection/overrun/indecision, where location is 90% of the signal), and the two **zone** reads of the
  SMC dialect — did the return hold the impulse's origin zone, fail it, or was there no zone because
  nothing broke structure; and is an imbalance still open, already filled, or absent because the
  candles overlap. Every detection chart is
  guarded by a statistical anti-leak
  test (the last candles cannot predict the answer); every classification chart is guarded by the
  credibility test (the final candles are ambient noise, never a synthetic spike) plus a
  structure-matches-label test asserting the on-screen geometry really encodes the answer.
- **Generated numbers are printed for the reader, and rates are printed as rates:** authored text has
  always been written per locale, but numbers a generator *substitutes* — a calculation prompt's
  parameters, its option labels, its worked solution — used to emit raw Python into both books, so an
  ES page could carry `70000 USDT` and `0.0005` inside Spanish prose. One formatter
  (`content/numbers.py`) now serves the app, the PDF and the answer key alike; nothing formats a number
  in TypeScript, and the frontend's only counterpart is a *parser*, so the inline calculator can tell
  which option `70.000` is. Rates go one step further: they are **held as a fraction** (what the
  arithmetic multiplies by) and **stated as a percentage** (what an exchange actually shows you), with
  the worked solution converting `0.05% = 0.0005` back exactly once — which is itself the skill.
  Declared on the formula rather than in the content, so a prompt cannot drift from its own units.
  The prose hung off those numbers is localized too — the unit on a result, the verdict in
  parentheses, the closing sentence about what the figure does *not* tell you — so an ES worked
  solution no longer ends on `= 0,6 units`; only the formula skeleton's identifiers stay English.
  `tests/test_exercise_numbers.py` holds all of it: no generated string carries the other locale's
  number form, no worked-solution prose reaches an ES reader in English, and the key always quotes a
  label the option list shows.
- **The answer's *shape* never reveals it:** a longer, more carefully-hedged option is the oldest tell in
  multiple choice, and writing distractors as throwaways is what creates it. So each distractor names a
  concrete but *wrong* mechanism — ideally a misconception the course explicitly warns about — and the
  nuance that used to pad the correct option lives in the explanation, where it teaches instead of
  leaking. `tests/test_quiz_answer_bias.py` holds the whole suite to that, per locale and in aggregate
  rather than per question: for each variant it enumerates every way the same number of options could
  have been the answer, giving the exact mean and variance of "the answer is the longest option" and of
  "the answer's length advantage", then combines them into a z-score that must land inside ±3σ. Because
  the null conditions on each variant's own length multiset, it measures *which* option was made long
  and can never be satisfied by writing shorter answers. The same aggregate treatment guards the two
  position tells — the slot the answer is authored into, and the slot the generator deals it to — plus
  the true/false balance, matching pairs and ordering steps.
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
- **Zones are drawn as zones, and withheld from the question:** an origin zone and an imbalance are
  bands, not lines, so they render as a shaded **`Band`** — a filled region between two planted prices,
  in the same high-contrast neutral the `plan` lines use, because an origin zone can be demand or supply
  and a coloured band would assert a direction the lesson refuses. A band is **ground truth**: the
  exercise asks the learner to *find* the zone, so shading it on the question would be the answer, and it
  reaches the client only through grading (revealed on the same chart, once answered) and through lesson
  figures. That inversion is asserted structurally over every registered injector, not remembered. And
  unlike a level, a band's contract is **asserted, never enforced** — widening a wick to make an
  imbalance "tested" would destroy the untraded span the band exists to point at — so each kind's claim
  is pinned over 300 seeds per label: the zone precedes the break it is the origin of, the return really
  trades into it, which *side* price ends on carries the label while the *distance* does not, and every
  chart carries at most one imbalance, matching the three-candle detector exactly.
- **Two frames of one series, aggregated to the cent:** m23-l2's chart exercises and its figure carry a
  second candle panel — the same generated stretch at a coarser resolution — because "is this run a
  pullback on the frame above it?" cannot be asked of one chart. The coarser panel is never generated
  separately: it is `aggregate`d out of the published lower one (first open, last close, extreme high,
  extreme low, summed volume), which is the lesson's own claim that a timeframe change is aggregation
  and not new information. `tests/test_chart_timeframes.py` re-derives every upper bar from its four
  lower ones **to the cent**, and then, red-first, corrupts each field in turn and requires the checker
  to catch it. The panel rides the ordinary `pattern_chart` pipeline as one more conditional payload
  key (the `oi`/`cvd`/`diagonals` precedent) and the PDF stacks the pair into a single captured image,
  so the printed exercise ↔ answer-key bijection is untouched. Two anti-leak details are load-bearing:
  both panels render at the *same height* (a smaller "context" panel would answer "which contains the
  other?" by layout), and the aggregation ratio never reaches the client (it would answer it in JSON).
- **Lesson figures:** lessons embed didactic charts via a `::figure{id}` directive — server-generated
  from a frozen seed (so each illustration is stable), reusing the exact chart renderer students see,
  with the pattern annotated and its resolution shown. Multi-panel and mobile-responsive; served by
  `GET /api/figures/{id}` (auth + locale-aware, cached). 34 figures across the course, including the
  labelled HH/HL staircase and the swing that breaks it (m08), a liquidity sweep read as a shelf being
  taken (m19) and as a liquidation wick (m06), a stop-limit that gaps past its own limit and never fills
  (m24), and one complete trade with its level, entry, stop and target drawn (m27). Every reference is
  checked to resolve in both languages, and no spec may sit unembedded.
- **Exams** (`/exams`): a sampled, graded run over the exercise bank — one question per module,
  **global** (every module that has a bank, so the epilogue is skipped) or **per-block** (offered only
  for blocks that have one), each instantiated with a fresh seed. One attempt per question, free
  navigation, **no feedback until submission**; everything (your answer, the correct
  answer, the worked solution) is revealed together at the end, with an overall + per-block/per-module
  breakdown (no pass/fail). Sessions are resumable and their seeds persist, so old reviews reproduce
  exactly. **Exam attempts are a separate lane** — they never touch practice statistics or course
  mastery. Sampling, seeds and grading are server-side; no solution reaches the client mid-session.
- **Progress** (`/stats`) informs and routes; it never rewards. Three rules keep it honest when there
  is barely any data yet. **Below ten observations a rate is a fraction, not a percentage** — "2/3 at
  first attempt", never "67%" — because one data point below ten moves a percentage by more than ten
  points, so the digits would claim a resolution the sample cannot support; counts over a known total
  (lessons marked, exercises passed) are censuses and stay as they are. And **"your costliest
  sections" refuses to rank a module until you have answered at least three of its distinct
  exercises** (or all of them, in the three modules that carry only two): fourteen attempts at one
  exercise are still one exercise. Below that the panel is empty and says why — an empty panel that
  admits it beats a confident ranking built on one data point. The third rule applies the same
  standard to the cohort: **"where everyone struggles" publishes a row only once three distinct
  learners have attempted it**, because below that the panel is not aggregate at all — at two
  learners you subtract yourself and are reading one identifiable classmate's results — and the
  headcount it prints counts *people*, kept apart from the first-attempt observations the rate is
  computed over (one learner answering four exercises is four observations and one person).
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
- **Reading-time estimates** appear on the course header, every block header, every module card, the
  module page — its own remaining total, plus **each lesson's own estimate on its row**, which is the
  number you need when choosing which of a two-lesson module to open — and the lesson page, appended to
  the existing meta line (`0/2 lecciones · 0/6 ejercicios ·
  ~25 min`). Every one of them is **time remaining** — total minus the lessons you have marked read — so
  a finished module, block or course shows **no figure at all** rather than "~0 min"; a lesson page is
  atomic and always shows its own full estimate. The estimate is computed **per lesson, per language**,
  at registry load: prose words at `READING_WPM` (200) plus `FIGURE_SECONDS` (30) per embedded
  `::figure`, counting callout text as prose and ignoring directives, markup and fenced code. Exercises
  and exams contribute nothing. Both constants are a **starting calibration** meant to be tuned against
  real reading, which is why they are named constants in one module
  (`backend/src/tradeschool/content/reading.py`) and why the estimate is a derived metric that is
  **absent from the course export**. ES and EN differ for the same lesson because the prose differs.
  The API serves **seconds per lesson** and nothing else — every module/block/course figure is a sum of
  those seconds, rounded once at display time (`frontend/src/features/course/readingTime.ts`), so no
  aggregate is ever built from already-rounded minutes and the levels nest exactly. Past an hour the
  same figure is said as **hours and minutes** (`~5 h 20 min`), with an exact hour dropping the minutes
  part (`~1 h`, never `~1 h 0 min`) — one format in both languages, and still only that one rounding:
  the hours are a *split* of the rounded total (`floor` + `%`), not a rounding of their own.
- Toggle **ES ↔ EN** (progress is unchanged) and **light/dark**; check mobile widths.
- The header **wordmark is the way back to `/course`** from any depth — an ordinary client-side link
  (keyboard-focusable, Enter-activated, focus ring in both themes), with no `replace` of its own so
  that Back still returns to the lesson you left, while a click on the course page itself replaces
  rather than stacking a second entry. `HOME_PATH` in `frontend/src/components/layout/nav.ts` is the
  one definition of where home is — the wordmark, the first nav item and `App.tsx`'s redirects all
  read it. The wordmark above the **login/register** card is deliberately *not* a link: there is
  nowhere for it to go that `RequireAuth` would not bounce straight back to `/login`.
- The **chart-credibility gallery** at <http://localhost:5173/dev/charts> renders grids of the
  generated charts with their ground-truth labels — the exact renderer students see. The exercise-id
  box accepts any chart exercise, e.g. `m12-ex-1` (divergences), `m08-ex-1` (fakeouts),
  `m09-ex-1` (Wyckoff), `m10-ex-1` (moving averages), `m11-ex-1` (RSI), `m11-ex-5` (MACD crossovers),
  `m13-ex-1` (Fibonacci), `m14-ex-1` (volume), `m19-ex-1` (open interest), `m30-ex-1` (CVD
  divergence), `m34-ex-1` (origin zones) and `m34-ex-2` (imbalances) — the last two draw their
  ground-truth **zone**, which the exercise itself withholds; CSV export per seed on each
  card.

## API URLs are course-scoped

Everything whose data belongs to a course hangs off the course:

```
/api/courses/{course}                      the course tree
/api/courses/{course}/export               whole-course theory (see below)
/api/courses/{course}/print/exercises      the printed exercises + answer key
/api/courses/{course}/glossary             the glossary
/api/courses/{course}/lessons/{id}         …/complete (POST marks, DELETE unmarks), /modules/{id}, /figures/{id}
/api/courses/{course}/exams                …/current, /{exam_id}, /{exam_id}/submit, …
/api/courses/{course}/attempts             …/{attempt_id}, /exercises/{id}/attempts
/api/courses/{course}/stats/me             …/stats/global (anonymous aggregate, within the course)
```

`{course}` is a permanent slug — today `crypto-futures`, the same id the manifest and the PDF
filename already use. It joins the stable-identifier namespace in `content/README.md`: chosen once,
never renamed. An unknown slug is a clean `404 COURSE_NOT_FOUND`, resolved *before* the resource is
looked up, so a wrong course plus a wrong lesson reports the course miss.

Genuinely global endpoints stay unscoped: `/api/auth/*` (an account is not per-course), `/api/health`,
`/api/version`, and the dev-gated `/api/dev/*`.

**Deprecated aliases.** Every pre-scoping URL still works — `/api/course`, `/api/course/export`,
`/api/glossary`, `/api/lessons/{id}`, `/api/exams`, `/api/stats/me`, … — and **serves directly rather
than redirecting**, so payloads are byte-identical and a POST is not at the mercy of a client's
redirect handling. Alias responses carry RFC 8594 headers naming the successor:

```
Deprecation: true
Link: </api/courses/crypto-futures/glossary>; rel="successor-version"
```

They are hidden from `/api/docs`, so the schema teaches only canonical URLs. They exist for clients
we do not control; **our own frontend and PDF pipeline use the scoped URLs exclusively**, enforced by
`frontend/src/api/urls.test.ts`. Removal point is the day a second course lands, which is when an
unscoped URL stops having an unambiguous answer.

One router serves both mounts: `current_course` reads the slug off `request.path_params`, returning
the single course when the segment is absent. That is also why the alias is marked in middleware
rather than with `deprecated=True` — the two mounts share one route object, so per-mount metadata has
nowhere to live on it.

### Page URLs carry the course too

The SPA mirrors the API, so the address bar always says which course you are in:

```
/courses/{course}                    the course page (home)
/courses/{course}/lessons/{id}       …/modules/{id}, /glossary, /stats
/courses/{course}/exams              …/{examId}, /{examId}/review
```

Routes are declared with the **literal** slug via `coursePath()` in `components/layout/nav.ts`, not a
`:course` param. The API client targets one course, so a route matching any slug would render
`/courses/anything/glossary` full of this course's content — a URL that lies. The param arrives with
the threading, the day a second course does.

Pre-scoping page URLs redirect (`/glossary` → `/courses/crypto-futures/glossary`, query string kept),
so old bookmarks land and the address bar corrects itself. `App.routes.test.tsx` pins that table.
nginx needs no change: `try_files $uri /index.html` already serves any depth.

A bookmark from before the one-time 2026-08-10 renumbering (see `content/README.md`) does *not*
redirect: the permutation reused sixteen ids outright, and append-only growth has since re-issued the
four it vacated (`m31`–`m34` now hold the order book, the venue premium, footprint and the SMC
dialect), so every old id names a live page and the URL cannot say which era it was bookmarked in. A
display id always resolves to its current holder. Per-id redirects were removed for that reason and
must not come back: the route is a static segment, so it would shadow the live module.

## Which build am I running?

The stack builds from the **working tree**, not from a commit, so "is this container running my
changes?" is a real question. One unauthenticated curl answers it:

```
curl -s localhost:8092/api/version
{"commit":"9a72932-dirty","builtAt":"2026-08-08T19:47:32Z","routes":31}
```

`commit` and `builtAt` are baked in as build args; `routes` is the registered API path count, a cheap
tell that the image carries the endpoints you expect. Stamp them by exporting the two variables:

```fish
env GIT_COMMIT=(git rev-parse --short HEAD)(git diff --quiet; or echo -dirty) \
    BUILD_TIME=(date -u +%Y-%m-%dT%H:%M:%SZ) \
    docker compose up -d --build
```

Both default to `unknown` in a bare `docker compose up --build`, which is itself the answer: an image
that cannot say what it was built from was not built by the command above.

A 404 on an endpoint you just added is usually one of two things — a stale image, which `/api/version`
now settles, or the path itself. Course-owned endpoints live under `/api/courses/{course}/…`; see
"API URLs are course-scoped" above.

## Exporting the course theory

A logged-in user can pull the entire course as one JSON document — every block → module → lesson
with its prose (exercise directives stripped, theory only), **in both languages by default**. The course
is authored in ES + EN and every content change touches both, so an archive of one of them is half an
archive; `lang` is how you ask for less.

```
GET /api/courses/{course}/export                  # both languages (the default) — see the shape below
GET /api/courses/{course}/export?lang=all         # the same document, asked for explicitly
GET /api/courses/{course}/export?lang=es          # one language (en|es), as plain strings
GET /api/courses/{course}/export?download=true    # attachment (tradeschool-course-all.json, or -es/-en)
```

The two shapes are discriminated by their top-level key, so a consumer never has to guess:

```jsonc
// no lang / lang=all  ->  every localized field is paired
{"locales": ["en", "es"],
 "blocks": [{"id": "block-f", "title": {"en": "Order flow and microstructure", "es": "Flujo de órdenes y microestructura"},
   "modules": [{"id": "m34", "title": {…}, "summary": {…},
     "lessons": [{"id": "m34-l1", "title": {…}, "markdown": {"en": "# The SMC…", "es": "# El dialecto…"}}]}]}]}

// lang=es  ->  plain strings, one language
{"locale": "es", "blocks": [{"id": "block-f", "title": "Flujo de órdenes y microestructura", "modules": [{…}]}]}
```

Both shapes come from one walk of the manifest, so they can never carry different modules. Note that
`::figure{id=…}` markers are **kept** in the exported prose (only `::exercise` directives are stripped),
so you can see where each generated chart belongs.

Both shapes also carry a `glossary` — a flat list under `lang=…`, and `{"en": […], "es": […]}` in the
bilingual document, matching how the localized fields pair.

### The glossary

```
GET /api/courses/{course}/glossary            # alphabetical in your account's locale
GET /api/courses/{course}/glossary?lang=es    # …or the locale you name (en|es)
```

The glossary **refers, it does not teach**: every entry is one or two sentences distilled from the
lesson that teaches the term, plus the pointer back to it. It is authored in `content/glossary.yaml`
and validated at startup — origins must be real lesson **keys** (served as display ids), glossary ids
share the one permanent id namespace,
and **no term may enter the glossary that does not appear in that locale's prose** (the glossary never
coins). Three entry shapes:

```jsonc
{"id": "g-funding", "term": "funding", "origin": "m04-l1", "originTitle": "Futuros perpetuos",
 "definition": "Un pago periódico entre largos y cortos…"}

// a homonym: one entry, numbered senses, each with its own origin
{"id": "g-premium", "term": "prima",
 "senses": [{"origin": "m19-l1", "definition": "…"}, {"origin": "m32-l1", "definition": "…"}]}

// an alias: a second name the course uses, deferring to the canonical entry
{"id": "g-choch", "term": "CHoCH", "origin": "m34-l1",
 "aliasOf": {"id": "g-change-of-character", "term": "cambio de carácter"}}
```

Ordering is alphabetical **per locale**, accent-insensitive, and the two locales deliberately sort
differently — an entry is looked up by the word the reader actually met, and roughly a third of the ES
terms are English pass-throughs (`funding`, `spot`, `spring`, `order block`).

#### The prose points into the glossary

Term occurrences in lesson prose become links: a hover tooltip (tap-and-dismiss popover on touch) in
the app, an internal jump to the glossary entry in the PDF. **One annotator decides both** —
`frontend/src/lib/glossary/annotate.ts`, run over the mdast each renderer already parses, so what the
book links and what the screen marks cannot drift. Neither surface detects terms on its own, and
`surfaces.test.tsx` renders real lessons down both pipelines and compares them term for term.

Detection is word-boundary anchored (the EMA-inside-`sistema` trap), tolerant of the ~100-column hard
wrap — a multi-word term split across two lines still matches, the same trap the never-coins guard
has — and blind to headings, code, link text and figure directives. It never stems: an entry lists
its own `match` variants where the derived plural is wrong. *Which* occurrences get marked is one
rule with two lifetimes:

| | which occurrence | what the reader gets |
|---|---|---|
| **App** | first per **lesson** | the term is a tooltip once per lesson, wherever it appears |
| **PDF** | first in the **book** | the term is linked at most once in ~200 pages |

A term is never linked in the lesson it points back at — a link to an entry that points back at the
page you are reading is a loop. That occurrence still **spends** the term's one slot in the book, so
a term the course first uses inside its own lesson gets no PDF link at all while remaining a tooltip
everywhere else in the app. Today that is 111 of 178 terms in EN and 119 in ES: the book carries 67
term links (EN) / 57 (ES) against 661 / 579 tooltips.

Every decision is recorded in `content/glossary-links.<locale>.txt`, a **frozen golden** that a
content change diffs loudly instead of moving links in silence — that diff is where a false positive
gets caught before a reader meets it, and there were plenty ("base de datos", "a lo largo de", "Wall
Street", "the summed footprints"). See `content/README.md` for the per-entry keys and how to
regenerate it.

#### The prose points across the course

Lesson prose also names other lessons by id — "una costura limpia con m22, la gestión del riesgo" —
and every `mXX` / `mXX-lN` mention becomes a link too: in the app a discreet dotted link that
navigates, titled on mouse hover / keyboard focus through the same one-panel popover the glossary
uses ("M22 · Gestión del riesgo"; on touch the tap simply navigates, and the title is the first thing
on the page that opens); in the PDF an internal jump to the module or lesson heading, in the same
quiet dotted cross-reference dress as a term link, with the printed text exactly as authored. The
first mention of another module in a lesson carries its short topic in the prose itself — that
apposition is what backs the reference on paper, where there is nothing to hover.

It is the same **one annotator** grown a second mark type — same walk, same word-boundary rules
(`fig-m11-…` and `m08-ex-6` are not mentions of m11 or m08), same structural blindness to headings
and code — and `lib/refs/registry.ts` is the ONE place a mention resolves to a target: a lesson
mention to that lesson, a module mention to the module page, or straight to its only lesson when the
module has just one (the same rule the lesson page's back link already follows). Every mention links
on every surface — a reference is navigation, not vocabulary, so there is no first-occurrence policy —
except a mention of the very page it sits on, which stays plain text. The registry is built from
whatever course structure each surface already holds, all of it rendered from the id↔key registry at
the API boundary, so a future display renumbering reaches every link by rebuilding, never by editing
a resolver.

The record is `content/lesson-refs.<locale>.txt`, a frozen golden under the same discipline, with
both axes in permanent **key** space; its suite also asserts **zero dangling references** — every
id-shaped mention in every lesson must name a module or lesson that exists, in both locales,
mention for mention — which is a prose-integrity guard the course never had before.

Auth (session cookie) is required, like the rest of the content API. The registry is built **once at
startup**, so newly authored content needs a backend restart before it appears in an export.

### The printed exercises, and the one endpoint that reveals solutions

```
GET /api/courses/{course}/print/exercises?lang=es   # one frozen instance per exercise, WITH its answer
```

This is what the PDF's exercises and its answer key are made of, and it is the **only** endpoint that
hands a solution to a client without a learner having answered first. That is what an answer key *is* —
the solutions, in the reader's hands, printed at the back of the book — so the trade-off is stated here
rather than hidden: **grading is untouched and still server-side**, an attempt still reveals nothing
before it is answered, and the statistics are computed from graded attempts exactly as before. A reader
who wants the answers can read them here, as they can turn to the back of any textbook.

Three properties make it a *book* rather than a dump:

* **A fixed seed per exercise.** Each instance is generated at `print_seed(exercise key)` — blake2b of
  the exercise's permanent `key` (its id at creation; for anything renumbered on 2026-08-10, its OLD
  id), deliberately not `hash()`, which is salted per process and would print a different book after
  every restart. Two exports of the same content version are identical, and a display renumbering
  cannot silently reprint the book.
* **One instance, one pass.** `generate()` is called once; the answer is read from `grade()` on the same
  `(config, seed)` and then **re-graded as a submitted answer, which must come back correct** before it
  is published. Every number the answer quotes is read out of the payload being published — a chart
  answer's prices are indexed out of the very series the reader sees — so a key cannot drift from its
  question. `tests/test_print_exercises.py` re-grades all 147.
* **Nothing dropped quietly.** An exercise that cannot be printed is listed in `excluded` with a reason
  and logged; the export console names it, and the lesson in the PDF prints *"N interactive exercises
  not included"*. Today the whole course prints: 147 of 147, nothing excluded.

## Printing the course (PDF)

**Export PDF**, next to the course-page header, produces the whole course as one print-ready document
in the language being browsed — cover, table of contents with page numbers, block and module headings
with their summaries, every lesson's prose, callouts and figures, **the lesson's exercises after its
prose, and an answer key at the back**, and it is **navigable**: bookmarks, a clickable contents, term
links into the glossary and exercise ↔ answer cross-links (see below). ~261 pages (EN) / ~274 (ES):
44 lessons, 34 figures, 147 exercises, 30 of which print a chart. Every lesson starts on a new page,
and the answer key is a table-of-contents entry with a resolved page number. The running footer carries the course **subtitle** (`course.subtitle`, the book's short name — the full title would wrap), the
**top-level section the page belongs to** (the block, or the answer key) and the page number, so a page
found loose still says where it came from; the cover and the contents precede the first block and name
no section. The file is named `tradeschool-<course>-<locale>-<YYYY-MM-DD>.pdf`.

### Navigating the book

The PDF is navigable, not just printable, and every one of these is a pdfmake feature rather than a
post-processing step:

* **A document outline** (bookmarks) that mirrors `course.yaml` exactly — block › module › lesson,
  with the glossary and the answer key beside the blocks. The 178 glossary entries stay out of it: a
  bookmark pane listing every term is a second glossary, not a way around the book.
* **A clickable table of contents.** This one already worked — pdfmake gives every `tocItem` row a
  `linkToDestination` — so what changed is that every heading now carries a **content id** instead of
  pdfmake's invented `toc-_default_-7`, and a test says so.
* **Term links into the glossary**, one per term across the whole book (see the glossary section
  above), styled as a dotted rule in the muted grey rather than web-blue: a printed cross-reference
  should be findable and otherwise invisible.
* **Exercise ↔ answer key, both directions.** The printed number jumps to its answer and the answer's
  number jumps back, which is what makes the stable numbering navigable.
* **The glossary's own pointers.** "Taught in M19-L1 · The basis" reaches that lesson, and an alias's
  `CHoCH → change of character` reaches that entry — a reference whose pointers you cannot follow is
  half a reference.

Two things constrain how those are built. A destination only exists where the id sits on a **text**
node — pdfmake writes one out of `line.id` as it renders a line, so the same id on a wrapping stack
anchors nothing. And a destination name is written into the file's name tree, so the exercise pair is
keyed by the **printed number**, never the exercise id: `render.test.ts` requires that no exercise id
reaches the bytes, and that rule is the reason it does not. `navigation.test.ts` walks the built
document and fails on any link whose target is not an anchor in the same document.

**That footer is why the document is rendered twice.** pdfmake gives the footer callback a page number
and nothing else, and which page a block starts on is not known until the document has been laid out.
So the first render resolves the section-to-page mapping (through the same `pageBreakBefore` hook the
pagination rules use, which is pdfmake's only view of a laid-out node) and the second one — cheap,
because every page break is decided by then, ~2s against ~50s — writes the file. Footers are drawn into
the bottom margin after the content, so none of this moves a line: the page count is identical with the
section in the footer and without it.

### Where the pages break

Two rules, in `lib/pdf/pagination.ts`, both about not stranding something from the thing that explains
it: **a heading keeps at least two lines of its own body on its page**, or it moves to the next one;
and **a callout, and an answer-key entry, print whole** — one that would straddle a page moves entire.
Figures already hold to their captions, and a test now says so.

**They are `pageBreakBefore` rules and deliberately not `unbreakable`.** pdfmake does not overflow an
unbreakable block taller than a page, it **truncates** it — `commitUnbreakableBlock` keeps `pages[0]`
and drops the rest — so a long note would lose a paragraph and the page would look fine. A break rule
cannot lose content: a box genuinely taller than a page breaks, and is **named in the generation
report** instead. (The course has none today.)

Three things about pdfmake's node model shape those rules, each found by a wrong page in the real book:
the **running footer** follows every page's content, so "is anything after this heading?" is always yes
until it is excluded; a **container** records its position where layout *enters* it, so a stack whose
unbreakable child moved to the next page still claims the one before; and a **callout's ink lives in
its inner paragraphs**, which leave with the box when it moves. `pagination.test.ts` pins all three.

The cost is real: pdfmake inserts one break per layout pass, so each one re-lays out the whole book and
typesetting goes from ~3s to ~35s per locale. That phase has no progress hook to report through — it
is the one part of the export that spins rather than counts.

**Exercises print as paper, and the key points back at the page.** A question carries a number derived
from its id — `m11-ex-5` prints as **Exercise 11.5**, stable for the life of the course because ids are
append-only — and the key answers *11.5*, so exercise → answer and answer → exercise both work. Options
are lettered where they were dealt, and the key cites that letter (`b) …`), never the option's internal
id: the correct option is rarely printed first. Chart exercises print the generated chart exactly as the
app draws it *before* you answer — no swing markers, no shaded zones, already cut before the resolution
because the instance is — and their answers name the resolution with the prices and dates of that very
chart (`Origin — 106.94 · 13/02/2024`). A calculation prints its worked solution; any exercise whose
content provides an explanation prints it as *Why*.

**It is generated in the browser, and that is the load-bearing decision.** Figures are drawn by
lightweight-charts on a canvas, so the browser is the only place a rendered figure actually exists.
Rather than teach the backend to draw charts a second time — a second renderer to keep in step with the
injectors and the level/band invariants — the export mounts each figure off-screen with the app's *own*
components (`CandleChart`, `CandleAnatomy`), pins the palette to **light** whatever theme the reader
uses (light, dark or OLED — print is paper), and screenshots it at 2× for print (~230 dpi). A figure that will not draw **fails the export,
naming the figure and reporting what it threw**; it never quietly leaves a hole where a chart should be,
because the prose around it quotes the numbers that chart draws.

That capture root mounts **only i18n** — no `ThemeProvider`, no router, no query client — which is why
`CandleChart` takes its palette through `useResolvedTheme(theme)`: an explicit theme also means "no
provider required". A figure component that insists on one of the app's providers cannot be captured, and
the symptom is silent — the chart simply never appears. `figures-providers.test.tsx` mounts the *real*
component in that harness (mocking only lightweight-charts, as the other chart tests do) to keep this
honest; `figures.test.tsx` covers the capture mechanics around it.

The document is assembled from **two** server documents, joined by id: the lesson tree from
`GET /api/courses/{course}/export?lang=…` (prose only — `registry._theory_only` strips the
`::exercise` directives server-side) and the exercises from
`GET /api/courses/{course}/print/exercises?lang=…`. Both are one
walk of the manifest, which is why the printed book cannot carry a different set of lessons — or a
different set of questions — from the app.

Exercise charts are captured the same way figures are, on the same off-screen stage, and are the reason
generation now takes noticeably longer: 34 figures plus 30 exercise charts. The button counts **both**
capture phases (`Drawing figures 12/29…`, then `Drawing exercise charts 8/23…`) rather than spinning.

```
frontend/src/lib/pdf/
  document.ts        the course -> a pdfmake document (pure: no DOM, no network, no i18next)
  markdown.ts        lesson markdown -> print content; the print twin of lib/markdown.tsx
                     (an exercise prompt is markdown too, and goes through the same renderer)
  exercises.ts       one printed exercise per kind, and the answer key — pure, like document.ts
  pagination.ts      where pages may break: headings keep their body, boxes print whole
  figures.tsx        off-screen light-theme capture of every ::figure, at print resolution
  exerciseCharts.tsx the same stage for the charts that ARE the question, markers and zones withheld
  labels.ts          every word the PDF prints that is not course content, resolved in one place
  page.ts            A4 geometry, print palette, type scale
  generate.ts        orchestration (export -> exercises -> figures -> charts -> typeset), with progress
  runtime.ts         loads the ~1 MB PDF engine on first use, never in the app's initial chunk
```

**The directive dialect is block-only, and that is not cosmetic either.** The course writes three
directives — `:::note`, `::figure`, `::exercise` — all of them block-level, so `lib/directives.ts`
installs the micromark extension with its **inline** `:name` construct deleted and every parser in the
codebase (app, print, and both golden reports) shares that one plugin. With the inline dialect on,
`03:00` parses as a childless `:00` directive: the prose said "a las 03:00 de un domingo" and both
surfaces printed "a las 03", `3:1` printed as `3`, and the line broke where the directive had cut the
text node. It was silent because a swallowed directive is not an error. `lib/directives.test.ts` pins
both halves — no inline directive is parsed whatever follows the colon, the three block ones still are —
and walks every lesson and exercise prompt in `content/` asserting the parser swallows nothing, which is
a prose-integrity guard in the same family as the reference report's zero-dangling assertion.

**The embedded font is not cosmetic.** A PDF carries its own type, and pdfmake's bundled Roboto has no
`U+2192` — `→` appears in the lesson prose over a hundred times and printed as an empty box.
`frontend/src/assets/fonts/liberation-sans/` therefore ships **Liberation Sans** (SIL OFL 1.1,
unmodified, `LICENSE` alongside it), which is metric-compatible with the app's Helvetica/Arial stack.
`fonts.test.ts` asserts it covers **every character in `content/`**, so a new symbol in a lesson fails a
test instead of printing a box.

The frontend test suite builds the real course — read straight off `content/course.yaml`, the lesson
files and the exercise configs, in both languages — and typesets it with pdfmake: lesson count and order
against the manifest, one page group per lesson, one figure block per `::figure`, no heading left at
the foot of a page and no callout or answer entry split across one (read back from the laid-out
document, in a second pass that observes the final pagination without changing it), every declared
exercise printed once inside its own lesson in course order, **a bijection between the printed exercises
and the answer key** (one entry each, both directions, no shared numbers), the key resolving to a page
number in the contents, an excluded exercise named in its lesson and absent from both halves, and a real
`%PDF` for each locale. Exercise *ids* still appear nowhere: the book speaks in numbers. Same lesson as
`test_export_is_complete_against_the_manifest`, applied to the document a reader prints.

The instances those tests print are stand-ins built from the real configs — running the generators means
running Python, and a second implementation of a seeded RNG in TypeScript is exactly the drift this
codebase refuses elsewhere. What the *instances* must satisfy lives where they are made:
`backend/tests/test_print_exercises.py` re-grades every published answer against its own seed, checks
each chart answer's prices against the published series, and asserts two builds are byte-identical.

## Themes

Four choices — **Light**, **Dark**, **OLED**, **System** — in the avatar menu and in the auth-card
footer (which collapses to an icon that cycles the same four on phone widths). The preference is
stored in `localStorage`, not on the server, so it applies before the first request and is re-applied
by a small inline script in `index.html` before React mounts (otherwise the first paint is the wrong
theme).

**System resolves to Light or Dark, and never to OLED.** `prefers-color-scheme` has no pure-black
value to report, so reading system-dark as OLED would move every dark-mode reader onto a theme they
never chose; pure black is a deliberate choice or it is nothing. `theme.test.tsx` pins the rule from
both directions.

**OLED is the dark theme plus a delta, not a third palette.** The document carries *both* `.dark` and
`.oled`, so every existing `dark:` utility still applies and an `oled:` one overrides only what pure
black actually breaks — which is also what makes the dark theme untouchable by construction: with no
`.oled` ancestor, none of those rules can match. What the delta covers, and the rule for where an
`oled:` utility belongs, is documented at the top of `src/index.css`. In short: on `#000` a shadow
falls on nothing and a surface one step lighter than the page is no longer lighter than the page, so
cards, panels, inputs and the floating menu trade elevation for a visible border, while badges,
callouts, accents and text inherit dark unchanged — ink *gains* contrast against black.

For **figures**, the same rule holds: `palette()` in `CandleChart.tsx` returns the dark palette with a
delta, so every signal colour is shared across themes — candle up/down, the indicator/signal pair, OI,
CVD, the overlay cycle, and the neutral that markers, shaded bands and `plan` lines share (m24/m27's
entry/stop/target, which are deliberately *not* red or green). Only the chrome moves: background to
pure black, a neutral grid and axis border in place of the blue-tinted grays, and an explicit
crosshair — light and dark keep the library's default there, so neither can shift. `palette.test.ts`
freezes the light and dark tables and asserts the OLED delta touches those four keys and no others.

The dev-only chart gallery at `/dev/charts` renders every figure and a sweep of generated exercise
charts with the production renderer, which is where a theme pass over the figures is done.

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

**`--build` is not optional after a content change.** `content/` is *baked into the image*
(`backend/Dockerfile`: `COPY content /app/content`, with `CONTENT_DIR=/app/content`) — there is no bind
mount — and the registry is read **once at process startup**. So `docker compose up -d` without `--build`
reuses the existing `tradeschool-backend:latest` and keeps serving the previous content, and `restart`
alone re-reads the same baked copy. Every content consumer shares that one snapshot — lessons, figures,
exercises, exams and the export — so a stale image is stale everywhere at once, never in one endpoint
only. `test_export_is_complete_against_the_manifest` asserts the export matches `content/course.yaml`
exactly, which is what turns "did my export miss a block?" into a question with an answer.
