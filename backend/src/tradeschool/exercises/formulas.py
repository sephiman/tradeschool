# SPDX-License-Identifier: AGPL-3.0-only
"""Named financial formulas — **`Decimal` end to end** (house rule §8), never float.

Each formula computes its result and explains itself with the scenario's real numbers, so the
step-by-step solution cannot drift from the graded value.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from tradeschool.content.numbers import format_number, format_percent
from tradeschool.content.schema import LocalizedText

FormulaParams = Mapping[str, object]


# --- the prose a worked solution hangs off its formula --------------------------------------------
# A step is a formula skeleton plus prose: a unit on the result, a verdict in parentheses, sometimes
# a closing sentence that says what the number does NOT tell you. The numbers were localized on
# 2026-08-22; the prose followed, because an ES reader was still being told `(you pay)` and `units`.
#
# What stays English, deliberately: the skeleton's IDENTIFIERS (`funding`, `notional`, `gross`,
# `taker buy volume`) and the glosses inside an expression (`(price move)`). Those are the formula
# reminder's vocabulary — and it already renders them in Spanish ("bruto = cantidad por var.
# precio"), so aligning the two is one decision about identifiers, not a phrase-by-phrase sweep.
# Half-translating an expression line would read worse than either end of that choice.
#
# `LocalizedText` rather than an English-keyed dict: a phrase cannot be constructed without both
# languages, so the failure mode of the sibling `MISTAKE_TRANSLATIONS_ES` table — an entry silently
# missing and falling back to English — is unrepresentable here.

_PAYS = LocalizedText(en="you pay", es="pagas")
_RECEIVES = LocalizedText(en="you receive", es="recibes")
_NO_TRANSFER = LocalizedText(en="no transfer", es="sin transferencia")
_MILLION = LocalizedText(en="million", es="millones")
_MILLION_USD = LocalizedText(en="million USD", es="millones de USD")
_FDV_ASIDE = LocalizedText(
    en="what the cap would be if EVERY token were circulating",
    es="lo que sería el market cap si TODOS los tokens circularan",
)
_UNITS = LocalizedText(en="units", es="unidades")
_PER_TRADE = LocalizedText(en="per trade", es="por operación")
_NET_BUYING = LocalizedText(en="net aggressive BUYING", es="COMPRA agresiva neta")
_NET_SELLING = LocalizedText(en="net aggressive SELLING", es="VENTA agresiva neta")
_BALANCED_FLOW = LocalizedText(en="balanced flow", es="flujo equilibrado")
_TOTAL_VOLUME = LocalizedText(
    en="Total volume for the period was {total} — that is a different figure, and it is the one "
    "that tells you nothing about direction.",
    es="El volumen total del periodo fue {total}: esa es otra cifra distinta, y es la que no te "
    "dice nada sobre la dirección.",
)
_ABSOLUTE_GAP = LocalizedText(en="the absolute gap is {gap}", es="el hueco absoluto es {gap}")
_PREMIUM_ASIDE = LocalizedText(
    en="The percentage is the figure worth quoting: an absolute gap means nothing until you know "
    "what price it is a gap ON.",
    es="El porcentaje es la cifra que merece la pena citar: un hueco absoluto no significa nada "
    "hasta que sabes SOBRE qué precio es el hueco.",
)

#: Every phrase above, so a guard can enumerate them rather than restate them (see
#: `tests/test_exercise_numbers.py::test_no_worked_solution_prose_reaches_an_es_reader_in_english`).
LOCALIZED_PROSE: tuple[LocalizedText, ...] = (
    _PAYS, _RECEIVES, _NO_TRANSFER, _MILLION, _MILLION_USD, _FDV_ASIDE, _UNITS, _PER_TRADE,
    _NET_BUYING, _NET_SELLING, _BALANCED_FLOW, _TOTAL_VOLUME, _ABSOLUTE_GAP, _PREMIUM_ASIDE,
)


def _dec(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _num(locale: str) -> Callable[[Decimal], str]:
    """This locale's compact decimal: no scientific notation, trailing zeros trimmed, grouped
    thousands and the right decimal mark. Bound once per `explain` call, as `fmt`."""

    def render(value: Decimal) -> str:
        text = format(value.normalize(), "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return format_number(Decimal(text or "0"), locale)

    return render


def _as_fraction(label: str, rate: Decimal, locale: str) -> str:
    """The %-to-fraction step, stated once at the head of a worked solution.

    The prompt states a rate the way an exchange does (`0.05%`); every line below multiplies by the
    fraction (`0.0005`). Converting in the reader's head is exactly the mistake this line prevents,
    and doing it on paper is the skill the exercise is really teaching.
    """
    return f"{label} = {format_percent(rate, locale)} = {_num(locale)(rate)}"


# A distractor is a (diagnosis, value) pair: a value a learner reaches by a specific, named mistake.
# The multiple-choice generator instantiates these from the same params, so every wrong option maps
# to a real error the worked solution can name (§ review D.8b).
Distractor = tuple[str, Decimal]


@dataclass(frozen=True)
class Formula:
    id: str
    arg_names: tuple[str, ...]
    #: Args that ARE rates: held as a fraction, stated to the learner as a percentage the way an
    #: exchange shows it. The formula owns this, not the content — `rate` is a rate wherever it is
    #: sampled — so a prompt cannot drift from the units its own arithmetic uses.
    percent_args: tuple[str, ...]
    compute: Callable[[FormulaParams], Decimal]
    #: (params, result, locale) -> the worked solution, with this locale's numbers in it.
    explain: Callable[[FormulaParams, Decimal, str], list[str]]
    # (params, correct_result) -> candidate wrong answers, each tagged with the mistake that yields it
    distractors: Callable[[FormulaParams, Decimal], list[Distractor]]


# --- Liquidation price (linear/USDT-margined perpetual, isolated, fees ignored) ---


def _liquidation_compute(p: FormulaParams) -> Decimal:
    entry = _dec(p["entry"])
    leverage = _dec(p["leverage"])
    mmr = _dec(p["mmr"])
    side = str(p["side"])
    imr = Decimal(1) / leverage
    factor = (Decimal(1) - imr + mmr) if side == "long" else (Decimal(1) + imr - mmr)
    return entry * factor


def _liquidation_explain(p: FormulaParams, result: Decimal, locale: str) -> list[str]:
    fmt = _num(locale)
    entry = _dec(p["entry"])
    leverage = _dec(p["leverage"])
    mmr = _dec(p["mmr"])
    side = str(p["side"])
    imr = Decimal(1) / leverage
    factor = (Decimal(1) - imr + mmr) if side == "long" else (Decimal(1) + imr - mmr)
    sign = "−" if side == "long" else "+"
    op = "+" if side == "long" else "−"
    return [
        _as_fraction("mmr", mmr, locale),
        f"liq = entry × (1 {sign} 1/leverage {op} mmr)   [{side}]",
        f"    = {fmt(entry)} × (1 {sign} 1/{fmt(leverage)} {op} {fmt(mmr)})",
        f"    = {fmt(entry)} × {fmt(factor)}",
        f"    = {fmt(result)}",
    ]


# --- Funding payment (m04): a single funding transfer on a linear perp -----------------------------
# Convention: when the funding rate is positive, longs pay shorts. Result is what the trader PAYS
# (positive = you pay out; negative = you receive).


def _funding_compute(p: FormulaParams) -> Decimal:
    notional = _dec(p["notional"])
    rate = _dec(p["rate"])
    sign = Decimal(1) if str(p["side"]) == "long" else Decimal(-1)
    return notional * rate * sign


def _funding_explain(p: FormulaParams, result: Decimal, locale: str) -> list[str]:
    fmt = _num(locale)
    notional = _dec(p["notional"])
    rate = _dec(p["rate"])
    side = str(p["side"])
    verdict = _PAYS if result > 0 else (_RECEIVES if result < 0 else _NO_TRANSFER)
    who = verdict.get(locale)
    return [
        _as_fraction("rate", rate, locale),
        f"funding = notional × rate × (+1 long / −1 short)   [{side}]",
        f"        = {fmt(notional)} × {fmt(rate)} × {'+1' if side == 'long' else '−1'}",
        f"        = {fmt(result)}   ({who})",
    ]


# --- Initial margin (m05): isolated margin to open a position -------------------------------------


def _initial_margin_compute(p: FormulaParams) -> Decimal:
    entry = _dec(p["entry"])
    quantity = _dec(p["quantity"])
    leverage = _dec(p["leverage"])
    return entry * quantity / leverage


def _initial_margin_explain(p: FormulaParams, result: Decimal, locale: str) -> list[str]:
    fmt = _num(locale)
    entry = _dec(p["entry"])
    quantity = _dec(p["quantity"])
    leverage = _dec(p["leverage"])
    notional = entry * quantity
    return [
        "margin = (entry × quantity) / leverage",
        f"       = ({fmt(entry)} × {fmt(quantity)}) / {fmt(leverage)}",
        f"       = {fmt(notional)} / {fmt(leverage)}",
        f"       = {fmt(result)}",
    ]


# --- Net PnL (m07): realized PnL on a closed perp trade, net of taker fees -------------------------


def _net_pnl_compute(p: FormulaParams) -> Decimal:
    entry = _dec(p["entry"])
    exit_ = _dec(p["exit"])
    quantity = _dec(p["quantity"])
    fee_rate = _dec(p["fee_rate"])
    direction = Decimal(1) if str(p["side"]) == "long" else Decimal(-1)
    gross = quantity * (exit_ - entry) * direction
    fees = fee_rate * quantity * (entry + exit_)  # taker fee on both the open and the close fill
    return gross - fees


def _net_pnl_explain(p: FormulaParams, result: Decimal, locale: str) -> list[str]:
    fmt = _num(locale)
    entry = _dec(p["entry"])
    exit_ = _dec(p["exit"])
    quantity = _dec(p["quantity"])
    fee_rate = _dec(p["fee_rate"])
    side = str(p["side"])
    direction = Decimal(1) if side == "long" else Decimal(-1)
    gross = quantity * (exit_ - entry) * direction
    fees = fee_rate * quantity * (entry + exit_)
    move = f"{fmt(exit_)} − {fmt(entry)}" if side == "long" else f"{fmt(entry)} − {fmt(exit_)}"
    return [
        _as_fraction("fee_rate", fee_rate, locale),
        f"gross = quantity × (price move)   [{side}]",
        f"      = {fmt(quantity)} × ({move}) = {fmt(gross)}",
        f"fees  = fee_rate × quantity × (entry + exit) = {fmt(fee_rate)} × {fmt(quantity)} "
        f"× {fmt(entry + exit_)} = {fmt(fees)}",
        f"net   = gross − fees = {fmt(gross)} − {fmt(fees)} = {fmt(result)}",
    ]


# --- Market cap & fully-diluted value (m20) -------------------------------------------------------
# Supplies are expressed in MILLIONS of tokens, so the result is in millions of USD.


def _market_cap_compute(p: FormulaParams) -> Decimal:
    return _dec(p["price"]) * _dec(p["circulating"])


def _market_cap_explain(p: FormulaParams, result: Decimal, locale: str) -> list[str]:
    fmt = _num(locale)
    price, circ = _dec(p["price"]), _dec(p["circulating"])
    return [
        "market cap = price × circulating supply",
        f"           = {fmt(price)} × {fmt(circ)} {_MILLION.get(locale)}",
        f"           = {fmt(result)} {_MILLION_USD.get(locale)}",
    ]


def _fdv_compute(p: FormulaParams) -> Decimal:
    return _dec(p["price"]) * _dec(p["max_supply"])


def _fdv_explain(p: FormulaParams, result: Decimal, locale: str) -> list[str]:
    fmt = _num(locale)
    price, mx = _dec(p["price"]), _dec(p["max_supply"])
    return [
        "FDV = price × max (fully diluted) supply",
        f"    = {fmt(price)} × {fmt(mx)} {_MILLION.get(locale)}",
        f"    = {fmt(result)} {_MILLION_USD.get(locale)}   ({_FDV_ASIDE.get(locale)})",
    ]


# --- Position size from risk (m22): the risk-first sizing formula ---------------------------------


def _position_size_compute(p: FormulaParams) -> Decimal:
    equity = _dec(p["equity"])
    risk_pct = _dec(p["risk_pct"])
    stop_distance = _dec(p["stop_distance"])
    return equity * risk_pct / stop_distance


def _position_size_explain(p: FormulaParams, result: Decimal, locale: str) -> list[str]:
    fmt = _num(locale)
    equity = _dec(p["equity"])
    risk_pct = _dec(p["risk_pct"])
    stop_distance = _dec(p["stop_distance"])
    risk_amount = equity * risk_pct
    return [
        _as_fraction("risk %", risk_pct, locale),
        "risk amount = equity × risk %",
        f"            = {fmt(equity)} × {fmt(risk_pct)} = {fmt(risk_amount)}",
        "quantity = risk amount / (distance from entry to stop)",
        f"         = {fmt(risk_amount)} / {fmt(stop_distance)}",
        f"         = {fmt(result)} {_UNITS.get(locale)}",
    ]


# --- Expectancy (m25): expected value per trade ---------------------------------------------------


def _expectancy_compute(p: FormulaParams) -> Decimal:
    win_rate = _dec(p["win_rate"])
    avg_win = _dec(p["avg_win"])
    avg_loss = _dec(p["avg_loss"])
    return win_rate * avg_win - (Decimal(1) - win_rate) * avg_loss


def _expectancy_explain(p: FormulaParams, result: Decimal, locale: str) -> list[str]:
    fmt = _num(locale)
    win_rate = _dec(p["win_rate"])
    avg_win = _dec(p["avg_win"])
    avg_loss = _dec(p["avg_loss"])
    loss_rate = Decimal(1) - win_rate
    return [
        "expectancy = win% × avg win − loss% × avg loss   (loss% = 1 − win%)",
        f"           = {fmt(win_rate)} × {fmt(avg_win)} − {fmt(loss_rate)} × {fmt(avg_loss)}",
        f"           = {fmt(win_rate * avg_win)} − {fmt(loss_rate * avg_loss)}",
        f"           = {fmt(result)} {_PER_TRADE.get(locale)}",
    ]


# --- Net delta (m29): the net aggressive flow of a period ----------------------------------------
# Taker buy volume minus taker sell volume. Positive = buyers were the aggressors on balance.
# Note this is NOT total volume: the two sides are subtracted, not added.


def _net_delta_compute(p: FormulaParams) -> Decimal:
    return _dec(p["taker_buy"]) - _dec(p["taker_sell"])


def _net_delta_explain(p: FormulaParams, result: Decimal, locale: str) -> list[str]:
    fmt = _num(locale)
    buy, sell = _dec(p["taker_buy"]), _dec(p["taker_sell"])
    lean = _NET_BUYING if result > 0 else (_NET_SELLING if result < 0 else _BALANCED_FLOW)
    return [
        "delta = taker buy volume − taker sell volume",
        f"      = {fmt(buy)} − {fmt(sell)}",
        f"      = {fmt(result)}   ({lean.get(locale)})",
        _TOTAL_VOLUME.get(locale).format(total=fmt(buy + sell)),
    ]


# --- Premium between venues (m32): the same coin priced differently on two exchanges --------------
# Expressed as a PERCENTAGE of the reference venue's price, which is what makes premiums comparable
# across coins and dates. The absolute gap is the intermediate step (see `explain`).


def _venue_premium_compute(p: FormulaParams) -> Decimal:
    ref, other = _dec(p["price_a"]), _dec(p["price_b"])
    return (other - ref) / ref * Decimal(100)


def _venue_premium_explain(p: FormulaParams, result: Decimal, locale: str) -> list[str]:
    fmt = _num(locale)
    ref, other = _dec(p["price_a"]), _dec(p["price_b"])
    gap = other - ref
    return [
        "premium % = (other venue − reference venue) / reference venue × 100",
        f"          = ({fmt(other)} − {fmt(ref)}) / {fmt(ref)} × 100",
        f"          = {fmt(gap)} / {fmt(ref)} × 100        "
        f"[{_ABSOLUTE_GAP.get(locale).format(gap=fmt(gap))}]",
        # The one hand-written percent left in the layer, space and all: m32-ex-1 carries
        # `unit: "%"`, which both surfaces render as `value + " %"` beside these very options.
        f"          = {fmt(result.quantize(Decimal('0.001')))} %",
        _PREMIUM_ASIDE.get(locale),
    ]


# --- Distractors: each is a value reached by a specific, named mistake (multiple-choice, §D.8b) ---


def _liquidation_distractors(p: FormulaParams, result: Decimal) -> list[Distractor]:
    entry, lev, mmr = _dec(p["entry"]), _dec(p["leverage"]), _dec(p["mmr"])
    imr = Decimal(1) / lev
    if str(p["side"]) == "long":  # all below entry, so not eliminable by "a long liquidates below entry"
        return [
            ("forget the maintenance-margin term", entry * (Decimal(1) - imr)),
            ("subtract mmr as well (wrong sign)", entry * (Decimal(1) - imr - mmr)),
            ("double the initial-margin cushion", entry * (Decimal(1) - 2 * imr + mmr)),
        ]
    return [  # all above entry
        ("forget the maintenance-margin term", entry * (Decimal(1) + imr)),
        ("add mmr as well (wrong sign)", entry * (Decimal(1) + imr + mmr)),
        ("double the initial-margin cushion", entry * (Decimal(1) + 2 * imr - mmr)),
    ]


def _funding_distractors(p: FormulaParams, result: Decimal) -> list[Distractor]:
    return [
        ("use the wrong side (flip the sign)", -result),
        ("count two funding intervals", result * 2),
        ("count only half an interval", result / 2),
    ]


def _initial_margin_distractors(p: FormulaParams, result: Decimal) -> list[Distractor]:
    # 2026-08-22 (test_mental_cost): the old "forget to divide by leverage" candidate is lev-times the
    # answer, so the same-order-of-magnitude filter dropped it on most draws above ~8x and a
    # generic filler took its slot. Every candidate here survives that filter for every draw.
    notional = _dec(p["entry"]) * _dec(p["quantity"])
    lev = _dec(p["leverage"])
    return [
        ("compute the margin for only half the position", notional / lev / 2),
        ("divide by leverage minus one", notional / (lev - 1) if lev > 1 else notional * 2),
        ("divide by leverage plus one", notional / (lev + 1)),
    ]


def _net_pnl_distractors(p: FormulaParams, result: Decimal) -> list[Distractor]:
    entry, exit_, qty, fr = _dec(p["entry"]), _dec(p["exit"]), _dec(p["quantity"]), _dec(p["fee_rate"])
    direction = Decimal(1) if str(p["side"]) == "long" else Decimal(-1)
    gross = qty * (exit_ - entry) * direction
    fees = fr * qty * (entry + exit_)
    return [
        ("take the gross move only (forget fees)", gross),
        ("charge the fee on one fill instead of both", gross - fees / 2),
        ("read the price move the wrong way round", -gross - fees),
    ]


def _market_cap_distractors(p: FormulaParams, result: Decimal) -> list[Distractor]:
    return [
        ("misread the circulating supply (~1.5x)", result * Decimal("1.5")),
        ("misread the circulating supply (~0.6x)", result * Decimal("0.6")),
        ("double-count the supply", result * 2),
    ]


def _fdv_distractors(p: FormulaParams, result: Decimal) -> list[Distractor]:
    return [
        ("use a supply figure ~0.5x too small", result * Decimal("0.5")),
        ("use a supply figure ~1.4x too large", result * Decimal("1.4")),
        ("slip a decimal on the price (~0.9x)", result * Decimal("0.9")),
    ]


def _position_size_distractors(p: FormulaParams, result: Decimal) -> list[Distractor]:
    # 2026-08-22 (test_mental_cost): the old trio was structurally broken — "halve the stop
    # distance" equals "double the risk percentage" for EVERY draw, and "assume 1%" equals the
    # answer whenever the given risk is 1%, so a generic filler shipped on every instance. These
    # three are pairwise distinct and inside the magnitude filter for all params.
    risk_amount = _dec(p["equity"]) * _dec(p["risk_pct"])
    stop = _dec(p["stop_distance"])
    return [
        ("double the risk percentage", 2 * risk_amount / stop),
        ("halve the risk percentage", risk_amount / 2 / stop),
        ("slip a decimal and size ten times too small", risk_amount / stop / 10),
    ]


def _expectancy_distractors(p: FormulaParams, result: Decimal) -> list[Distractor]:
    p_win, w, loss = _dec(p["win_rate"]), _dec(p["avg_win"]), _dec(p["avg_loss"])
    return [
        ("use the win rate for losses too (forget 1 - win%)", p_win * w - p_win * loss),
        ("add the losing side instead of subtracting", p_win * w + (Decimal(1) - p_win) * loss),
        ("ignore the losing trades entirely", p_win * w),
    ]


# --- Trading-style net result (m23): the same gross move costs differently per style --------------
# Fees scale with the NUMBER of trades (they hit the scalper); funding scales with TIME HELD (it taxes
# the swing trader). A day trade is one round-trip with no overnight funding.


def _style_cost(
    style: str, per_rt_fee: Decimal, notional: Decimal, fundr: Decimal, fi: Decimal, rt: Decimal
) -> Decimal:
    if style == "scalper":
        return per_rt_fee * rt  # many round-trips, each paying the taker fee on both fills
    if style == "swing":
        return per_rt_fee + fundr * notional * fi  # one round-trip + funding over the hold
    return per_rt_fee  # day: one round-trip, no funding


def _style_net_compute(p: FormulaParams) -> Decimal:
    notional, gp, fr = _dec(p["notional"]), _dec(p["gross_pct"]), _dec(p["fee_rate"])
    gross = notional * gp
    base_fee = fr * notional * 2  # one round-trip = taker fee on the open and the close fill
    cost = _style_cost(str(p["style"]), base_fee, notional, _dec(p["funding_rate"]),
                       _dec(p["funding_intervals"]), _dec(p["round_trips"]))
    return gross - cost


def _style_net_explain(p: FormulaParams, result: Decimal, locale: str) -> list[str]:
    fmt = _num(locale)
    notional, gp, fr, style = _dec(p["notional"]), _dec(p["gross_pct"]), _dec(p["fee_rate"]), str(p["style"])
    fundr, fi, rt = _dec(p["funding_rate"]), _dec(p["funding_intervals"]), _dec(p["round_trips"])
    gross = notional * gp
    base_fee = fr * notional * 2
    cost = _style_cost(style, base_fee, notional, fundr, fi, rt)
    if style == "scalper":
        cost_line = f"cost = fee×notional×2 × round-trips = {fmt(base_fee)} × {fmt(rt)} = {fmt(cost)}"
    elif style == "swing":
        fund = fundr * notional * fi
        cost_line = (
            f"cost = one round-trip {fmt(base_fee)} + funding "
            f"{fmt(fundr)}×{fmt(notional)}×{fmt(fi)}={fmt(fund)} = {fmt(cost)}"
        )
    else:
        cost_line = f"cost = one round-trip fee = fee×notional×2 = {fmt(cost)}"
    # Three rates in one prompt, so they convert together rather than three lines deep: funding is
    # named even for the styles that pay none, so the reader sees WHY their cost line has no funding.
    rates = [_as_fraction("move", gp, locale), _as_fraction("fee_rate", fr, locale),
             _as_fraction("funding_rate", fundr, locale)]
    return [
        "   ".join(rates),
        f"gross = notional × move = {fmt(notional)} × {fmt(gp)} = {fmt(gross)}   [{style}]",
        cost_line,
        f"net = gross − cost = {fmt(gross)} − {fmt(cost)} = {fmt(result)}",
    ]


def _net_delta_distractors(p: FormulaParams, result: Decimal) -> list[Distractor]:
    buy, sell = _dec(p["taker_buy"]), _dec(p["taker_sell"])
    return [
        ("add the two sides instead of subtracting them (that is total volume, not net flow)", buy + sell),
        ("read the delta the wrong way round (sell minus buy)", -result),
        ("take only the aggressive buying and ignore the selling against it", buy),
    ]


def _venue_premium_distractors(p: FormulaParams, result: Decimal) -> list[Distractor]:
    ref, other = _dec(p["price_a"]), _dec(p["price_b"])
    gap = other - ref
    return [
        ("divide by the other venue's price instead of the reference venue's", gap / other * Decimal(100)),
        ("read the premium the wrong way round", -result),
        ("forget to convert the fraction into a percentage", gap / ref),
    ]


def _style_net_distractors(p: FormulaParams, result: Decimal) -> list[Distractor]:
    notional, gp, fr, style = _dec(p["notional"]), _dec(p["gross_pct"]), _dec(p["fee_rate"]), str(p["style"])
    fundr, fi, rt = _dec(p["funding_rate"]), _dec(p["funding_intervals"]), _dec(p["round_trips"])
    gross = notional * gp
    base_fee = fr * notional * 2
    half = _style_cost(style, base_fee / 2, notional, fundr, fi, rt)
    return [
        ("ignore trading costs (take the gross move)", gross),
        ("charge the taker fee on one fill instead of both", gross - half),
        ("treat it as a single round-trip with no funding", gross - base_fee),
    ]


FORMULAS: dict[str, Formula] = {
    "liquidation_price": Formula(
        id="liquidation_price",
        arg_names=("entry", "leverage", "mmr", "side"),
        percent_args=("mmr",),
        compute=_liquidation_compute,
        explain=_liquidation_explain,
        distractors=_liquidation_distractors,
    ),
    "funding_payment": Formula(
        id="funding_payment",
        arg_names=("notional", "rate", "side"),
        percent_args=("rate",),
        compute=_funding_compute,
        explain=_funding_explain,
        distractors=_funding_distractors,
    ),
    "initial_margin": Formula(
        id="initial_margin",
        arg_names=("entry", "quantity", "leverage"),
        percent_args=(),
        compute=_initial_margin_compute,
        explain=_initial_margin_explain,
        distractors=_initial_margin_distractors,
    ),
    "net_pnl": Formula(
        id="net_pnl",
        arg_names=("entry", "exit", "quantity", "side", "fee_rate"),
        percent_args=("fee_rate",),
        compute=_net_pnl_compute,
        explain=_net_pnl_explain,
        distractors=_net_pnl_distractors,
    ),
    "market_cap": Formula(
        id="market_cap",
        arg_names=("price", "circulating"),
        percent_args=(),
        compute=_market_cap_compute,
        explain=_market_cap_explain,
        distractors=_market_cap_distractors,
    ),
    "fdv": Formula(
        id="fdv",
        arg_names=("price", "max_supply"),
        percent_args=(),
        compute=_fdv_compute,
        explain=_fdv_explain,
        distractors=_fdv_distractors,
    ),
    "position_size_from_risk": Formula(
        id="position_size_from_risk",
        arg_names=("equity", "risk_pct", "stop_distance"),
        percent_args=("risk_pct",),
        compute=_position_size_compute,
        explain=_position_size_explain,
        distractors=_position_size_distractors,
    ),
    "expectancy": Formula(
        id="expectancy",
        arg_names=("win_rate", "avg_win", "avg_loss"),
        percent_args=(),
        compute=_expectancy_compute,
        explain=_expectancy_explain,
        distractors=_expectancy_distractors,
    ),
    "net_delta": Formula(
        id="net_delta",
        arg_names=("taker_buy", "taker_sell"),
        percent_args=(),
        compute=_net_delta_compute,
        explain=_net_delta_explain,
        distractors=_net_delta_distractors,
    ),
    "venue_premium_pct": Formula(
        id="venue_premium_pct",
        arg_names=("price_a", "price_b"),
        percent_args=(),
        compute=_venue_premium_compute,
        explain=_venue_premium_explain,
        distractors=_venue_premium_distractors,
    ),
    "style_net_result": Formula(
        id="style_net_result",
        arg_names=("notional", "gross_pct", "style", "fee_rate", "round_trips",
                   "funding_rate", "funding_intervals"),
        percent_args=("gross_pct", "fee_rate", "funding_rate"),
        compute=_style_net_compute,
        explain=_style_net_explain,
        distractors=_style_net_distractors,
    ),
}


def get_formula(formula_id: str) -> Formula:
    try:
        return FORMULAS[formula_id]
    except KeyError as exc:
        raise KeyError(f"unknown formula {formula_id!r}") from exc
