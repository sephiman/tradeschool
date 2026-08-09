# SPDX-License-Identifier: AGPL-3.0-only
"""Aggregate guards on the answer key: an option's *shape* must never reveal that it is the answer.

Every bound here conditions on the options a variant already has and asks only **which** of them was
marked correct. So a course of long, precise options passes, and a course whose long option is always
the answer fails — the statistic cannot be gamed by writing shorter prose.

The bounds are suite-wide, never per exercise. A per-exercise rule ("the answer may not be the
longest") would merely invert the tell into "the answer is never the longest", which is just as
learnable; what has to hold is that the answer is indistinguishable from its distractors *in
aggregate*, which is exactly a chance band.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import combinations
from math import sqrt
from pathlib import Path
from statistics import fmean
from typing import cast

import pytest

from tradeschool.config import get_settings
from tradeschool.content.registry import load_registry
from tradeschool.exercises.base import rng_for
from tradeschool.exercises.pattern_chart import PatternChartConfig
from tradeschool.exercises.quiz import QuizConfig, QuizKind, QuizVariant
from tradeschool.exercises.registry import get_generator
from tradeschool.exercises.types import ExerciseType

LOCALES = ("en", "es")

#: How far the suite may sit from chance before it is a tell, in standard deviations of the exact
#: permutation null. Three sigma is ~1 false alarm in 370 content passes — loose enough that ordinary
#: authoring drift never trips it, tight enough that the pre-fix content failed at thirty.
SIGMA = 3.0

#: Positions carrying fewer expected answers than this are pooled out of the position guard: a normal
#: bound on a handful of counts says nothing. (Only `e` — one variant in the whole course has five
#: options — falls below it.)
MIN_EXPECTED = 5.0


@dataclass(frozen=True)
class Answered:
    """One option-bearing variant, reduced to what the guards measure."""

    exercise: str
    variant: str
    lengths: tuple[int, ...]
    correct: frozenset[int]
    #: Which positions could have been the answer. ``None`` means "any of them", true of every quiz
    #: variant. A chart exercise may show a choice its ``targets`` exclude, and counting that choice
    #: as a possible answer would score a deliberate narrowing as a length tell.
    candidates: frozenset[int] | None = None

    @property
    def n(self) -> int:
        return len(self.lengths)


Statistic = Callable[[tuple[int, ...], frozenset[int]], float]


def _variants(kind: QuizKind) -> list[tuple[str, QuizVariant]]:
    """Every quiz variant of one sub-kind in the real course, tagged with its exercise id."""
    registry = load_registry(get_settings().content_dir)
    out: list[tuple[str, QuizVariant]] = []
    for _module, _lesson, exercise in registry.manifest.iter_exercises():
        resolved = registry.get_exercise_config(exercise.id)
        if resolved is None or resolved[0] is not ExerciseType.QUIZ:
            continue
        config = resolved[1]
        assert isinstance(config, QuizConfig)
        out.extend((exercise.id, v) for v in config.variants if v.kind is kind)
    return out


def _answered(kind: QuizKind, locale: str) -> list[Answered]:
    return [
        Answered(
            exercise=exercise_id,
            variant=v.id,
            lengths=tuple(len(o.text.get(locale)) for o in v.options),
            correct=frozenset(i for i, o in enumerate(v.options) if o.correct),
        )
        for exercise_id, v in _variants(kind)
    ]


# --- the null ------------------------------------------------------------------------------------
# Exact, not sampled: enumerate every way the same number of options could have been the correct ones
# and read the statistic's mean and variance straight off that. The largest variant in the course is
# 5-of-8, so the enumeration is 56 cases at worst.


def _moments(
    stat: Statistic,
    lengths: tuple[int, ...],
    k: int,
    candidates: frozenset[int] | None = None,
) -> tuple[float, float]:
    positions = range(len(lengths)) if candidates is None else sorted(candidates)
    values = [stat(lengths, frozenset(c)) for c in combinations(positions, k)]
    mean = fmean(values)
    return mean, fmean([(v - mean) ** 2 for v in values])


def _suite_z(rows: Sequence[Answered], stat: Statistic) -> tuple[float, float, float, float]:
    """Observed total, its null mean and sd, and the z-score of the three.

    A zero-variance null is the *ideal*, not an error: it means no relabelling of which option is
    correct could have moved the statistic, so length carries nothing. Scores as dead centre.
    """
    observed = sum(stat(r.lengths, r.correct) for r in rows)
    mean = variance = 0.0
    for r in rows:
        mu, var = _moments(stat, r.lengths, len(r.correct), r.candidates)
        mean += mu
        variance += var
    sd = sqrt(variance)
    return observed, mean, sd, ((observed - mean) / sd if sd else 0.0)


def _longest_is_correct(lengths: tuple[int, ...], correct: frozenset[int]) -> float:
    """1 when one option is strictly the longest and it is a correct one. Ties count for nobody."""
    longest = max(lengths)
    if lengths.count(longest) != 1:
        return 0.0
    return float(lengths.index(longest) in correct)


def _length_edge(lengths: tuple[int, ...], correct: frozenset[int]) -> float:
    """How many characters the average correct option carries over the average distractor."""
    right = [x for i, x in enumerate(lengths) if i in correct]
    wrong = [x for i, x in enumerate(lengths) if i not in correct]
    return fmean(right) - fmean(wrong)


def _report(name: str, rows: Sequence[Answered], stat: Statistic) -> tuple[float, str]:
    observed, mean, sd, z = _suite_z(rows, stat)
    return z, (
        f"{name}: observed {observed:.1f} over {len(rows)} variants, "
        f"chance {mean:.1f} ± {sd:.1f} (z = {z:+.2f}, limit ±{SIGMA})"
    )


# --- length --------------------------------------------------------------------------------------


@pytest.mark.parametrize("locale", LOCALES)
def test_the_longest_option_is_not_the_answer_more_often_than_chance(locale: str) -> None:
    """The oldest tell in multiple choice: when in doubt, pick the wordiest one."""
    rows = _answered(QuizKind.SINGLE_CHOICE, locale)
    z, detail = _report("single_choice longest-is-correct", rows, _longest_is_correct)
    assert abs(z) <= SIGMA, detail


@pytest.mark.parametrize("locale", LOCALES)
def test_the_answer_carries_no_systematic_length_advantage(locale: str) -> None:
    """The same tell one step weaker: never the longest, but reliably the longer."""
    rows = _answered(QuizKind.SINGLE_CHOICE, locale)
    z, detail = _report("single_choice length edge", rows, _length_edge)
    assert abs(z) <= SIGMA, detail


@pytest.mark.parametrize("locale", LOCALES)
def test_multi_select_answers_are_not_the_long_ones(locale: str) -> None:
    """Select-all is the same game with more than one right answer, and the same shortcut works."""
    rows = _answered(QuizKind.MULTI_SELECT, locale)
    longest_z, longest = _report("multi_select longest-is-correct", rows, _longest_is_correct)
    edge_z, edge = _report("multi_select length edge", rows, _length_edge)
    assert abs(longest_z) <= SIGMA and abs(edge_z) <= SIGMA, f"{longest}\n{edge}"


# --- position ------------------------------------------------------------------------------------


def _position_z(rows: Iterable[Answered]) -> list[tuple[int, float, float, float, float]]:
    """Per slot: observed, expected, sd, z — under "the answer sits anywhere, equally"."""
    rows = list(rows)
    width = max(r.n for r in rows)
    stats: list[tuple[int, float, float, float, float]] = []
    for slot in range(width):
        holders = [r for r in rows if r.n > slot]
        observed = float(sum(1 for r in holders if min(r.correct) == slot))
        expected = sum(1 / r.n for r in holders)
        sd = sqrt(sum((1 / r.n) * (1 - 1 / r.n) for r in holders))
        if expected < MIN_EXPECTED:
            continue
        stats.append((slot, observed, expected, sd, (observed - expected) / sd))
    return stats


@pytest.mark.parametrize("locale", LOCALES)
def test_the_answer_is_authored_into_every_slot_equally(locale: str) -> None:
    """The source order is content too — and a reader of the YAML, or the printed book's frozen
    instance, sees it even though the generator re-deals it for every learner."""
    stats = _position_z(_answered(QuizKind.SINGLE_CHOICE, locale))
    worst = max(stats, key=lambda s: abs(s[4]))
    detail = "authored position: " + ", ".join(
        f"{chr(97 + slot)}={observed:.0f}(chance {expected:.0f}±{sd:.0f}, z={z:+.1f})"
        for slot, observed, expected, sd, z in stats
    )
    assert abs(worst[4]) <= SIGMA, detail


def test_the_generator_deals_the_answer_to_every_slot_equally() -> None:
    """What a learner actually sees. The source order above is only the deck; this is the deal, and
    it must stay a deal — a shuffle quietly reduced to identity would restore the source's bias."""
    registry = load_registry(get_settings().content_dir)
    generator = get_generator(ExerciseType.QUIZ)
    seeds = rng_for(20260809)
    rows: list[Answered] = []
    for _module, _lesson, exercise in registry.manifest.iter_exercises():
        resolved = registry.get_exercise_config(exercise.id)
        if resolved is None or resolved[0] is not ExerciseType.QUIZ:
            continue
        config = resolved[1]
        for _ in range(200):
            seed = seeds.randrange(2**62)
            instance = generator.generate(config, seed, "en")
            if instance.payload.get("kind") != QuizKind.SINGLE_CHOICE.value:
                continue
            options = cast(Sequence[Mapping[str, object]], instance.payload["options"])
            dealt = [str(o["id"]) for o in options]
            answer = cast(
                Mapping[str, object],
                generator.grade(config, seed, {"optionId": ""}, "en").correct_answer,
            )
            slot = dealt.index(str(answer["optionId"]))
            rows.append(
                Answered(
                    exercise=exercise.id,
                    variant="",
                    lengths=tuple(range(len(dealt))),
                    correct=frozenset({slot}),
                )
            )
    stats = _position_z(rows)
    worst = max(stats, key=lambda s: abs(s[4]))
    detail = "dealt position: " + ", ".join(
        f"{chr(97 + slot)}={observed / len(rows):.1%}(z={z:+.1f})"
        for slot, observed, _expected, _sd, z in stats
    )
    assert abs(worst[4]) <= SIGMA, detail


