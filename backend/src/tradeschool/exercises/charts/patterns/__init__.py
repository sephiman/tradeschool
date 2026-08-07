# SPDX-License-Identifier: AGPL-3.0-only
"""Phase-2 pattern injectors (§3.3) for the generic `pattern_chart` generator.

Each plants ONE didactic feature and knows its own ground-truth label. Injectors reuse — never
modify — the frozen `engine.build_series` and `indicators`; shared anti-leak machinery is `common.py`.
"""
