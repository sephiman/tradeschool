# SPDX-License-Identifier: AGPL-3.0-only
"""m04-l1's mark-vs-last block says it REUSES m06-l1's worked liquidation numbers — hold it to that.

The 2026-08-02 figure-coupling pass re-anchored m06 onto its figure's 9,500 shelf and left m04's
"reuse the liquidation module's numbers" block quoting values m06 no longer prints. This guard makes
that impossible to repeat: the reused values are DERIVED from fig-m06-liquidation-cascade's coupled
anchors, so a reseed or re-anchor of that figure fails here naming the m04 prose that must follow.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tradeschool.config import get_settings
from tradeschool.content.registry import load_registry
from tradeschool.content.schema import LOCALES

#: The 10x example both lessons walk: cushion 1/leverage, less the 0.5% the exchange keeps.
_LIQ_FACTOR_10X = 1 - 0.10 + 0.005


def _fmt(value: float, locale: str) -> str:
    """The way the prose prints these numbers: thousands separators, decimals only when real."""
    text = f"{value:,.2f}" if value % 1 else f"{int(value):,}"
    return text.translate({44: ".", 46: ","}) if locale == "es" else text


def _flat(markdown: str) -> str:
    return " ".join(markdown.split())  # prose is hard-wrapped


def _reused_values() -> list[float]:
    """Entry (the figure's shelf), the 10x liquidation derived from it, and the cascade wick."""
    coupling = yaml.safe_load(
        (get_settings().content_dir / "figure-coupling.yaml").read_text(encoding="utf-8")
    )
    anchors = {
        a["what"]: a["prose"]
        for a in coupling["figures"]["fig-m06-liquidation-cascade"]["anchors"]
    }
    shelf = float(anchors["level:shelf"])
    wick = float(anchors["low:120"])
    return [shelf, round(shelf * _LIQ_FACTOR_10X, 2), wick]


@pytest.mark.parametrize("locale", LOCALES)
def test_m04_reuse_block_quotes_m06s_current_numbers(locale: str) -> None:
    registry = load_registry(Path(get_settings().content_dir))
    source = _flat(registry.markdown[locale]["m06-l1"])
    reuse = _flat(registry.markdown[locale]["m04-l1"])
    for value in _reused_values():
        printed = _fmt(value, locale)
        # The source of truth really prints it (else the coupling moved and m06 needs its pass first)…
        assert printed in source, f"m06-l1 ({locale}) no longer prints {printed}"
        # …and m04's "reuse the liquidation module's numbers" claim is literally true.
        assert printed in reuse, f"m04-l1 ({locale}) claims to reuse {printed} but does not quote it"
