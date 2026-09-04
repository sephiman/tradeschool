<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Verification blind spots

Three checks in this repository were green on things that were wrong. None of them was a weak check;
each was a *strong* check answering a question next to the one anyone reading it assumed it answered.
The Android port found all three, because a port is the first reader that cannot fill in the gap from
context — it has only the artifact.

Each lesson below is written the same way: what the check said, what it could not say, and what was
added. Every one was shown red before it was shown green.

---

## 1. A whitespace-tokenized diff cannot see whitespace bugs

`frontend/src/lib/bundle/verify.ts` proves the bundle carries the web's text with a multiset diff:
tokenize both sides, count every word, require the difference to be empty. It has caught real damage
and it stays.

The tokenizer is `value.split(/\s+/)`.

That single expression decides what the check is *able* to be about. Whitespace is the delimiter, so
whitespace is the one thing that can never appear in the answer — a soft break that became a hard
one, a doubled space, an indent that grew a tab, a newline that flattened into a space. Every one of
them is consumed by the split before any comparison happens. (Damage that also moves *words* is a
different matter: a lost line takes its words with it and the multiset does catch that. The blind
spot is precisely whitespace that leaves the words alone.) The check is not weak here; it is silent
by construction, which is worse, because a silent check reads exactly like a passing one.

There is a second thing a multiset has no representation for: **order**. `{the, stop, is, above, the,
entry}` and `{the, entry, is, above, the, stop}` are the same bag. So are two paragraphs in the wrong
sequence, and so is one paragraph split into two. A lesson could ship with its opening and its
conclusion swapped and the diff would print `0 differing`.

**What was added.** `bundleBlocks` / `renderedBlocks` / `blockDiff` in the same file: one string per
block of reading, in order, compared block for block, with whitespace kept as information rather than
used as a delimiter. Runs of whitespace collapse (HTML collapses them too, so a doubled space is not
a reader-visible bug), but a **hard break survives as a newline**, because that one *is* visible.

**Shown red first.** Swap the first two paragraphs of `en/m01-l1.json` in a written bundle and run
`export_bundle.py --verify-only`. Not one text node changes, so the multiset is byte-identical:

```
  en prose    74505 bundle vs 74505 web tokens · 0 differing
  en blocks   44 lessons vs the rendered page · 1 disagreeing
      blocks   m01-l1 #1
        bundle   "A blockchain is a shared ledger: a list of transactions that many independent…"
        rendered "Before you ever open a trade, you need a clear, un-mystical picture of what you…"
```

Exit 2 — and on a normal export, no bundle is written at all.

---

## 2. An oracle derived from the code under test agrees with its bugs

The same multiset diff compares the bundle's text against *the web's text*. That phrase is doing a
lot of work. Concretely, it compared:

```
bundle side:     ast.ts's processor  ->  annotate  ->  JSON  ->  disk  ->  read back
reference side:  ast.ts's processor  ->  (nothing)
```

Both sides come out of the same `unified()` pipeline in `bundle/ast.ts`. So the check is real about
everything downstream of the parse — a dropped node, a mangled `→`, a stale file — and structurally
blind to the parse itself. Add a plugin to that processor and both sides acquire its behaviour at the
same instant; the diff stays empty while the bundle changes. The test agrees with itself.

This is the general shape, and it is not specific to markdown: **an oracle built from the code under
test cannot disagree with it.** It is easy to build one by accident, because the most convenient
reference is always the one already imported.

**What was added.** The reference for the block check is not another parse. It is the HTML
`LessonMarkdown` actually paints — `src/lib/bundle/rendered.tsx` runs the app's own component through
`renderToStaticMarkup`, and the blocks are read back off the DOM. That path goes mdast → hast → HTML
→ DOM through `mdast-util-to-hast` and the `components` map, none of which `bundle/` touches, and it
is configured in `lib/markdown.tsx` rather than in `bundle/ast.ts`. The two parser configurations
drifting apart is now the *first* thing the check reports instead of the one thing it cannot.

It is also why the block check is deliberately run **without annotation**: an annotated bundle
against an un-annotated page is the cheapest possible statement of "marks change no character".

