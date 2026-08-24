# SPDX-License-Identifier: AGPL-3.0-only
"""Write `dist/contracts/generation-goldens/` — what the Kotlin generators are compared against.

Phase W2. The PRNG vectors prove the two languages draw the same numbers; this proves they build the
same charts out of them. One line per document, `id<TAB>sha256`, so a port runs the same ids and
diffs two text files.

**One hash recipe, and it is the committed goldens'.** Each document is canonicalized exactly as
`tests/test_golden_exercise_mode.py` canonicalizes it — the `{"p", "label", "ann"}` envelope for a
pattern chart, `{"p", "t", "s1", "s2"}` for a divergence, the `panels` list for a figure — and hashed
with the same `json.dumps(sort_keys=True, separators=(",", ":"))` bytes. The only difference is that
the digest is not truncated, so **the first 16 hex digits of every line ARE the committed
fingerprint** where a committed fingerprint exists. `tests/test_generation_goldens.py` asserts that
for all 84 goldens and the 4 checkable pins, which is what keeps this file and the suite from drifting
into two opinions about what a document is. The whole-document recipe
`verify_golden_stability.py` uses for its cross-machine digest is deliberately NOT used here.

**Two files, two stability contracts, and they are not the same promise.**

  * `exercise-mode.tsv` — **never moves.** These are the documents a learner is graded on. A line
    that changes means exercise generation changed, which is a bug until proven otherwise; adapting
    the file to make a comparison pass is the one thing it exists to prevent.
  * `figures.tsv` — **moves only with content, and only with a note.** A figure's seed is frozen in
    `content/figures/*.yaml` and a reader sees exactly that chart, so a line here changing means
    either a real content change (a reseed, a new resolution leg) or an accident. Phase W1 moved
    exactly one of these lines, for one value of one pane, and wrote down why.

**Retry-loop seeds are chosen by measurement, not by hope.** Three loops in the generation path
rebuild a chart when the plant it wanted did not land, and a port that gets the retry condition
subtly wrong reproduces every single-attempt document perfectly and diverges only on the rare
multi-attempt ones. So the loops are instrumented — by rebinding what each loop body calls, never by
touching production code — the seeds that go round more than once are found, and those documents are
in the file with their iteration counts in the README.

**The configs travel with the digests.** A golden is a promise about a document, and a document is a
config plus a seed — so `configs/` carries the exact config behind every line, serialized the way the
bundle serializes content and hashed beside it. `targets` feeds `rng.integers(0, len(targets))`: a
port that rebuilds a config from this file's prose instead of reading those bytes can match every
field and still generate a different document from every seed.

**One synthetic case pins how a double becomes text.** The hash is over JSON, so every double in a
payload is serialized, and CPython writes `repr()` — the shortest string that round-trips. The JVM's
`Double.toString` round-trips too and disagrees: `0.0001`, the display quantum of every momentum
pane in this course, is `1.0E-4` there. That is a whole-file mismatch from a formatter, not from
arithmetic, and `synthetic:formatter-shortest-repr` is the one-line test for it.

Usage (from `backend/`):
    uv run python scripts/export_generation_goldens.py
    uv run python scripts/export_generation_goldens.py --seeds 4 --scan 40      # a fast smoke run
    uv run python scripts/export_generation_goldens.py --dump-id fakeout:multi:0
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import sys
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

_BACKEND = Path(__file__).resolve().parent.parent
for _extra in (_BACKEND, _BACKEND / "src"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from scripts.export_bundle import canonical_bytes  # noqa: E402
from scripts.generation_workload import (  # noqa: E402
    CONTENT_DIR,
    DIVERGENCE_INDICATORS,
    DIVERGENCE_TARGETS,
    GOLDEN_DIVERGENCE_TARGETS,
    divergence_config,
    pattern_config,
)
from tradeschool.exercises.charts.patterns.registry import all_injectors, get_injector  # noqa: E402
from tradeschool.exercises.figures import build_figure, load_figures  # noqa: E402
from tradeschool.exercises.pattern_chart import (  # noqa: E402
    PatternChartConfig,
    PatternChartGenerator,
)
from tradeschool.exercises.pattern_chart import _instantiate as pattern_instantiate  # noqa: E402
from tradeschool.exercises.synthetic_chart import (  # noqa: E402
    SyntheticChartConfig,
    SyntheticChartGenerator,
)
from tradeschool.exercises.synthetic_chart import _instantiate as divergence_instantiate  # noqa: E402

DEFAULT_OUT = _BACKEND.parent / "dist" / "contracts" / "generation-goldens"

#: Seeds for the MULTI-target config — every label offered, so `rng.integers(0, len(targets))` picks
#: one and the retry loops run against whatever it picked. This is the committed goldens' own config.
MULTI_SEEDS: tuple[int, ...] = tuple(range(100))

#: Seeds for the SINGLE-target configs — one config per label, so the draw is deterministic and no
#: label goes unswept. A PREFIX of `MULTI_SEEDS`, so a document that appears in both blocks is the
#: same seed and a port debugging one is debugging the other.
SINGLE_SEEDS: tuple[int, ...] = tuple(range(20))

#: Bars per exercise-mode chart. The committed fingerprints use 130; a different `n` is a different
#: document, so this is not a tuning knob.
EXERCISE_BARS = 130

#: How far to scan for retry-loop seeds. Past the sweep's own range on purpose: a loop that only
#: retries on seed 312 still has to be in the file.
RETRY_SCAN_SEEDS: tuple[int, ...] = tuple(range(400))


# --- the one hash recipe ---------------------------------------------------------------------------


def canonical_json(document: object) -> bytes:
    """The bytes the committed fingerprints hash: sorted keys, no spaces, ASCII-escaped.

    Deliberately NOT the bundle's serialization (`export_bundle.canonical_bytes`, which turns
    `ensure_ascii` off so the TypeScript half can write the same files). This one is frozen by 90
    committed fingerprints and cannot be modernized.
    """
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def document_sha256(document: object) -> str:
    """The full digest. Its first 16 hex digits are the committed fingerprint, where one exists."""
    return hashlib.sha256(canonical_json(document)).hexdigest()


# --- the documents ---------------------------------------------------------------------------------

Document = tuple[str, Any]


def _config_and_kind(identifier: str) -> tuple[object, str]:
    """The config and document kind one id names — the ONE place an id is resolved.

    Every path into the goldens goes through here: the sweep, the retry scan and `--dump-id`. A
    second resolver would be a second opinion about what `fakeout:multi:7` means, and the whole point
    of the file is that a port and this repo agree on exactly that.
    """
    parts = identifier.split(":")
    if parts[0] == "divergence":
        indicator, shape = parts[1], parts[2]
        divergence_targets: tuple[str, ...] = (
            GOLDEN_DIVERGENCE_TARGETS if shape == "golden" else (shape,)
        )
        return divergence_config(indicator, divergence_targets), "divergence"
    injector = get_injector(parts[0])
    labels = tuple(injector.labels)
    targets: tuple[str, ...] = labels if parts[1] == "multi" else (parts[1],)
    return pattern_config(injector.name, labels, list(targets)), "pattern"


def raw_from_config(config: object, kind: str, seed: int) -> object:
    """The generator's own return value for one config and seed — the ONE instantiation site.

    Separate from `raw_for_id` so a config read back from a frozen file goes through exactly the code
    an id does. The two `cast`s are the price of `generation_workload`'s config builders returning
    `object`, which they do so that module stays importable without the generator types; the parse
    they wrap has already validated the config.
    """
    if kind == "divergence":
        return divergence_instantiate(cast("SyntheticChartConfig", config), seed)
    return pattern_instantiate(cast("PatternChartConfig", config), seed)


def raw_for_id(identifier: str) -> object:
    """One id's raw generator result, a tuple, before any envelope is put round it."""
    config, kind = _config_and_kind(identifier)
    return raw_from_config(config, kind, int(identifier.rsplit(":", 1)[1]))