# --- the one-bit questions -----------------------------------------------------------------------


def test_true_false_claims_are_not_mostly_false() -> None:
    """A true/false bank that is 87% false teaches "answer false", which beats reading the claim.

    Locale-independent: the claim is one statement authored in two languages, with one answer.
    """
    answers = [v.answer for _id, v in _variants(QuizKind.TRUE_FALSE)]
    total = len(answers)
    true_count = sum(1 for a in answers if a)
    expected, sd = total / 2, sqrt(total) / 2
    z = (true_count - expected) / sd
    assert abs(z) <= SIGMA, (
        f"true_false answers: {true_count} true / {total - true_count} false of {total}, "
        f"chance {expected:.1f} ± {sd:.1f} (z = {z:+.2f}, limit ±{SIGMA})"
    )


# --- chart choices -------------------------------------------------------------------------------
# A pattern_chart's options are not authored per exercise: every one of them draws from one shared
# vocabulary of label keys, rendered once in the frontend bundle. So the tell, if there is one, is not
# "this author padded this answer" but "the labels that happen to be long are the ones the generators
# happen to pick" — a corpus-wide property, and the same statistic answers it.

#: Rendered choice text lives in the frontend bundle: the backend only ever names label *keys*, and
#: what a learner (and the printed answer key) compares is the localized string. The other half is
#: locked in `i18n.test.ts`, which asserts every label an injector can emit has an entry here.
_I18N_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n"

