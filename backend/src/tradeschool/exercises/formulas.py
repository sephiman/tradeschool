# SPDX-License-Identifier: AGPL-3.0-only
"""Named financial formulas — **`Decimal` end to end** (house rule §8). Each formula both computes
its result and explains itself with the scenario's real numbers, so the step-by-step solution is
always correct and consistent with the value being graded. Float is never used here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal

FormulaParams = Mapping[str, object]


def _dec(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _fmt(value: Decimal) -> str:
    """Compact decimal string: no scientific notation, trailing zeros trimmed."""
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


# A distractor is a (diagnosis, value) pair: a value a learner reaches by a specific, named mistake.
# The multiple-choice generator instantiates these from the same params, so every wrong option maps
# to a real error the worked solution can name (§ review D.8b).
Distractor = tuple[str, Decimal]


@dataclass(frozen=True)
class Formula:
    id: str
    arg_names: tuple[str, ...]
    compute: Callable[[FormulaParams], Decimal]
    explain: Callable[[FormulaParams, Decimal], list[str]]
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


def _liquidation_explain(p: FormulaParams, result: Decimal) -> list[str]:
    entry = _dec(p["entry"])
    leverage = _dec(p["leverage"])
    mmr = _dec(p["mmr"])
    side = str(p["side"])
    imr = Decimal(1) / leverage
    factor = (Decimal(1) - imr + mmr) if side == "long" else (Decimal(1) + imr - mmr)
    sign = "−" if side == "long" else "+"
    op = "+" if side == "long" else "−"
    return [
        f"liq = entry × (1 {sign} 1/leverage {op} mmr)   [{side}]",
        f"    = {_fmt(entry)} × (1 {sign} 1/{_fmt(leverage)} {op} {_fmt(mmr)})",
        f"    = {_fmt(entry)} × {_fmt(factor)}",
        f"    = {_fmt(result)}",
    ]


# --- Funding payment (m04): a single funding transfer on a linear perp -----------------------------
# Convention: when the funding rate is positive, longs pay shorts. Result is what the trader PAYS
# (positive = you pay out; negative = you receive).


def _funding_compute(p: FormulaParams) -> Decimal:
    notional = _dec(p["notional"])
    rate = _dec(p["rate"])
    sign = Decimal(1) if str(p["side"]) == "long" else Decimal(-1)
    return notional * rate * sign


def _funding_explain(p: FormulaParams, result: Decimal) -> list[str]:
    notional = _dec(p["notional"])
    rate = _dec(p["rate"])
    side = str(p["side"])
    who = "you pay" if result > 0 else ("you receive" if result < 0 else "no transfer")
    return [
        f"funding = notional × rate × (+1 long / −1 short)   [{side}]",
        f"        = {_fmt(notional)} × {_fmt(rate)} × {'+1' if side == 'long' else '−1'}",
        f"        = {_fmt(result)}   ({who})",
    ]


# --- Initial margin (m05): isolated margin to open a position -------------------------------------


def _initial_margin_compute(p: FormulaParams) -> Decimal:
    entry = _dec(p["entry"])
    quantity = _dec(p["quantity"])
    leverage = _dec(p["leverage"])
    return entry * quantity / leverage


def _initial_margin_explain(p: FormulaParams, result: Decimal) -> list[str]:
    entry = _dec(p["entry"])
    quantity = _dec(p["quantity"])
    leverage = _dec(p["leverage"])
    notional = entry * quantity
    return [
        "margin = (entry × quantity) / leverage",
        f"       = ({_fmt(entry)} × {_fmt(quantity)}) / {_fmt(leverage)}",
        f"       = {_fmt(notional)} / {_fmt(leverage)}",
        f"       = {_fmt(result)}",
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


def _net_pnl_explain(p: FormulaParams, result: Decimal) -> list[str]:
    entry = _dec(p["entry"])
    exit_ = _dec(p["exit"])
    quantity = _dec(p["quantity"])
    fee_rate = _dec(p["fee_rate"])
    side = str(p["side"])
    direction = Decimal(1) if side == "long" else Decimal(-1)
    gross = quantity * (exit_ - entry) * direction
    fees = fee_rate * quantity * (entry + exit_)
    move = f"{_fmt(exit_)} − {_fmt(entry)}" if side == "long" else f"{_fmt(entry)} − {_fmt(exit_)}"
    return [
        f"gross = quantity × (price move)   [{side}]",
        f"      = {_fmt(quantity)} × ({move}) = {_fmt(gross)}",
        f"fees  = fee_rate × quantity × (entry + exit) = {_fmt(fee_rate)} × {_fmt(quantity)} "
        f"× {_fmt(entry + exit_)} = {_fmt(fees)}",
        f"net   = gross − fees = {_fmt(gross)} − {_fmt(fees)} = {_fmt(result)}",
    ]


# --- Market cap & fully-diluted value (m18) -------------------------------------------------------
# Supplies are expressed in MILLIONS of tokens, so the result is in millions of USD.


def _market_cap_compute(p: FormulaParams) -> Decimal:
    return _dec(p["price"]) * _dec(p["circulating"])


def _market_cap_explain(p: FormulaParams, result: Decimal) -> list[str]:
    price, circ = _dec(p["price"]), _dec(p["circulating"])
    return [
        "market cap = price × circulating supply",
        f"           = {_fmt(price)} × {_fmt(circ)} million",
        f"           = {_fmt(result)} million USD",
    ]


def _fdv_compute(p: FormulaParams) -> Decimal:
    return _dec(p["price"]) * _dec(p["max_supply"])


def _fdv_explain(p: FormulaParams, result: Decimal) -> list[str]:
    price, mx = _dec(p["price"]), _dec(p["max_supply"])
    return [
        "FDV = price × max (fully diluted) supply",
        f"    = {_fmt(price)} × {_fmt(mx)} million",
        f"    = {_fmt(result)} million USD   (what the cap would be if EVERY token were circulating)",
    ]


# --- Position size from risk (m19): the risk-first sizing formula ---------------------------------


def _position_size_compute(p: FormulaParams) -> Decimal:
    equity = _dec(p["equity"])
    risk_pct = _dec(p["risk_pct"])
    stop_distance = _dec(p["stop_distance"])
    return equity * risk_pct / stop_distance


def _position_size_explain(p: FormulaParams, result: Decimal) -> list[str]:
    equity = _dec(p["equity"])
    risk_pct = _dec(p["risk_pct"])
    stop_distance = _dec(p["stop_distance"])
    risk_amount = equity * risk_pct
    return [
        "risk amount = equity × risk %",
        f"            = {_fmt(equity)} × {_fmt(risk_pct)} = {_fmt(risk_amount)}",
        "quantity = risk amount / (distance from entry to stop)",
        f"         = {_fmt(risk_amount)} / {_fmt(stop_distance)}",
        f"         = {_fmt(result)} units",
    ]


# --- Expectancy (m22): expected value per trade ---------------------------------------------------


def _expectancy_compute(p: FormulaParams) -> Decimal:
    win_rate = _dec(p["win_rate"])
    avg_win = _dec(p["avg_win"])
    avg_loss = _dec(p["avg_loss"])
    return win_rate * avg_win - (Decimal(1) - win_rate) * avg_loss


def _expectancy_explain(p: FormulaParams, result: Decimal) -> list[str]:
    win_rate = _dec(p["win_rate"])
    avg_win = _dec(p["avg_win"])
    avg_loss = _dec(p["avg_loss"])
    loss_rate = Decimal(1) - win_rate
    return [
        "expectancy = win% × avg win − loss% × avg loss   (loss% = 1 − win%)",
        f"           = {_fmt(win_rate)} × {_fmt(avg_win)} − {_fmt(loss_rate)} × {_fmt(avg_loss)}",
        f"           = {_fmt(win_rate * avg_win)} − {_fmt(loss_rate * avg_loss)}",
        f"           = {_fmt(result)} per trade",
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
    notional = _dec(p["entry"]) * _dec(p["quantity"])
    lev = _dec(p["leverage"])
    return [
        ("forget to divide by leverage (use the full notional)", notional),
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
    risk_amount = _dec(p["equity"]) * _dec(p["risk_pct"])
    stop = _dec(p["stop_distance"])
    return [
        ("double the risk percentage", 2 * risk_amount / stop),
        ("halve the stop distance", risk_amount / (stop / 2)),
        ("assume 1% risk instead of the given percentage", _dec(p["equity"]) * Decimal("0.01") / stop),
    ]


def _expectancy_distractors(p: FormulaParams, result: Decimal) -> list[Distractor]:
    p_win, w, loss = _dec(p["win_rate"]), _dec(p["avg_win"]), _dec(p["avg_loss"])
    return [
        ("use the win rate for losses too (forget 1 - win%)", p_win * w - p_win * loss),
        ("add the losing side instead of subtracting", p_win * w + (Decimal(1) - p_win) * loss),
        ("ignore the losing trades entirely", p_win * w),
    ]


# --- Trading-style net result (m20): the same gross move costs differently per style --------------
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


def _style_net_explain(p: FormulaParams, result: Decimal) -> list[str]:
    notional, gp, fr, style = _dec(p["notional"]), _dec(p["gross_pct"]), _dec(p["fee_rate"]), str(p["style"])
    fundr, fi, rt = _dec(p["funding_rate"]), _dec(p["funding_intervals"]), _dec(p["round_trips"])
    gross = notional * gp
    base_fee = fr * notional * 2
    cost = _style_cost(style, base_fee, notional, fundr, fi, rt)
    if style == "scalper":
        cost_line = f"cost = fee×notional×2 × round-trips = {_fmt(base_fee)} × {_fmt(rt)} = {_fmt(cost)}"
    elif style == "swing":
        fund = fundr * notional * fi
        cost_line = (
            f"cost = one round-trip {_fmt(base_fee)} + funding "
            f"{_fmt(fundr)}×{_fmt(notional)}×{_fmt(fi)}={_fmt(fund)} = {_fmt(cost)}"
        )
    else:
        cost_line = f"cost = one round-trip fee = fee×notional×2 = {_fmt(cost)}"
    return [
        f"gross = notional × move = {_fmt(notional)} × {_fmt(gp)} = {_fmt(gross)}   [{style}]",
        cost_line,
        f"net = gross − cost = {_fmt(gross)} − {_fmt(cost)} = {_fmt(result)}",
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
        compute=_liquidation_compute,
        explain=_liquidation_explain,
        distractors=_liquidation_distractors,
    ),
    "funding_payment": Formula(
        id="funding_payment",
        arg_names=("notional", "rate", "side"),
        compute=_funding_compute,
        explain=_funding_explain,
        distractors=_funding_distractors,
    ),
    "initial_margin": Formula(
        id="initial_margin",
        arg_names=("entry", "quantity", "leverage"),
        compute=_initial_margin_compute,
        explain=_initial_margin_explain,
        distractors=_initial_margin_distractors,
    ),
    "net_pnl": Formula(
        id="net_pnl",
        arg_names=("entry", "exit", "quantity", "side", "fee_rate"),
        compute=_net_pnl_compute,
        explain=_net_pnl_explain,
        distractors=_net_pnl_distractors,
    ),
    "market_cap": Formula(
        id="market_cap",
        arg_names=("price", "circulating"),
        compute=_market_cap_compute,
        explain=_market_cap_explain,
        distractors=_market_cap_distractors,
    ),
    "fdv": Formula(
        id="fdv",
        arg_names=("price", "max_supply"),
        compute=_fdv_compute,
        explain=_fdv_explain,
        distractors=_fdv_distractors,
    ),
    "position_size_from_risk": Formula(
        id="position_size_from_risk",
        arg_names=("equity", "risk_pct", "stop_distance"),
        compute=_position_size_compute,
        explain=_position_size_explain,
        distractors=_position_size_distractors,
    ),
    "expectancy": Formula(
        id="expectancy",
        arg_names=("win_rate", "avg_win", "avg_loss"),
        compute=_expectancy_compute,
        explain=_expectancy_explain,
        distractors=_expectancy_distractors,
    ),
    "style_net_result": Formula(
        id="style_net_result",
        arg_names=("notional", "gross_pct", "style", "fee_rate", "round_trips",
                   "funding_rate", "funding_intervals"),
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
