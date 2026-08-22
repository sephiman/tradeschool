# SPDX-License-Identifier: AGPL-3.0-only
"""Every number the exercise layer prints, printed for the reader in front of it (2026-08-22).

The generated layer used to emit raw Python into both books: an ES page could carry `70000 USDT`,
`0.0005` and `35.00` inside Spanish prose while the lesson above it wrote `70.000` and `0,05%`. The
authored layer never had this problem — quiz options and chart prompts are written per locale and
were already right — so everything here is about the three places a number is GENERATED: the
calculation prompt's parameter substitution, the option labels, and the worked solution.

Four properties, in the order they matter:

* **The reader's separators.** Nothing generated may reach a reader in the other locale's form.
* **One label, two readers.** The answer key quotes an option's label, so the key and the option
  list must be formatted by the same call — the failure this catches is a key that says `35.00`
  under an option that says `35,00`, which grades correct and reads wrong.
* **A rate is a percentage.** Prompts state rates the way an exchange does; the fraction the formula
  multiplies by may not appear in the prompt at all.
* **Same value, both books.** Separators change; the number does not.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from tradeschool.config import get_settings
from tradeschool.content.numbers import format_number, format_param, format_percent
from tradeschool.content.registry import load_registry
from tradeschool.content.schema import LOCALES
from tradeschool.exercises.calculation import (
    MISTAKE_TRANSLATIONS_ES,
    CalculationConfig,
    _display_params,
    _mc_options,
    _options_for_params,
    _sample_params,
)
from tradeschool.exercises.formulas import FORMULAS, LOCALIZED_PROSE, get_formula
from tradeschool.exercises.registry import get_generator
from tradeschool.exercises.types import ExerciseType

#: Enough draws to walk every choice param of every calculation exercise several times over. The
#: exhaustive sweep of the space belongs to `test_mental_cost.py`; this is about presentation.
SEEDS = range(24)


def _states(number: str, text: str) -> bool:
    """Does `text` state `number` as a number in its own right?

    Plain substring matching is useless here, and misleadingly so: the ES rendering of `0.5` is
    `0,5`, which sits inside the perfectly correct EN `70,500`, and the EN rendering of `1.2` sits
    inside `1,200.00`. Only an occurrence bounded by non-digits is the number itself.
    """
    return re.search(rf"(?<![\d.,]){re.escape(number)}(?![\d.,%])", text) is not None


def _calculations() -> list[tuple[str, CalculationConfig]]:
    registry = load_registry(get_settings().content_dir)
    out: list[tuple[str, CalculationConfig]] = []
    for _module, _lesson, exercise in registry.manifest.iter_exercises():
        resolved = registry.get_exercise_config(exercise.id)
        if resolved is None or resolved[0] is not ExerciseType.CALCULATION:
            continue
        config = resolved[1]
        assert isinstance(config, CalculationConfig)
        out.append((exercise.id, config))
    return out


CALCULATIONS = _calculations()
IDS = [c[0] for c in CALCULATIONS]


def test_the_course_actually_has_calculation_exercises() -> None:
    """Guards the guards: an empty parametrization would pass every test below in silence."""
    assert len(CALCULATIONS) >= 10


# --- the formatter itself ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "en", "es"),
    [
        ("70000", "70,000", "70.000"),
        ("35.00", "35.00", "35,00"),  # trailing zeros are a money answer's cents, and survive
        ("0.0005", "0.0005", "0,0005"),
        ("1234567.5", "1,234,567.5", "1.234.567,5"),
        ("-1000.25", "-1,000.25", "-1.000,25"),
        ("0", "0", "0"),
        ("999", "999", "999"),  # grouping starts at a thousand, as the prose does it
    ],
)
def test_format_number_swaps_separators_and_nothing_else(value: str, en: str, es: str) -> None:
    assert format_number(Decimal(value), "en") == en
    assert format_number(Decimal(value), "es") == es
    # Digits are the invariant: the two books state the same number, differently punctuated.
    assert [c for c in en if c.isdigit()] == [c for c in es if c.isdigit()]


@pytest.mark.parametrize(
    ("fraction", "en", "es"),
    [
        ("0.0005", "0.05%", "0,05%"),
        ("0.0001", "0.01%", "0,01%"),
        ("0.001", "0.1%", "0,1%"),
        ("-0.0004", "-0.04%", "-0,04%"),
        ("0.00055", "0.055%", "0,055%"),
        ("0.005", "0.5%", "0,5%"),
        ("0.01", "1%", "1%"),  # a whole percent keeps no decimal to punctuate
        ("0.02", "2%", "2%"),
        ("1", "100%", "100%"),  # normalize() would render this 1E+2; it must not reach a reader
    ],
)
def test_format_percent_states_the_fraction_as_an_exchange_does(
    fraction: str, en: str, es: str
) -> None:
    assert format_percent(Decimal(fraction), "en") == en
    assert format_percent(Decimal(fraction), "es") == es
    assert " %" not in es, "ES percent spacing follows the funding lessons (0,05%), not the RAE"


def test_a_non_numeric_param_passes_through_untouched() -> None:
    """`side` and `style` go through the same substitution map as the numbers, and are words."""
    for locale in LOCALES:
        assert format_param("long", locale) == "long"
        assert format_param("swing", locale) == "swing"
        assert format_param("", locale) == ""


# --- the generated layer ------------------------------------------------------------------------


def _generated_strings(config: CalculationConfig, seed: int, locale: str) -> list[str]:
    """Everything an instance shows a reader: prompt, option labels, worked solution."""
    generator = get_generator(ExerciseType.CALCULATION)
    instance = generator.generate(config, seed, locale)
    _params, _expected, _options, correct_id, _diag = _mc_options(config, seed)
    graded = generator.grade(config, seed, {"optionId": correct_id}, locale)
    labels = [str(o["value"]) for o in instance.payload["options"]]  # type: ignore[union-attr,index]
    return [instance.prompt, *labels, *graded.solution_steps]


@pytest.mark.parametrize(("exercise_id", "config"), CALCULATIONS, ids=IDS)
def test_no_generated_string_carries_the_other_locales_number_form(
    exercise_id: str, config: CalculationConfig
) -> None:
    """The EN book holds zero European numbers, and the ES book zero Anglophone ones.

    Checked against the numbers this instance actually produced rather than by sniffing the prose for
    comma-vs-dot: `1,234` is a valid thousands group in one locale and a valid decimal in the other,
    so only the pair of renderings of a KNOWN value can tell the two apart.
    """
    other = {"en": "es", "es": "en"}
    offenders: list[str] = []
    for seed in SEEDS:
        params = _sample_params(config, seed)
        for locale in LOCALES:
            mine = _display_params(config, params, locale)
            theirs = _display_params(config, params, other[locale])
            texts = _generated_strings(config, seed, locale)
            for name, wanted in mine.items():
                foreign = theirs[name]
                if foreign == wanted:
                    continue  # e.g. leverage "10", or a whole percent — nothing to punctuate
                for text in texts:
                    if _states(foreign, text):
                        offenders.append(f"seed {seed} [{locale}] {name}: {foreign!r} in {text!r}")
    assert not offenders, f"{exercise_id} prints the wrong locale's numbers:\n  " + "\n  ".join(
        offenders[:5]
    )


@pytest.mark.parametrize(("exercise_id", "config"), CALCULATIONS, ids=IDS)
def test_the_answer_key_quotes_a_label_the_option_list_shows(
    exercise_id: str, config: CalculationConfig
) -> None:
    """Option generation and the key are formatted by the same call, so they cannot disagree.

    Grading is by option id, so a mismatch here would never fail a learner — it would just print a
    key that quotes `35.00` beneath an option reading `35,00`. That is precisely the kind of drift a
    formatting change introduces silently, hence the assertion.
    """
    generator = get_generator(ExerciseType.CALCULATION)
    for seed in SEEDS:
        for locale in LOCALES:
            instance = generator.generate(config, seed, locale)
            options = instance.payload["options"]
            assert isinstance(options, list)
            labels = {str(o["id"]): str(o["value"]) for o in options}  # type: ignore[index]
            _p, _e, _o, correct_id, _d = _mc_options(config, seed)
            graded = generator.grade(config, seed, {"optionId": correct_id}, locale)
            key = graded.correct_answer
            assert isinstance(key, dict)
            assert key["value"] == labels[str(key["optionId"])], (
                f"{exercise_id} seed {seed} [{locale}]: key quotes {key['value']!r}, "
                f"option shows {labels[str(key['optionId'])]!r}"
            )


@pytest.mark.parametrize(("exercise_id", "config"), CALCULATIONS, ids=IDS)
def test_every_rate_reaches_the_prompt_as_a_percentage(
    exercise_id: str, config: CalculationConfig
) -> None:
    """A prompt states `0.05%`; the fraction `0.0005` the formula multiplies by never appears in it.

    The fraction still has to be reachable, which is what the worked solution's `rate = 0.05% =
    0.0005` line is for — asserted here so the conversion cannot be dropped from `explain`.
    """
    formula = get_formula(config.formula)
    if not formula.percent_args:
        pytest.skip(f"{config.formula} has no rate arguments")
    generator = get_generator(ExerciseType.CALCULATION)
    for seed in SEEDS:
        params = _sample_params(config, seed)
        for locale in LOCALES:
            prompt = generator.generate(config, seed, locale).prompt
            _p, _e, _o, correct_id, _d = _mc_options(config, seed)
            steps = generator.grade(config, seed, {"optionId": correct_id}, locale).solution_steps
            for name in formula.percent_args:
                if f"{{{name}}}" not in config.prompt.get(locale):
                    continue  # a rate the prompt does not quote has nothing to state wrongly
                rate = Decimal(str(params[name]))
                percent, fraction = format_percent(rate, locale), format_number(rate, locale)
                assert percent in prompt, f"{exercise_id} [{locale}]: prompt drops {percent}"
                assert not _states(fraction, prompt), (
                    f"{exercise_id} [{locale}]: prompt still states the raw fraction {fraction}"
                )
                assert any(f"{percent} = {fraction}" in step for step in steps), (
                    f"{exercise_id} [{locale}]: the worked solution never converts {percent}"
                )


# --- the prose around the numbers ---------------------------------------------------------------

#: One params dict per BRANCH of every formula's `explain`, so a phrase that only appears on the
#: short side, the zero-delta case or the swing style is still exercised.
BRANCHES: list[dict[str, object]] = [
    {"entry": "20000", "leverage": "10", "mmr": "0.005", "side": side} for side in ("long", "short")
] + [
    {"notional": "70000", "rate": rate, "side": side}
    for rate, side in (("0.0005", "long"), ("0.0005", "short"), ("0", "long"))
] + [
    {"entry": "41000", "quantity": "1", "leverage": "25"},
    {"price": "3.5", "circulating": "1400"},
    {"price": "3.5", "max_supply": "3000"},
    {"equity": "60000", "risk_pct": "0.005", "stop_distance": "500"},
    {"win_rate": "0.55", "avg_win": "200", "avg_loss": "360"},
    {"price_a": "60000", "price_b": "60900"},
] + [
    {"entry": "35000", "exit": "30500", "quantity": "0.5", "side": side, "fee_rate": "0.0002"}
    for side in ("long", "short")
] + [
    {"taker_buy": buy, "taker_sell": sell}
    for buy, sell in (("1450", "600"), ("600", "1450"), ("600", "600"))
] + [
    {"notional": "31000", "gross_pct": "0.02", "style": style, "fee_rate": "0.0004",
     "round_trips": "15", "funding_rate": "0.0001", "funding_intervals": "6"}
    for style in ("scalper", "day", "swing")
]


def _steps(locale: str) -> list[tuple[str, str]]:
    """(formula id, line) for every branch of every formula, in one locale."""
    out: list[tuple[str, str]] = []
    for name, formula in FORMULAS.items():
        for params in BRANCHES:
            if set(formula.arg_names) - set(params):
                continue  # these params are not this formula's branch
            for line in formula.explain(params, formula.compute(params), locale):
                out.append((name, line))
    return out


def test_no_worked_solution_prose_reaches_an_es_reader_in_english() -> None:
    """`(you pay)`, `units`, `million USD`, the closing sentences — all of it, in every branch.

    The ES book had these in English until 2026-08-22: the numbers were localized first and the
    prose hung off them was not, so a Spanish page ended a worked solution on `= 0,6 units`.
    """
    english = dict(_steps("en"))
    spanish = _steps("es")
    assert english and spanish
    joined_en = " ".join(line for _f, line in _steps("en"))
    leaks: list[str] = []
    for phrase in LOCALIZED_PROSE:
        stem_en = phrase.en.split("{")[0].strip()
        assert stem_en in joined_en, f"dead phrase: no worked solution says {phrase.en!r}"
        stem_es = phrase.es.split("{")[0].strip()
        for formula_id, line in spanish:
            if stem_en in line:
                leaks.append(f"{formula_id}: {stem_en!r} still in {line!r}")
        assert any(stem_es in line for _f, line in spanish), (
            f"no ES worked solution ever says {phrase.es!r}"
        )
    assert not leaks, "English prose in an ES worked solution:\n  " + "\n  ".join(leaks)


#: Units that are the same text in both books by their nature, not by neglect: a ticker and a
#: symbol. Anything else is a word, and a word has to be declared in two languages.
LOCALE_NEUTRAL_UNITS = frozenset({"USDT", "%"})


@pytest.mark.parametrize(("exercise_id", "config"), CALCULATIONS, ids=IDS)
def test_a_unit_that_is_a_word_is_declared_in_both_languages(
    exercise_id: str, config: CalculationConfig
) -> None:
    """The unit prints beside every option and in the answer key — the most-read text in the layer.

    It was a single untranslated string until 2026-08-22, so an ES option column read `0,0800 units`
    directly under a worked solution ending `= 0,08 unidades`.
    """
    if config.unit is None:
        return
    if isinstance(config.unit, str):
        assert config.unit in LOCALE_NEUTRAL_UNITS, (
            f"{exercise_id}: unit {config.unit!r} is a bare string, so both books print it "
            f"identically — give it {{en: …, es: …}} or add it to LOCALE_NEUTRAL_UNITS"
        )
        return
    en, es = config.unit.get("en"), config.unit.get("es")
    assert en and es, f"{exercise_id}: unit is missing a language"
    assert en != es, (
        f"{exercise_id}: unit is {en!r} in both languages — declare it as a bare string instead"
    )
    for locale in LOCALES:
        payload = get_generator(ExerciseType.CALCULATION).generate(config, 1, locale).payload
        assert payload["unit"] == config.unit.get(locale), f"{exercise_id} [{locale}]"


def test_every_named_mistake_can_be_stated_in_spanish() -> None:
    """The diagnosis appended to a wrong answer is prose too, and it falls back to English silently.

    m23-ex-5's `charge the taker fee on one fill instead of both` was the one label with no entry —
    a near-twin of net_pnl's, which is exactly how it went unnoticed.
    """
    emitted: set[str] = set()
    for _exercise_id, config in CALCULATIONS:
        for params in (_sample_params(config, seed) for seed in SEEDS):
            _e, _o, _c, diag = _options_for_params(config, params, order_seed=7)
            emitted.update(m for m in diag.values() if m)
    missing = sorted(emitted - set(MISTAKE_TRANSLATIONS_ES))
    assert not missing, f"named mistakes with no ES translation: {missing}"


def test_percent_args_name_real_formula_arguments() -> None:
    """A rate arg that is not an arg at all would format nothing and fail silently."""
    for name, formula in FORMULAS.items():
        unknown = set(formula.percent_args) - set(formula.arg_names)
        assert not unknown, f"{name}: percent_args names non-arguments {sorted(unknown)}"


def test_win_rate_is_deliberately_not_a_percentage() -> None:
    """m25 defines its win rate AS a fraction in the prompt ("the fraction of trades"), and the
    formula's own vocabulary is `win% x avg win`. Recorded so a later sweep re-decides it rather
    than assuming it was missed."""
    assert "win_rate" not in FORMULAS["expectancy"].percent_args