#: Seeds drawn per chart exercise. 21 exercises x 60 puts ~1,260 instances behind the bound, which
#: resolves a ~4-point shift in the longest-is-correct rate, and costs a few seconds to generate.
CHART_SEEDS = 60

#: Second-exercise "harder drills" that deliberately show a choice their `targets` exclude, so the
#: option list cannot give the narrowed question away; each says so in its own config comment. The
#: guard below pins the set exactly — an *unlisted* never-correct choice is an eliminable distractor,
#: and an entry that stops narrowing is a stale exemption.
NARROWED_DRILLS = {
    "m08-ex-2": {"genuine_breakout"},
    "m09-ex-2": {"none"},
    "m13-ex-2": {"retrace_382"},
}

_CHART_DRAWS: dict[int, list[tuple[str, PatternChartConfig, list[tuple[list[str], str]]]]] = {}


def _chart_draws(seeds: int) -> list[tuple[str, PatternChartConfig, list[tuple[list[str], str]]]]:
    """Per chart exercise: its config and `seeds` (choices, winning label key) draws.

    Cached and locale-free — a draw yields label *keys*, and the generator picks the same target for
    a seed whichever language it is asked to render, so both locales measure one set of draws.

    Seeds are drawn from one stream rather than counted 0..n. Which target a chart lands on is a
    function of the seed and the number of targets *alone*, so walking the same low seeds through
    every exercise hands 21 copies of one 60-draw sequence to a bound that assumes independence, and
    inflates every z by roughly the square root of the sharing. Learners get unrelated seeds; so does
    this.
    """
    if seeds not in _CHART_DRAWS:
        registry = load_registry(get_settings().content_dir)
        generator = get_generator(ExerciseType.PATTERN_CHART)
        stream = rng_for(20260809)
        out: list[tuple[str, PatternChartConfig, list[tuple[list[str], str]]]] = []
        for _module, _lesson, exercise in registry.manifest.iter_exercises():
            resolved = registry.get_exercise_config(exercise.id)
            if resolved is None or resolved[0] is not ExerciseType.PATTERN_CHART:
                continue
            config = resolved[1]
            assert isinstance(config, PatternChartConfig)
            draws = []
            for _ in range(seeds):
                seed = stream.randrange(2**62)
                offered = cast(Sequence[object], generator.generate(config, seed, "en").payload["choices"])
                choices = [str(c) for c in offered]
                answer = cast(
                    Mapping[str, object],
                    generator.grade(config, seed, {"label": choices[0]}, "en").correct_answer,
                )
                draws.append((choices, str(answer["label"])))
            out.append((exercise.id, config, draws))
        _CHART_DRAWS[seeds] = out
    return _CHART_DRAWS[seeds]