def envelope_of(kind: str, result: object) -> Any:
    """A raw generator result wrapped in the envelope its own committed fingerprint uses."""
    assert isinstance(result, tuple)
    if kind == "divergence":
        target, swing1, swing2, payload = result
        return {"p": payload, "t": target.value, "s1": swing1, "s2": swing2}
    label, annotations, payload = result
    return {"p": payload, "label": label, "ann": annotations}


def document_for_id(identifier: str) -> Any:
    """One document, built from its id alone. What `--dump-id` prints, and what the sweep stores."""
    if identifier == FORMATTER_ID:
        return formatter_document()[1]
    if identifier.startswith("frozen:"):
        figure_id = identifier.split(":", 1)[1]
        return build_figure(load_figures(CONTENT_DIR)[figure_id], "en")["panels"]
    _config, kind = _config_and_kind(identifier)
    return envelope_of(kind, raw_for_id(identifier))


def exercise_ids(
    multi_seeds: tuple[int, ...] = MULTI_SEEDS, single_seeds: tuple[int, ...] = SINGLE_SEEDS
) -> Iterator[str]:
    """Every exercise-mode id, in a stable order: multi-target first, then label by label.

    The divergence generator gets the GOLDEN three-target list for its multi-target config, not the
    five-target one: the target is drawn with `rng.integers(0, len(targets))`, so the length of that
    list decides which label a seed lands on, and the committed fingerprints use three.
    """
    for injector in all_injectors():
        for seed in multi_seeds:
            yield f"{injector.name}:multi:{seed}"
        for label in injector.labels:
            for seed in single_seeds:
                yield f"{injector.name}:{label}:{seed}"
    for indicator in DIVERGENCE_INDICATORS:
        for seed in multi_seeds:
            yield f"divergence:{indicator}:golden:{seed}"
        for target in DIVERGENCE_TARGETS:
            for seed in single_seeds:
                yield f"divergence:{indicator}:{target}:{seed}"


def exercise_documents(
    multi_seeds: tuple[int, ...] = MULTI_SEEDS, single_seeds: tuple[int, ...] = SINGLE_SEEDS
) -> Iterator[Document]:
    for identifier in exercise_ids(multi_seeds, single_seeds):
        yield identifier, document_for_id(identifier)


def figure_documents() -> Iterator[Document]:
    """The frozen content figures, hashed as `test_generation_numerics.py` hashes its content pin.

    An `svg` figure is skipped and named in the README instead: it has no numerics at all, so there is
    nothing for a generator to reproduce and a line of zeroes would only invite a port to chase it.
    """
    for figure_id, spec in sorted(load_figures(CONTENT_DIR).items()):
        if spec.kind != "chart":
            continue
        yield f"frozen:{figure_id}", build_figure(spec, "en")["panels"]


