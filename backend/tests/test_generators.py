# SPDX-License-Identifier: AGPL-3.0-only
"""Generator + formula tests: determinism, grading, Decimal, and no solution in the payload (§8)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tradeschool.exercises.base import InvalidAnswerError
from tradeschool.exercises.calculation import CalculationGenerator, _mc_options
from tradeschool.exercises.formulas import _num, get_formula
from tradeschool.exercises.quiz import QuizGenerator

QUIZ_RAW = {
    "type": "quiz",
    "variants": [
        {
            "id": "v1",
            "prompt": {"en": "Pick the true one", "es": "Elige la verdadera"},
            "options": [
                {"id": "a", "text": {"en": "right", "es": "correcta"}, "correct": True},
                {"id": "b", "text": {"en": "wrong", "es": "incorrecta"}},
                {"id": "c", "text": {"en": "nope", "es": "no"}},
            ],
            "explanation": {"en": "because a", "es": "porque a"},
        }
    ],
}

# Fully-pinned calculation: entry 20000, 10x, mmr 0.005, long -> 20000*(1-0.1+0.005)=18100.
CALC_RAW = {
    "type": "calculation",
    "formula": "liquidation_price",
    "prompt": {"en": "{side} {entry} {leverage} {mmr}", "es": "{side} {entry} {leverage} {mmr}"},
    "params": {
        "entry": {"kind": "int_range", "min": 20000, "max": 20000, "step": 1},
        "leverage": {"kind": "choice", "values": ["10"]},
        "mmr": {"kind": "choice", "values": ["0.005"]},
        "side": {"kind": "choice", "values": ["long"]},
    },
    "tolerance": {"rel": "0.001"},
    "round": 2,
}


def test_liquidation_formula_is_exact_decimal() -> None:
    f = get_formula("liquidation_price")
    result = f.compute({"entry": "20000", "leverage": "10", "mmr": "0.005", "side": "long"})
    assert result == Decimal("18100")
    short = f.compute({"entry": "20000", "leverage": "10", "mmr": "0.005", "side": "short"})
    assert short == Decimal("21900")


def test_phase2_formulas_are_exact_decimal() -> None:
    funding = get_formula("funding_payment")
    assert funding.compute({"notional": "10000", "rate": "0.0005", "side": "long"}) == Decimal("5.0000")
    assert funding.compute({"notional": "10000", "rate": "0.0005", "side": "short"}) == Decimal("-5.0000")

    margin = get_formula("initial_margin")
    assert margin.compute({"entry": "20000", "quantity": "0.5", "leverage": "10"}) == Decimal("1000.0")

    pnl = get_formula("net_pnl")
    # long 2 units 100->110; taker fee 0.0005 both fills: gross 20 - fees 0.21 = 19.79
    long_p = {"entry": "100", "exit": "110", "quantity": "2", "side": "long", "fee_rate": "0.0005"}
    short_p = {"entry": "110", "exit": "100", "quantity": "2", "side": "short", "fee_rate": "0.0005"}
    assert pnl.compute(long_p) == Decimal("19.79")
    assert pnl.compute(short_p) == Decimal("19.79")

    assert get_formula("market_cap").compute({"price": "2", "circulating": "150"}) == Decimal("300")
    assert get_formula("fdv").compute({"price": "2", "max_supply": "500"}) == Decimal("1000")

    size = get_formula("position_size_from_risk")
    assert size.compute({"equity": "10000", "risk_pct": "0.01", "stop_distance": "100"}) == Decimal("1")

    exp = get_formula("expectancy")
    assert exp.compute({"win_rate": "0.4", "avg_win": "300", "avg_loss": "100"}) == Decimal("60.0")

    # Same gross move (600), three styles: fees hit the scalper, funding taxes the swing hold.
    snr = get_formula("style_net_result")
    common = {"notional": "20000", "gross_pct": "0.03", "fee_rate": "0.0004",
              "round_trips": "15", "funding_rate": "0.0001", "funding_intervals": "6"}
    assert snr.compute({**common, "style": "day"}) == Decimal("584")  # 600 - 16
    assert snr.compute({**common, "style": "scalper"}) == Decimal("360")  # 600 - 16*15
    assert snr.compute({**common, "style": "swing"}) == Decimal("572")  # 600 - (16 + 12 funding)


def test_phase2_formula_explanations_include_the_result() -> None:
    # Every formula's step-by-step must end on the value being graded (consistency with grade()).
    cases = {
        "funding_payment": {"notional": "10000", "rate": "0.0005", "side": "long"},
        "initial_margin": {"entry": "20000", "quantity": "0.5", "leverage": "10"},
        "net_pnl": {"entry": "100", "exit": "110", "quantity": "2", "side": "long", "fee_rate": "0.0005"},
        "market_cap": {"price": "2", "circulating": "150"},
        "fdv": {"price": "2", "max_supply": "500"},
        "position_size_from_risk": {"equity": "10000", "risk_pct": "0.01", "stop_distance": "100"},
        "expectancy": {"win_rate": "0.4", "avg_win": "300", "avg_loss": "100"},
        "style_net_result": {"notional": "20000", "gross_pct": "0.03", "style": "scalper",
                             "fee_rate": "0.0004", "round_trips": "15", "funding_rate": "0.0001",
                             "funding_intervals": "6"},
    }
    for name, params in cases.items():
        f = get_formula(name)
        result = f.compute(params)
        # In BOTH locales: the worked solution is printed for a reader, so its numbers carry that
        # reader's separators, and the value it ends on must still be the graded one.
        for locale in ("en", "es"):
            steps = f.explain(params, result, locale)
            assert steps and any(_num(locale)(result) in s for s in steps), (name, locale)


def test_quiz_is_seed_deterministic_and_hides_solution() -> None:
    gen = QuizGenerator()
    config = gen.parse_config(QUIZ_RAW)
    a = gen.generate(config, seed=42, locale="en")
    b = gen.generate(config, seed=42, locale="en")
    assert a == b  # same seed -> identical instance
    options = a.payload["options"]
    assert isinstance(options, list) and len(options) == 3
    # The pre-answer payload must never leak which option is correct.
    for opt in options:
        assert set(opt.keys()) == {"id", "text"}


def test_quiz_grading() -> None:
    gen = QuizGenerator()
    config = gen.parse_config(QUIZ_RAW)
    # Only one variant, so the correct option is 'a' regardless of seed.
    good = gen.grade(config, seed=7, answer={"optionId": "a"}, locale="en")
    assert good.correct is True
    assert good.explanation == "because a"
    bad = gen.grade(config, seed=7, answer={"optionId": "b"}, locale="en")
    assert bad.correct is False
    with pytest.raises(InvalidAnswerError):
        gen.grade(config, seed=7, answer={}, locale="en")


def test_calculation_is_multiple_choice_with_diagnosable_distractors() -> None:
    gen = CalculationGenerator()
    config = gen.parse_config(CALC_RAW)  # liquidation, long, 20000 @ 10x, mmr 0.005 -> 18100
    inst = gen.generate(config, seed=1, locale="en")
    assert inst.payload["kind"] == "multiple_choice"
    opts = inst.payload["options"]
    assert isinstance(opts, list) and len(opts) == 4
    values = [o["value"] for o in opts]
    assert len(set(values)) == 4  # four distinct options
    assert "18,100.00" in values  # the correct value is one of them, EN-formatted
    for o in opts:
        assert set(o.keys()) == {"id", "value"}  # neither the correct flag nor the diagnosis leaks

    _p, _e, options, correct_id, _diag = _mc_options(config, 1)
    good = gen.grade(config, seed=1, answer={"optionId": correct_id}, locale="en")
    assert good.correct is True
    assert good.correct_answer == {"optionId": correct_id, "value": "18,100.00"}
    assert any("18,100" in step for step in good.solution_steps)

    wrong_id = next(o["id"] for o in options if o["id"] != correct_id)
    bad = gen.grade(config, seed=1, answer={"optionId": wrong_id}, locale="en")
    assert bad.correct is False
    assert any("if you" in step for step in bad.solution_steps)  # names the mistake behind the option

    with pytest.raises(InvalidAnswerError):
        gen.grade(config, seed=1, answer={"value": "18100"}, locale="en")  # free numeric input is gone


def test_calculation_distractors_stay_on_the_plausible_side() -> None:
    # A long's liquidation is below entry; every option (incl. distractors) must stay below entry, so
    # none is eliminable by that heuristic alone (§D.8b).
    gen = CalculationGenerator()
    config = gen.parse_config(CALC_RAW)
    # Read off the CANONICAL options: `_mc_options` is the raw side of the layer, and the
    # magnitude property is about the values, not about how a locale prints them.
    _p, _e, options, _cid, _d = _mc_options(config, 1)
    assert all(Decimal(o["value"]) < 20000 for o in options)


def test_quiz_true_false() -> None:
    gen = QuizGenerator()
    config = gen.parse_config({"type": "quiz", "variants": [
        {"id": "tf", "kind": "true_false",
         "prompt": {"en": "A stablecoin targets a fixed value.", "es": "..."},
         "answer": True, "explanation": {"en": "yes", "es": "sí"}},
    ]})
    inst = gen.generate(config, seed=1, locale="en")
    assert inst.payload == {"kind": "true_false"}  # the claim is the prompt; no answer leaks
    assert gen.grade(config, 1, {"value": True}, "en").correct is True
    assert gen.grade(config, 1, {"value": False}, "en").correct is False
    with pytest.raises(InvalidAnswerError):
        gen.grade(config, 1, {"value": "yes"}, "en")


def test_quiz_multi_select_all_or_nothing() -> None:
    gen = QuizGenerator()
    config = gen.parse_config({"type": "quiz", "variants": [
        {"id": "ms", "kind": "multi_select", "prompt": {"en": "Pick the risks", "es": "..."},
         "options": [
             {"id": "a", "text": {"en": "A", "es": "A"}, "correct": True},
             {"id": "b", "text": {"en": "B", "es": "B"}, "correct": True},
             {"id": "c", "text": {"en": "C", "es": "C"}},
             {"id": "d", "text": {"en": "D", "es": "D"}},
         ]},
    ]})
    inst = gen.generate(config, seed=2, locale="en")
    assert inst.payload["kind"] == "multi_select"
    for opt in inst.payload["options"]:  # type: ignore[union-attr]
        assert set(opt.keys()) == {"id", "text"}  # no 'correct' leaks
    assert gen.grade(config, 2, {"optionIds": ["a", "b"]}, "en").correct is True
    assert gen.grade(config, 2, {"optionIds": ["b", "a"]}, "en").correct is True  # order-insensitive
    assert gen.grade(config, 2, {"optionIds": ["a"]}, "en").correct is False  # partial is wrong
    assert gen.grade(config, 2, {"optionIds": ["a", "b", "c"]}, "en").correct is False


def test_quiz_ordering() -> None:
    gen = QuizGenerator()
    config = gen.parse_config({"type": "quiz", "variants": [
        {"id": "ord", "kind": "ordering", "prompt": {"en": "Order the cycle", "es": "..."},
         "items": [
             {"id": "acc", "text": {"en": "accumulation", "es": "a"}, "position": 1},
             {"id": "mup", "text": {"en": "markup", "es": "b"}, "position": 2},
             {"id": "dis", "text": {"en": "distribution", "es": "c"}, "position": 3},
             {"id": "mdn", "text": {"en": "markdown", "es": "d"}, "position": 4},
         ]},
    ]})
    inst = gen.generate(config, seed=3, locale="en")
    assert {i["id"] for i in inst.payload["items"]} == {"acc", "mup", "dis", "mdn"}  # type: ignore[union-attr]
    for it in inst.payload["items"]:  # type: ignore[union-attr]
        assert "position" not in it  # correct order not leaked
    assert gen.generate(config, 3, "en").payload == inst.payload  # deterministic
    assert gen.grade(config, 3, {"order": ["acc", "mup", "dis", "mdn"]}, "en").correct is True
    assert gen.grade(config, 3, {"order": ["mup", "acc", "dis", "mdn"]}, "en").correct is False


def test_quiz_matching_hides_pairing_and_grades() -> None:
    gen = QuizGenerator()
    config = gen.parse_config({"type": "quiz", "variants": [
        {"id": "mat", "kind": "matching", "prompt": {"en": "Match order types", "es": "..."},
         "pairs": [
             {"id": "p1", "left": {"en": "market", "es": "m"}, "right": {"en": "fills now", "es": "r"}},
             {"id": "p2", "left": {"en": "limit", "es": "l"}, "right": {"en": "price control", "es": "r"}},
             {"id": "p3", "left": {"en": "stop", "es": "s"}, "right": {"en": "triggers", "es": "r"}},
         ]},
    ]})
    inst = gen.generate(config, seed=4, locale="en")
    assert {x["id"] for x in inst.payload["lefts"]} == {"l0", "l1", "l2"}  # type: ignore[union-attr]
    assert {x["id"] for x in inst.payload["rights"]} == {"r0", "r1", "r2"}  # type: ignore[union-attr]
    # Recover the correct mapping from grade's correct_answer, then confirm it grades right.
    truth = gen.grade(config, 4, {"pairs": {}}, "en")
    correct_map = truth.correct_answer["pairs"]  # type: ignore[index,call-overload]
    assert truth.correct is False  # empty answer is wrong
    assert gen.grade(config, 4, {"pairs": correct_map}, "en").correct is True
    swapped = dict(correct_map)
    ks = list(swapped)
    swapped[ks[0]], swapped[ks[1]] = swapped[ks[1]], swapped[ks[0]]
    assert gen.grade(config, 4, {"pairs": swapped}, "en").correct is False


def test_quiz_variant_selection_is_deterministic() -> None:
    # Two variants; the same seed must always select the same variant.
    raw = {
        "type": "quiz",
        "variants": [
            {"id": "v1", "prompt": {"en": "one", "es": "uno"}, "options": [
                {"id": "a", "text": {"en": "x", "es": "x"}, "correct": True},
                {"id": "b", "text": {"en": "y", "es": "y"}},
            ]},
            {"id": "v2", "prompt": {"en": "two", "es": "dos"}, "options": [
                {"id": "a", "text": {"en": "x", "es": "x"}, "correct": True},
                {"id": "b", "text": {"en": "y", "es": "y"}},
            ]},
        ],
    }
    gen = QuizGenerator()
    config = gen.parse_config(raw)
    prompts = {gen.generate(config, seed=s, locale="en").prompt for s in range(20)}
    # With 20 seeds we should see both variants surface (variability), but each seed is stable.
    assert prompts <= {"one", "two"}
    again = gen.generate(config, seed=3, locale="en").prompt
    assert again == gen.generate(config, seed=3, locale="en").prompt