def _chart_answered(locale: str) -> list[Answered]:
    text = json.loads((_I18N_DIR / f"{locale}.json").read_text(encoding="utf-8"))["chartLabel"]
    rows: list[Answered] = []
    for exercise_id, config, draws in _chart_draws(CHART_SEEDS):
        targets = set(config.targets)
        for choices, winner in draws:
            rows.append(
                Answered(
                    exercise=exercise_id,
                    variant=winner,
                    lengths=tuple(len(text.get(c, c)) for c in choices),
                    correct=frozenset({choices.index(winner)}),
                    candidates=frozenset(i for i, c in enumerate(choices) if c in targets),
                )
            )
    return rows


@pytest.mark.parametrize("locale", LOCALES)
def test_chart_choice_labels_do_not_reveal_the_answer_by_length(locale: str) -> None:
    """Two-sided, because "the answer is the short one" is as learnable as the reverse.

    Conditioned on each exercise's declared `targets`: a drill that never answers one of the choices
    it shows is a different fault (guarded below), and scoring it here would read as a length tell no
    amount of rewording could clear.
    """
    rows = _chart_answered(locale)
    longest_z, longest = _report("chart-label longest-is-correct", rows, _longest_is_correct)
    edge_z, edge = _report("chart-label length edge", rows, _length_edge)
    assert abs(longest_z) <= SIGMA and abs(edge_z) <= SIGMA, f"{longest}\n{edge}"