def svg_figure_ids() -> list[str]:
    return sorted(fid for fid, spec in load_figures(CONTENT_DIR).items() if spec.kind != "chart")


def figure_panel_count() -> int:
    return sum(len(spec.panels) for spec in load_figures(CONTENT_DIR).values())


# --- the frozen configs ----------------------------------------------------------------------------

#: The configs' own directory inside the goldens, and the index carrying their hashes.
CONFIG_DIR_NAME = "configs"
CONFIG_INDEX_NAME = "INDEX.tsv"

#: A path component is a registry name, an injector label or a `DivergenceType` value. All three are
#: identifiers today; this refuses the day one of them grows a slash or a dot, rather than writing
#: outside the directory.
_SAFE_COMPONENT = re.compile(r"^[a-z0-9_]+$")


def config_key_of(identifier: str) -> str | None:
    """The config half of a document id — everything before the seed — or `None` if it has no config.

    Two shapes have none, and both are named rather than filtered by accident: the formatter case has
    no generator behind it at all, and a `frozen:` figure's config is its own YAML in
    `content/figures/`, which already travels in the bundle.
    """
    if identifier == FORMATTER_ID or identifier.startswith("frozen:"):
        return None
    return identifier.rsplit(":", 1)[0]


def config_relative_path(key: str) -> str:
    """Where one config is written — derived from the key, so the two can never disagree."""
    parts = key.split(":")
    components = (
        ("divergence", parts[1], parts[2]) if parts[0] == "divergence" else ("pattern", parts[0], parts[1])
    )
    for component in components:
        if not _SAFE_COMPONENT.match(component):
            raise ValueError(f"config key {key!r} has a component unusable as a path: {component!r}")
    return "/".join(components) + ".json"


def parse_config_document(document: Mapping[str, Any], kind: str) -> object:
    """A frozen config file's JSON, back through the generator's own `parse_config`.

    The same door the content loader uses, so "lossless" cannot mean lossless against a parser
    nothing else runs.
    """
    if kind == "divergence":
        return SyntheticChartGenerator().parse_config(document)
    return PatternChartGenerator().parse_config(document)


def config_documents(identifiers: Iterable[str]) -> dict[str, Any]:
    """`config key -> config as JSON` for every id that has one, in first-appearance order.

    Derived from the ids actually exported rather than from a second enumeration of the registry: the
    frozen set cannot then drift from the digests it is supposed to explain.
    """
    documents: dict[str, Any] = {}
    for identifier in identifiers:
        key = config_key_of(identifier)
        if key is None or key in documents:
            continue
        config, _kind = _config_and_kind(key)
        documents[key] = cast("PatternChartConfig | SyntheticChartConfig", config).model_dump(mode="json")
    return documents


