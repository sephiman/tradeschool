# SPDX-License-Identifier: AGPL-3.0-only
"""Phase-2 pattern injectors (§3.3) for the generic `pattern_chart` generator.

Each injector plants ONE didactic feature (a fakeout, a Wyckoff range, a moving-average regime, …)
onto a base price path and knows its own ground-truth label, so the exercise solution is exact and
never travels to the client before answering. Injectors reuse — never modify — the frozen candle
engine (`engine.build_series`) and indicators (`indicators.rsi/macd`). The anti-leak machinery vetted
at the Phase-1 gate lives in `common.py` and is shared by every injector here.
"""
