# SPDX-License-Identifier: AGPL-3.0-only
"""Reading-time estimate for a lesson, in SECONDS.

Seconds, not minutes: every aggregate the UI shows is a sum of lessons, and summing already-rounded
minutes drifts. The display layer rounds exactly once. A derived metric, absent from the course export.
"""

from __future__ import annotations

import re

# Both constants are a STARTING CALIBRATION, expected to be tuned against real reading (how long
# learners actually spend on a lesson) once there is data to tune against. They are named, and used
# nowhere as literals, precisely so that tuning them is a one-line change.
#
# 200 words per minute: the low end of the usual adult silent-reading range, chosen deliberately —
# this is dense technical prose with numbers in it, not a novel.
READING_WPM = 200
# 30 seconds per embedded figure: a lesson chart is read, not skimmed (find the annotated candle,
# check it against the caption), and it contributes no words at all to the prose count.
FIGURE_SECONDS = 30

# --- markup the estimate must see through -----------------------------------------------------
# Order matters below: containers before leaves before inline markup.

_FRONT_MATTER = re.compile(r"\A---\n.*?\n---[ \t]*\n", re.DOTALL)
# A fenced code block is not prose (it is read at a completely different speed), so the whole body
# goes. Inline code is the opposite case — `Decimal` inside a sentence is a word you read — and is
# handled further down by dropping the backticks and keeping the token.
_FENCED_CODE = re.compile(r"^```[^\n]*\n.*?^```[ \t]*$", re.DOTALL | re.MULTILINE)
# `:::note{type=warning}` … `:::` — the FENCE lines go, the callout prose inside them stays: a
# warning is text the learner reads like any other paragraph.
_CONTAINER_FENCE = re.compile(r"^:::[a-z]*(\{[^}\n]*\})?[ \t]*$", re.MULTILINE)
# Leaf directives (`::figure{id=…}`, `::exercise{id=…}`) contribute no words. Figures are paid for
# separately in FIGURE_SECONDS; exercises contribute nothing to a *reading* estimate at all.
_LEAF_DIRECTIVE = re.compile(r"^::[a-z][\w-]*(\{[^}\n]*\})?[ \t]*$", re.MULTILINE)
_FIGURE_DIRECTIVE = re.compile(r"^::figure\{[^}\n]*\}[ \t]*$", re.MULTILINE)

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_INLINE_CODE = re.compile(r"`([^`]*)`")
_HEADING_MARK = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.MULTILINE)
_QUOTE_MARK = re.compile(r"^[ \t]*>[ \t]?", re.MULTILINE)
_LIST_MARK = re.compile(r"^[ \t]*([-*+]|\d+\.)[ \t]+", re.MULTILINE)
_THEMATIC_BREAK = re.compile(r"^[ \t]*(-{3,}|\*{3,}|_{3,})[ \t]*$", re.MULTILINE)
_TABLE_RULE = re.compile(r"^[ \t]*\|?[ \t]*:?-{2,}:?[ \t|:-]*$", re.MULTILINE)
_EMPHASIS = re.compile(r"[*_]{1,3}")
_ESCAPE = re.compile(r"\\(.)")


def prose_text(markdown: str) -> str:
    """The lesson stripped to what a reader actually reads; callout text kept."""
    text = _FRONT_MATTER.sub("", markdown)
    text = _HTML_COMMENT.sub("", text)
    text = _FENCED_CODE.sub("", text)
    text = _CONTAINER_FENCE.sub("", text)
    text = _LEAF_DIRECTIVE.sub("", text)
    text = _IMAGE.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _THEMATIC_BREAK.sub("", text)
    text = _TABLE_RULE.sub("", text)
    text = _HEADING_MARK.sub("", text)
    text = _QUOTE_MARK.sub("", text)
    text = _LIST_MARK.sub("", text)
    text = text.replace("|", " ")
    text = _EMPHASIS.sub("", text)
    text = _ESCAPE.sub(r"\1", text)
    return text.strip()


def prose_word_count(markdown: str) -> int:
    """Words in the lesson prose, counted the same way in every language.

    A token needs one alphanumeric character to count, so a dash used as punctuation is not a word.
    """
    return sum(1 for token in prose_text(markdown).split() if any(ch.isalnum() for ch in token))


def figure_count(markdown: str) -> int:
    """Embedded `::figure{id=…}` directives — the charts the reader stops to look at."""
    return len(_FIGURE_DIRECTIVE.findall(markdown))


def estimate_seconds(markdown: str) -> int:
    """Estimated reading time for one lesson, in whole seconds.

    Only the prose term is rounded; the figure term stays exact, so adding a figure moves the estimate
    by exactly FIGURE_SECONDS.
    """
    prose = round(prose_word_count(markdown) / READING_WPM * 60)
    return prose + figure_count(markdown) * FIGURE_SECONDS