def write_configs(out: Path, documents: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    """Write one file per config plus the index. Returns the index's `(key, path, sha256)` rows.

    The bundle's serialization, not this file's: `canonical_json` is frozen by 90 committed
    fingerprints and escapes non-ASCII, while a config is content and travels the way the bundle's
    content does. The two differ, so the choice is imported rather than retyped.
    """
    rows: list[tuple[str, str, str]] = []
    for key, document in documents.items():
        relative = config_relative_path(key)
        path = out / CONFIG_DIR_NAME / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = canonical_bytes(document)
        path.write_bytes(payload)
        rows.append((key, relative, hashlib.sha256(payload).hexdigest()))
    rows.sort()
    (out / CONFIG_DIR_NAME / CONFIG_INDEX_NAME).write_text(
        "\n".join(
            [
                "# FROZEN CONFIGS — the exact input behind every digest in `exercise-mode.tsv`.",
                "#",
                "# A document id is `<config>:<seed>`, so a port strips the trailing seed and reads the",
                "# file named here. The bytes are the bundle's canonical serialization — sorted keys, no",
                "# spaces, real UTF-8, one trailing newline — and `sha256` is over exactly those bytes.",
                "#",
                "# CONSUME THEM BYTE-IDENTICALLY, never `equivalent`. `targets` feeds",
                "# `rng.integers(0, len(targets))`, so that list's LENGTH decides which label a seed lands",
                "# on: a config meaning the same thing with a different target count generates a different",
                "# document from every seed at once. Defaults are written out (`indicator`, `explanation`",
                "# as `null`) so a port never has to guess one.",
                "#",
                "# Held to the committed goldens by `backend/tests/test_generation_config_freeze.py`.",
                "config\tpath\tsha256",
                *(f"{key}\t{relative}\t{digest}" for key, relative, digest in rows),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


# --- the retry loops -------------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryLoop:
    """One rebuild-until-it-lands loop, and the call that happens exactly once per iteration."""

    name: str
    where: str
    attempts: int
    module: str
    attribute: str
    counts: str
    injectors: tuple[str, ...]


#: The three retry loops in the generation path, with what an iteration means in each.
#:
#: The counted call is chosen to fire exactly once per iteration of that loop and nowhere else in its
#: module, which is why the counter is a count and not an estimate. Where the loop has a last-resort
#: attempt after the budget, whether that attempt is counted differs, and is stated: `divergence-plant`
#: builds its fallback WITHOUT noise and so never reaches `detrend_linear`, while
#: `cvd-divergence-plant` runs its fallback through the same closure as every other attempt.
RETRY_LOOPS: tuple[RetryLoop, ...] = (
    RetryLoop(
        name="divergence-plant",
        where="charts/injectors.py:184",
        attempts=7,
        module="tradeschool.exercises.charts.injectors",
        attribute="detrend_linear",
        counts=(
            "noisy attempts only: the loop shrinks sigma by 0.6 each time and re-verifies the "
            "oscillator relationship at the two swings. 7 means all seven failed and the no-noise "
            "last resort was used — that attempt builds no noise, so it is not counted."
        ),
        injectors=("divergence",),
    ),
    RetryLoop(
        name="cvd-divergence-plant",
        where="charts/patterns/cvd_divergence.py:139",
        attempts=7,
        module="tradeschool.exercises.charts.patterns.cvd_divergence",
        attribute="with_warmup",
        counts=(
            "every attempt, the last resort included (it runs the same closure with amplitude 0), "
            "so 8 is the maximum and means the fallback was needed."
        ),
        injectors=("cvd_divergence",),
    ),
    RetryLoop(
        name="squeeze-phase",
        where="charts/patterns/volatility_bands.py:143",
        attempts=6,
        module="tradeschool.exercises.charts.patterns.volatility_bands",
        attribute="_phase_path",
        counts=(
            "every attempt; each one pushes the phase harder (`_ESCALATE * attempt`) and then LOOKS "
            "at the bands it produced. There is no fallback: 6 without a landing raises."
        ),
        injectors=("volatility_bands",),
    ),
)


#: Loops with NO retrying seed anywhere in the measured range — a fact, not an omission.
#:
#: `cvd-divergence-plant` landed on its first attempt in all 3 200 builds over seeds 0..799: every
#: `cvd_divergence` document in the goldens is a single-attempt document, and the loop's retry branch
#: is unexercised by any seed this course can reach. Recorded here rather than left implicit, because
#: a loop that starts retrying is a change in generator behaviour and
#: `tests/test_generation_goldens.py` fails naming it.
LOOPS_WITH_NO_RETRY_FOUND: tuple[str, ...] = ("cvd-divergence-plant",)

#: How far the statement above was measured.
MEASURED_SCAN_DEPTH = 800


@contextmanager
def instrumented() -> Iterator[dict[str, int]]:
    """Count each retry loop's iterations, by rebinding what its body calls. Production untouched.

    The wrapper delegates to the original and returns its value unchanged, so a run with the counters
    installed produces byte-identical documents to a run without them — asserted in
    `tests/test_generation_goldens.py`, because a counter that perturbed the stream would poison every
    golden that was selected using it.
    """
    counts = {loop.name: 0 for loop in RETRY_LOOPS}
    restore: list[tuple[Any, str, Any]] = []

    def wrap(original: Callable[..., Any], name: str) -> Callable[..., Any]:
        def counting(*args: Any, **kwargs: Any) -> Any:
            counts[name] += 1
            return original(*args, **kwargs)

        return counting

    for loop in RETRY_LOOPS:
        module = importlib.import_module(loop.module)
        original = getattr(module, loop.attribute)
        setattr(module, loop.attribute, wrap(original, loop.name))
        restore.append((module, loop.attribute, original))
    try:
        yield counts
    finally:
        for module, attribute, original in restore:
            setattr(module, attribute, original)


def retry_iterations(
    build: Callable[[], object], counts: dict[str, int]
) -> dict[str, int]:
    """Iterations each loop ran while building ONE document — a difference of the running tallies."""
    before = dict(counts)
    build()
    return {name: counts[name] - before[name] for name in counts}


@dataclass(frozen=True)
class RetryFinding:
    """A document whose build went round one of the loops more than once."""

    loop: str
    key: str
    seed: int
    iterations: int


def _candidate_ids(seed: int) -> Iterator[tuple[str, str]]:
    """`(loop name, document id)` for every document at this seed that can reach a retry loop.

    Only the three injectors that own a loop: sweeping all 21 over 400 seeds to find seeds for three
    loops would spend twenty times the work for no extra coverage.
    """
    owners = {name: loop.name for loop in RETRY_LOOPS for name in loop.injectors}
    for injector in all_injectors():
        loop = owners.get(injector.name)
        if loop is None:
            continue
        yield loop, f"{injector.name}:multi:{seed}"
        for label in injector.labels:
            yield loop, f"{injector.name}:{label}:{seed}"
    for indicator in DIVERGENCE_INDICATORS:
        yield "divergence-plant", f"divergence:{indicator}:golden:{seed}"
        for target in DIVERGENCE_TARGETS:
            yield "divergence-plant", f"divergence:{indicator}:{target}:{seed}"


def scan_retry_loops(scan_seeds: tuple[int, ...] = RETRY_SCAN_SEEDS) -> list[RetryFinding]:
    """Every document in the scan range whose build retried, sorted deepest-first within each loop."""
    findings: list[RetryFinding] = []
    with instrumented() as counts:
        for seed in scan_seeds:
            for loop, identifier in _candidate_ids(seed):
                try:
                    ran = retry_iterations(lambda i=identifier: raw_for_id(i), counts)  # type: ignore[misc]
                except Exception:  # a refused plant is a designed outcome, not a retry finding
                    continue
                if ran[loop] > 1:
                    findings.append(
                        RetryFinding(loop=loop, key=identifier, seed=seed, iterations=ran[loop])
                    )
    return sorted(findings, key=lambda f: (f.loop, -f.iterations, f.key))


def retry_documents(findings: list[RetryFinding], *, per_depth: int = 3) -> Iterator[Document]:
    """The retry findings as documents, keeping up to `per_depth` seeds per (loop, iteration count).

    Bounded on purpose, and the bound is reported rather than applied quietly: a hundred two-attempt
    seeds teach a port nothing the third one did not, while the rare deep ones are the whole point.
    """
    chosen: dict[tuple[str, int], int] = {}
    for finding in findings:
        bucket = (finding.loop, finding.iterations)
        if chosen.get(bucket, 0) >= per_depth:
            continue
        chosen[bucket] = chosen.get(bucket, 0) + 1
        yield finding.key, document_for_id(finding.key)


# --- the formatter case ----------------------------------------------------------------------------


@dataclass(frozen=True)
class FormatterCase:
    """One double, with what each language prints for it. Both columns MEASURED, neither remembered."""

    name: str
    value: float
    python: str
    jvm: str


#: Doubles whose text form decides whether two languages hash the same bytes.
#:
#: `python` is `repr(value)` on CPython 3.14; `jvm` is `Double.toString(value)` on OpenJDK 25, measured
#: by `scripts/kotlin_side/DoubleReprCheck.java` (run it against the exported `formatter-cases.tsv` to
#: re-measure on another toolchain). Both round-trip; they choose differently:
#:
#:   * CPython writes the SHORTEST string that round-trips, in plain notation for exponents in
#:     [-4, 16) and `1e-05`/`1e+16` style outside it.
#:   * The JVM writes plain notation only inside [1e-3, 1e7), always a digit before the point, and an
#:     exponent with no `+` and no leading zero — and its digits are not always the shortest
#:     (`5e-324` becomes `4.9E-324`).
#:
#: `momentum-quantum` is not a curiosity: 0.0001 is the rounding quantum of every momentum pane in
#: this course, so a port using `Double.toString` mismatches real figures on the first pane it builds.
FORMATTER_CASES: tuple[FormatterCase, ...] = (
    FormatterCase("momentum-quantum", 1e-4, "0.0001", "1.0E-4"),
    FormatterCase("momentum-quantum-negative", -1e-4, "-0.0001", "-1.0E-4"),
    FormatterCase("below-python-plain", 1e-5, "1e-05", "1.0E-5"),
    FormatterCase("python-keeps-plain", 1e-3, "0.001", "0.001"),
    FormatterCase("tiny", 1e-7, "1e-07", "1.0E-7"),
    FormatterCase("ten-million", 1e7, "10000000.0", "1.0E7"),
    FormatterCase("jvm-switches-here", 12345678.0, "12345678.0", "1.2345678E7"),
    FormatterCase("just-below-jvm-switch", 1234567.0, "1234567.0", "1234567.0"),
    FormatterCase("large-power-of-ten", 1e16, "1e+16", "1.0E16"),
    FormatterCase("very-large", 1e21, "1e+21", "1.0E21"),
    FormatterCase("binary-artifact", 0.1 + 0.2, "0.30000000000000004", "0.30000000000000004"),
    FormatterCase("negative-zero", -0.0, "-0.0", "-0.0"),
    FormatterCase("unit", 1.0, "1.0", "1.0"),
    FormatterCase("real-price", 27000.0, "27000.0", "27000.0"),
    FormatterCase("min-subnormal", 5e-324, "5e-324", "4.9E-324"),
    FormatterCase("max-double", 1.7976931348623157e308, "1.7976931348623157e+308", "1.7976931348623157E308"),
    FormatterCase(
        "min-normal", 2.2250738585072014e-308, "2.2250738585072014e-308",
        "2.2250738585072014E-308",
    ),
)

FORMATTER_ID = "synthetic:formatter-shortest-repr"


def formatter_document() -> Document:
    """A payload of nothing but the awkward doubles, shaped like a real one so it hashes the same way."""
    return FORMATTER_ID, {
        "p": {case.name: case.value for case in FORMATTER_CASES},
        "label": "formatter",
        "ann": [],
    }


def jvm_notation_differs(value: float) -> bool:
    """Would the JVM write this double in a different NOTATION than CPython does?

    A notation check, not a full repr comparison: the JVM leaves plain notation at 1e-3 and 1e7 while
    CPython leaves it at 1e-4 and 1e16, so anything in between the two thresholds is written one way
    here and the other way there. Digit-level differences (`5e-324` vs `4.9E-324`) are NOT counted;
    `DoubleReprCheck.java` is what compares exactly.
    """
    if value == 0.0 or value != value or value in (float("inf"), float("-inf")):
        return False
    magnitude = abs(value)
    return magnitude < 1e-3 or magnitude >= 1e7


def _count_awkward_floats(document: object) -> int:
    if isinstance(document, float):
        return 1 if jvm_notation_differs(document) else 0
    if isinstance(document, dict):
        return sum(_count_awkward_floats(value) for value in document.values())
    if isinstance(document, list | tuple):
        return sum(_count_awkward_floats(value) for value in document)
    return 0


# --- files -----------------------------------------------------------------------------------------


def _lines(documents: list[tuple[str, str]], comment: list[str]) -> str:
    body = ["# " + line if line else "#" for line in comment]
    body.extend(f"{key}\t{digest}" for key, digest in documents)
    return "\n".join(body) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"default {DEFAULT_OUT}")
    parser.add_argument(
        "--seeds", type=int, default=len(MULTI_SEEDS),
        help=f"multi-target seeds (default {len(MULTI_SEEDS)}; single-target uses the first "
             f"{len(SINGLE_SEEDS)} of them)",
    )
    parser.add_argument(
        "--scan", type=int, default=len(RETRY_SCAN_SEEDS),
        help=f"how many seeds to scan for retry-loop documents (default {len(RETRY_SCAN_SEEDS)})",
    )
    parser.add_argument(
        "--dump-id", default=None,
        help="print one document's full canonical JSON and exit — the bytes that were hashed",
    )
    args = parser.parse_args(argv)

    multi_seeds = tuple(range(args.seeds))
    single_seeds = tuple(range(min(len(SINGLE_SEEDS), args.seeds)))

    if args.dump_id:
        try:
            print(canonical_json(document_for_id(args.dump_id)).decode())
        except (KeyError, IndexError, ValueError) as error:
            print(f"cannot build a document for id {args.dump_id!r}: {error}", file=sys.stderr)
            return 1
        return 0

    started = time.monotonic()
    print(f"building exercise-mode documents ({len(multi_seeds)} multi / {len(single_seeds)} single) ...",
          flush=True)
    exercise: dict[str, str] = {}
    awkward = 0
    for key, document in exercise_documents(multi_seeds, single_seeds):
        exercise[key] = document_sha256(document)
        awkward += _count_awkward_floats(document)
    swept = len(exercise)

    print(f"scanning {args.scan} seeds for retry-loop documents ...", flush=True)
    findings = scan_retry_loops(tuple(range(args.scan)))
    retry_keys: list[str] = []
    for key, document in retry_documents(findings):
        if key not in exercise:
            exercise[key] = document_sha256(document)
        retry_keys.append(key)

    identifier, document = formatter_document()
    exercise[identifier] = document_sha256(document)

    print("building figure documents ...", flush=True)
    figures = {key: document_sha256(document) for key, document in figure_documents()}

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    # Derived from the ids just exported, so the frozen set explains exactly these digests.
    frozen_configs = config_documents(exercise)
    config_rows = write_configs(out, frozen_configs)
    by_loop: dict[str, list[RetryFinding]] = {}
    for finding in findings:
        by_loop.setdefault(finding.loop, []).append(finding)

    (out / "exercise-mode.tsv").write_text(
        _lines(
            sorted(exercise.items()),
            [
                "EXERCISE-MODE GENERATION GOLDENS — these lines NEVER move.",
                "",
                "`id<TAB>sha256`. The digest is sha256 over the canonical JSON of the document's",
                "envelope: `{\"p\": payload, \"label\": label, \"ann\": annotations}` for a pattern chart,",
                "`{\"p\", \"t\", \"s1\", \"s2\"}` for a divergence, serialized with sorted keys and no",
                "spaces. The FIRST 16 HEX DIGITS are the fingerprint the web repo's",
                "`tests/test_golden_exercise_mode.py` has committed, where it has one.",
                "",
                "id shapes:",
                "  <injector>:multi:<seed>              every label offered; the label is drawn",
                "  <injector>:<label>:<seed>            one label offered; the draw is deterministic",
                "  divergence:<rsi|macd>:golden:<seed>  the committed goldens' 3-target list",
                "  divergence:<rsi|macd>:<target>:<seed>",
                "  synthetic:formatter-shortest-repr    no generator: how a double becomes text",
                "",
                "A line that changes means exercise generation changed. Do not adapt this file to",
                "make a comparison pass; find out what moved. The reasoning is in the web",
                "repository's `phase-w2-bundle-and-contracts.md`.",
                "",
                f"documents: {len(exercise)}  (bars per chart: {EXERCISE_BARS})",
            ],
        ),
        encoding="utf-8",
    )

    (out / "figures.tsv").write_text(
        _lines(
            sorted(figures.items()),
            [
                "FIGURE GOLDENS — these lines move only when the CONTENT moves, and only with a note.",
                "",
                "`frozen:<figure id><TAB>sha256`, one line per chart figure in `content/figures/`. The",
                "digest is sha256 over the canonical JSON of `build_figure(spec, \"en\")[\"panels\"]` —",
                "the same recipe `tests/test_generation_numerics.py` pins its content figure with, so",
                "the first 16 hex digits match that pin where it exists.",
                "",
                "A figure's seed is frozen in its own YAML and a reader sees exactly this chart, so a",
                "line here changing is either a real content change (a reseed, a new injector,",
                "a new resolution leg) or an accident. Phase W1 moved exactly one line of this file,",
                "by one 0.0001 step in one momentum value, and wrote down why. Move one the same way:",
                "with the reason recorded beside it.",
                "",
                "Also coupled: `content/figure-coupling.yaml` declares which lesson prose quotes which",
                "of these generated values, and `backend/tests/test_figure_prose_coupling.py` fails",
                "naming the lessons that need a prose pass. A moved figure line means that pass is due.",
                "",
                f"figures: {len(figures)} chart figures, {figure_panel_count()} panels in total.",
                f"NOT here: {', '.join(svg_figure_ids())} — kind `svg`, a frontend component name with",
                "no numerics, so there is nothing for a generator to reproduce.",
            ],
        ),
        encoding="utf-8",
    )

    (out / "formatter-cases.tsv").write_text(
        "\n".join(
            [
                "# How a double becomes text — the input to `synthetic:formatter-shortest-repr`.",
                "#",
                "# `python` is CPython's `repr`, which is what `json.dumps` writes and therefore what",
                "# every digest in this directory is taken over. `jvm` is OpenJDK's `Double.toString`,",
                "# measured by `backend/scripts/kotlin_side/DoubleReprCheck.java` — run that program",
                "# against this file to re-measure on your own toolchain.",
                "#",
                "# Both round-trip. They disagree about notation (CPython leaves plain form at 1e-4 and",
                "# 1e16, the JVM at 1e-3 and 1e7) and occasionally about digits (`5e-324` vs `4.9E-324`).",
                "# A port that formats with `Double.toString` fails every document containing a value in",
                "# the gap — starting with 0.0001, the momentum pane's own quantum.",
                "name\thex\tpython\tjvm\tagree",
                *[
                    "\t".join(
                        [
                            case.name,
                            "0x" + __import__("struct").pack(">d", case.value).hex(),
                            case.python,
                            case.jvm,
                            "true" if case.python == case.jvm else "false",
                        ]
                    )
                    for case in FORMATTER_CASES
                ],
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    configs = len(all_injectors()) + len(DIVERGENCE_INDICATORS)
    multi_documents = len(multi_seeds) * configs
    readme = [
        "<!-- SPDX-License-Identifier: AGPL-3.0-only -->",
        "# Cross-language generation goldens",
        "",
        "Generated by `backend/scripts/export_generation_goldens.py` in the TradeSchool web repo. Do",
        "not hand-edit; regenerate and read the diff.",
        "",
        "The Android port reimplements the chart and exercise generators in Kotlin. These files are",
        "what those generators are compared against: run the same ids, hash the same way, diff two",
        "text files. A mismatch names one document instead of one screenshot.",
        "",
        "## The hash recipe — one, and it is the web repo's own",
        "",
        "```",
        "digest = sha256(json.dumps(envelope, sort_keys=True, separators=(\",\", \":\")))",
        "```",
        "",
        "| document | envelope |",
        "| --- | --- |",
        "| pattern chart | `{\"p\": payload, \"label\": label, \"ann\": annotations}` |",
        "| divergence | `{\"p\": payload, \"t\": target, \"s1\": swing1, \"s2\": swing2}` |",
        "| figure | the `panels` list of `build_figure(spec, \"en\")` |",
        "",
        "`payload` is the ROUNDED payload — prices to 2 decimals, panes to 2 or 4 — which is exactly",
        "the parity contract Phase W1 settled on. Raw intermediate floats are deliberately not part of",
        "any contract here: two correct libms may differ in the last bit of an `exp`, and measurement",
        "showed that a full-ulp perturbation of every `exp`/`log` result moves none of these digests.",
        "",
        "**The first 16 hex digits of a line are the fingerprint the web repo commits**, where it",
        "commits one (84 in `tests/test_golden_exercise_mode.py`, 6 pins in",
        "`tests/test_generation_numerics.py`). That overlap is asserted by",
        "`backend/tests/test_generation_goldens.py`, so these files cannot drift from the suite.",
        "",
        "## The two files are two different promises",
        "",
        "| file | contract |",
        "| --- | --- |",
        f"| `exercise-mode.tsv` ({len(exercise)} documents) | **never moves.** "
        "A learner is graded on these. |",
        f"| `figures.tsv` ({len(figures)} documents) | **moves only with content, with a note.** "
        "Frozen seeds a reader sees. |",
        "",
        "`formatter-cases.tsv` is neither: it is the input table behind one synthetic document, kept",
        "separate so a port can read the expected text per value instead of only a digest.",
        "",
        "## What is in `exercise-mode.tsv`",
        "",
        "| block | documents |",
        "| --- | --- |",
        f"| multi-target, {len(multi_seeds)} seeds x every injector | {multi_documents} |",
        f"| single-target, {len(single_seeds)} seeds x every injector-label pair | "
        f"{swept - multi_documents} |",
        f"| retry-loop seeds (see below) | {len(exercise) - swept - 1} new |",
        "| the formatter case | 1 |",
        f"| **total** | **{len(exercise)}** |",
        "",
        f"Injectors: {len(all_injectors())} pattern injectors plus the divergence generator, whose two",
        "oscillators (`rsi`, `macd`) take different retry paths and so count as two configs.",
        "",
        "## The frozen configs",
        "",
        f"`{CONFIG_DIR_NAME}/` carries the {len(config_rows)} configs these documents were generated",
        f"from — one JSON file each, with `{CONFIG_DIR_NAME}/{CONFIG_INDEX_NAME}` naming every one",
        "beside the sha256 of its own bytes. A document id is `<config>:<seed>`, so strip the trailing",
        "seed and what remains names the file:",
        "",
        "```",
        "fakeout:multi:7                    -> configs/pattern/fakeout/multi.json",
        "divergence:macd:bearish_hidden:149 -> configs/divergence/macd/bearish_hidden.json",
        "```",
        "",
        "**Consume them byte-identically, never re-declared as equivalent.** `targets` feeds",
        "`rng.integers(0, len(targets))`, so the LENGTH of that list decides which label a seed lands",
        "on — a config that means the same thing with one target fewer generates a different document",
        "from every seed at once, and the digests above would all move together with nothing to say",
        "why. That is why the divergence generator carries a three-target `golden` config beside its",
        "five-target ones, and why the defaults are written out rather than left to a port's idea of",
        "them: `indicator` and `explanation` are `null` here, explicitly.",
        "",
        "The serialization is the BUNDLE's canonical form — sorted keys, no spaces, real UTF-8, one",
        "trailing newline — not the digest recipe above, which escapes non-ASCII and ends without a",
        "newline. Two canonical forms, and mixing them is a silent wrong hash.",
        "",
        "## Retry-loop seeds",
        "",
        "Three loops rebuild a chart when the plant they wanted did not land. A port that gets the",
        "retry CONDITION subtly wrong reproduces every single-attempt document perfectly and diverges",
        "only on the rare multi-attempt ones — so those are found by instrumenting the loops (counting",
        "one call per iteration, production code untouched) and included explicitly.",
        "",
        f"Scanned seeds 0..{args.scan - 1}. Up to 3 seeds are kept per (loop, iteration count); the",
        "rest are reported here and dropped, never dropped silently.",
        "",
        "| loop | where | budget | what an iteration means |",
        "| --- | --- | --- | --- |",
    ]
    for loop in RETRY_LOOPS:
        readme.append(f"| `{loop.name}` | `{loop.where}` | {loop.attempts} | {loop.counts} |")
    readme += [
        "",
        "| loop | iterations | seeds found | documents kept |",
        "| --- | --- | --- | --- |",
    ]
    for loop in RETRY_LOOPS:
        depths: dict[int, list[str]] = {}
        for finding in by_loop.get(loop.name, []):
            depths.setdefault(finding.iterations, []).append(f"{finding.key}")
        if not depths:
            readme.append(f"| `{loop.name}` | — | none in range | 0 |")
        for iterations in sorted(depths, reverse=True):
            keys = depths[iterations]
            kept = [key for key in retry_keys if key in keys][:3]
            readme.append(
                f"| `{loop.name}` | {iterations} | {len(keys)} | {', '.join(f'`{k}`' for k in kept)} |"
            )
    readme += [
        "",
        "One of the three never retries, and that is a measured fact rather than a gap: "
        f"`{'`, `'.join(LOOPS_WITH_NO_RETRY_FOUND)}` landed on its first attempt in every build over",
        f"seeds 0..{MEASURED_SCAN_DEPTH - 1}, so every `cvd_divergence` document here is a",
        "single-attempt document and that loop's retry branch is unexercised by any seed this course",
        "can reach. The web repo's suite fails naming it if that ever stops being true.",
        "",
        "## The formatter case",
        "",
        "`synthetic:formatter-shortest-repr` has no generator behind it. Its payload is a dictionary of",
        "awkward doubles, and it exists because the digest is taken over JSON: every double becomes",
        "text first, and the two languages do not agree on the text.",
        "",
        "CPython writes the shortest string that round-trips (`0.0001`, `1e-05`, `1e+16`). The JVM's",
        "`Double.toString` also round-trips and writes `1.0E-4`, `1.0E-5`, `1.0E16` — plain notation",
        "only inside [1e-3, 1e7), always a digit before the point, an exponent with no sign and no",
        "leading zero, and digits that are not always the shortest (`5e-324` becomes `4.9E-324`).",
        "",
        "**This is not academic.** `0.0001` is the rounding quantum of every momentum pane in this",
        f"course, and {awkward} float(s) in the exported exercise-mode payloads fall in the range where",
        "the two notations differ. A port formatting with `Double.toString` fails on the first figure",
        "with a momentum pane.",
        "",
        "`formatter-cases.tsv` has both columns, both measured — CPython "
        f"{sys.version.split()[0]} and OpenJDK via `scripts/kotlin_side/DoubleReprCheck.java`. Run",
        "that program against the file to re-measure on your toolchain.",
        "",
        "## Debugging a mismatch",
        "",
        "```",
        "cd backend",
        "uv run python scripts/export_generation_goldens.py --dump-id <id>",
        "```",
        "",
        "prints the exact canonical JSON that was hashed, so the diff is against numbers rather than",
        "against a digest.",
        "",
    ]
    (out / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    print()
    print("=" * 78)
    print(f"GENERATION GOLDENS  {out}")
    print("=" * 78)
    print(f"exercise-mode.tsv   {len(exercise)} documents  (never move)")
    print(f"figures.tsv         {len(figures)} documents  (move with content, with a note)")
    print(f"formatter-cases.tsv {len(FORMATTER_CASES)} doubles, both languages measured")
    print(f"{CONFIG_DIR_NAME + '/':<20}{len(config_rows)} frozen configs  (consume byte-identically)")
    print(f"total documents     {len(exercise) + len(figures)}")
    print()
    for loop in RETRY_LOOPS:
        found = by_loop.get(loop.name, [])
        seen = sorted({finding.iterations for finding in found}, reverse=True)
        print(f"  {loop.name:<22} {len(found):>4} retrying seeds  depths {seen or '—'}")
    print(f"  {'awkward floats':<22} {awkward:>4} in the exported payloads (JVM notation differs)")
    print(f"elapsed             {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
