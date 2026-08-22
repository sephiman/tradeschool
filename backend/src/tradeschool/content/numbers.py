# SPDX-License-Identifier: AGPL-3.0-only
"""How this course prints a number, per locale — the one path prose, exercises, the PDF and the
answer key all go through.

Lesson prose has always been hand-formatted per locale (`70.000` in the ES book, `70,000` in the EN
one). The generated exercise layer printed raw Python instead, so an ES page could carry `70000
USDT` and `0.0005` inside Spanish prose. Everything the learner reads now comes through here.

Two rules, and they are the whole module:

* **Separators swap, digits never do.** ES groups thousands with `.` and marks decimals with `,`;
  EN does the reverse. Nothing else about the number changes, so the two books state the same value.
* **A rate is stated as a percentage, computed as a fraction.** `0.0005` is what the formula
  multiplies by; `0.05%` is what an exchange shows and what the prompt says. `format_percent` is the
  only place that conversion is made for display, and the worked solution walks it back once.

Percent spacing is `0,05%` in ES, not `0,05 %`: that is what the funding lessons this layer quizzes
against print (m04-l1, m19-l1, m21-l1, m22-l1), and matching them on the page beats matching the RAE.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

#: (thousands, decimal) per locale. EN is the fallback for anything unrecognised, as `LocalizedText`.
_SEPARATORS: dict[str, tuple[str, str]] = {"en": (",", "."), "es": (".", ",")}

_PERCENT = Decimal(100)


def _separators(locale: str) -> tuple[str, str]:
    return _SEPARATORS.get(locale, _SEPARATORS["en"])


def _places(value: Decimal) -> int:
    """Decimal places to print: exactly the ones the value carries, so `35.00` keeps its cents."""
    exponent = value.as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def format_number(value: Decimal | int | str, locale: str) -> str:
    """A number as the reader of `locale` sees it: grouped thousands, that locale's decimal mark.

    Trailing zeros are significant and kept — a money answer quantized to `35.00` prints as `35,00`
    in ES, never `35`, because the option list is read as a column of prices.
    """
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    text = f"{number:,.{_places(number)}f}"
    thousands, decimal = _separators(locale)
    # Via placeholders: a straight two-step swap would turn every ES thousands `,` back into a `.`.
    return text.replace(",", "\0").replace(".", decimal).replace("\0", thousands)


def format_percent(fraction: Decimal | int | str, locale: str) -> str:
    """A rate held as a fraction, printed the way an exchange shows it: `0.0005` -> `0.05%`.

    Trailing zeros are dropped here, unlike `format_number`: the fraction's own scale is an artifact
    of how it is stored (`0.0500`), never a claim about precision.
    """
    number = fraction if isinstance(fraction, Decimal) else Decimal(str(fraction))
    percent = (number * _PERCENT).normalize()
    exponent = percent.as_tuple().exponent
    if isinstance(exponent, int) and exponent > 0:  # normalize() renders 100 as 1E+2; undo that
        percent = percent.quantize(Decimal(1))
    return f"{format_number(percent, locale)}%"


def format_param(value: object, locale: str, *, percent: bool = False) -> str:
    """One prompt parameter as the learner reads it.

    Non-numeric parameters (`side`, `style`) pass through untouched — the prompt substitutes words
    and numbers through the same map, and only the numbers are this module's business.
    """
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    if not number.is_finite():
        return str(value)
    return format_percent(number, locale) if percent else format_number(number, locale)