**The cost.** The export got slower (~4 s → ~10 s) because it now renders 88 lesson pages. That is
the price of a second opinion and it is worth paying at export time.

---

## 3. A convention no one enforces is not a rule

Every chart series in `backend/src/tradeschool/exercises/` is rounded where it is built — 2dp for
anything with magnitude, 4dp for the small signed series (MACD, momentum). Rounded *where it is built*, which means the rule lives in a
dozen injectors and in `engine.build_series`, and nothing anywhere states it.

Three fields are copied out of an injector verbatim by both payload builders:

```python
levels    = [{"price": lv.price, ...} for lv in result.levels]
bands     = [{"low": b.low, "high": b.high, ...} for b in result.bands]
diagonals = [{"start_price": d.start_price, "end_price": d.end_price, ...} for d in ...]
```

An injector that forgets its `round(..., 2)` there puts a raw double into a digest. This is not wrong
arithmetic — the chart is fine, the lesson is fine, nobody looking at the page could tell. It is
seventeen significant digits of float noise that the Kotlin port has to reproduce bit for bit, and it
fails a whole golden file for a reason no reader of that file could find.

**What was added.** `PAYLOAD_SCALES` in `backend/scripts/export_generation_goldens.py` declares the
scale of every float a chart payload may carry, keyed by path. A value that is not already at its
scale fails the export; so does a float at a path the table does not declare, which is what stops a
new pane from shipping unquantized by being unlisted. Same shape as `export_bundle.BLOCK_INVENTORY`,
for the same reason: a closed set is the only kind that says no to something nobody thought of.

**Shown red first**, by wrapping an injector so one level price loses its rounding — production
untouched, the way the retry-loop instrument does it:

```
QUANTIZATION CHECK FAILED — … field(s) disagree with the scales the payload declares, so no
goldens were written:
  wyckoff:multi:0[0] levels[].price: 1 value(s) not at 2dp, first 9454.763333333334 (rounds to 9454.76)
  fibonacci:retrace_618:0[0] levels[].price: 1 value(s) not at 2dp, first 29361.233333333334 (rounds to 29361.23)
```

**And it found a live one on its first green run.** `diagonals.extended()` re-anchors a line to a
figure's right edge and takes the new `end_price` from `price_at`, an interpolation that nothing
rounds — while every injector rounds the anchors it drew. Only the figure path calls it, which is why
`exercise-mode.tsv` is clean and four m15 figures are not:

```
frozen:fig-m15-channel[0]   diagonals[].end_price   2178.8625714285713
frozen:fig-m15-channel[1]   diagonals[].end_price    362.4491428571429
frozen:fig-m15-trendline[0] diagonals[].end_price  11271.306285714285
frozen:fig-m15-triangle[0]  diagonals[].end_price    500.31028776978417
frozen:fig-m15-wedge[0]     diagonals[].end_price  34742.18446043165
```

**Paid, 2026-09-04.** The fix is one `round(..., 2)` in `extended()`. It **moved `figures.tsv`** for
those four charts and nothing else — `exercise-mode.tsv` is byte-identical, the 90 committed
fingerprints hold, and the figure/prose coupling check found no lesson quoting a value that moved.
The note naming the four figures and the cause is in the file's own header, which is what that file's
contract asks for.

Between finding it and fixing it the debt sat in `KNOWN_UNQUANTIZED`, pinned exactly — so a new
offender anywhere else still failed — and in both directions: an entry that stops firing fails the
export too, with `retire the note`. That is what made it temporary rather than permanent, and it is
why the pin is now empty: paying the debt forced the note to be retired in the same change. The
mechanism stays, tested with a synthetic pin, for the next finding.

---

## The shape of all three

A check is a question, and the question it actually asks is decided by details that read as
implementation: the delimiter you tokenize on, the import you took the reference from, whether a rule
is written down or merely followed. When those details go unstated, everyone downstream — including
the person who wrote the check — reads the *intent* and assumes the coverage.

The port could not do that. It had the artifact and nothing else, so it asked what the artifact
actually guaranteed, and the answer was smaller than the name of the check in all three cases.