@pytest.mark.parametrize("locale", LOCALES)
def test_the_length_bound_would_catch_a_planted_tell_either_way(locale: str) -> None:
    """A bound nothing can fail is not a bound.

    Takes the real chart rows and re-points every answer at its longest, then at its shortest,
    allowed choice — the two tells the guard exists for — and insists both blow past the limit in
    the direction they were planted. Guards the guard: were `_length_edge` ever reduced to an
    absolute length, or the null widened until it swallowed everything, this is what would notice.
    """
    rows = _chart_answered(locale)

    def repointed(longest: bool) -> list[Answered]:
        out = []
        for r in rows:
            allowed = sorted(r.candidates) if r.candidates is not None else list(range(r.n))
            choose = max if longest else min
            out.append(replace(r, correct=frozenset({choose(allowed, key=lambda i: r.lengths[i])})))
        return out

    for planted, want_positive in ((True, True), (False, False)):
        rigged = repointed(planted)
        _lz, longest_detail = _report("planted longest-is-correct", rigged, _longest_is_correct)
        edge_z, edge_detail = _report("planted length edge", rigged, _length_edge)
        assert (edge_z > SIGMA) if want_positive else (edge_z < -SIGMA), (
            f"planting the {'longest' if planted else 'shortest'} answer did not trip the bound:\n"
            f"{longest_detail}\n{edge_detail}"
        )


def test_every_chart_choice_shown_can_actually_be_the_answer() -> None:
    """A choice outside `targets` is never correct, so repetition eventually deletes it from the
    question. Three drills accept that trade deliberately; anything else is an accident."""
    narrowed = {
        exercise_id: sorted(set(config.choices) - set(config.targets))
        for exercise_id, config, _draws in _chart_draws(CHART_SEEDS)
        if set(config.choices) - set(config.targets)
    }
    expected = {k: sorted(v) for k, v in NARROWED_DRILLS.items()}
    assert narrowed == expected, f"never-correct choices: {narrowed}, documented: {expected}"


# --- the kinds that were already clean -------------------------------------------------------------
# Measured at 0.2 <= |z| <= 0.8 before the answer-length pass and left untouched by it. They are here
# to keep it that way: both are solvable by bulk alone if length ever starts tracking the answer.


def _pairing_z(kind: QuizKind, locale: str, left: Callable[[QuizVariant], list[int]],
               right: Callable[[QuizVariant], list[int]]) -> tuple[float, int]:
    """Does the correct pairing line long with long? Null = every pairing, exactly enumerated."""
    from itertools import permutations

    observed = variance = 0.0
    counted = 0
    for _id, v in _variants(kind):
        a, b = left(v), right(v)
        values = [sum(a[i] * b[j] for i, j in enumerate(p)) for p in permutations(range(len(a)))]
        mean = fmean(values)
        var = fmean([(x - mean) ** 2 for x in values])
        if var == 0:
            continue
        observed += sum(x * y for x, y in zip(a, b, strict=True)) - mean
        variance += var
        counted += 1
    return observed / sqrt(variance), counted


@pytest.mark.parametrize("locale", LOCALES)
def test_matching_pairs_cannot_be_solved_by_length_alone(locale: str) -> None:
    z, counted = _pairing_z(
        QuizKind.MATCHING,
        locale,
        lambda v: [len(p.left.get(locale)) for p in v.pairs],
        lambda v: [len(p.right.get(locale)) for p in v.pairs],
    )
    assert abs(z) <= SIGMA, f"matching length coupling over {counted} variants: z = {z:+.2f}"


@pytest.mark.parametrize("locale", LOCALES)
def test_ordering_steps_do_not_grow_with_their_position(locale: str) -> None:
    z, counted = _pairing_z(
        QuizKind.ORDERING,
        locale,
        lambda v: [len(i.text.get(locale)) for i in sorted(v.items, key=lambda x: x.position)],
        lambda v: list(range(1, len(v.items) + 1)),
    )
    assert abs(z) <= SIGMA, f"ordering length-vs-position coupling over {counted} variants: z = {z:+.2f}"
