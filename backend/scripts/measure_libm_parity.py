# SPDX-License-Identifier: AGPL-3.0-only
"""Record every double reaching `np.exp`/`np.log` in the generation path, and pin its value.

Phase W1 deliverable 0. Every close price is `base * exp(shape + noise)`, and neither function is
required to be correctly rounded, so two libms may differ in the last bit — which matters because the
port calls `StrictMath` (fdlibm), a different algorithm from glibc's. So: sweep the workload, collect
the real arguments, write down what each implementation returns, bit for bit.

Writes to `scripts/artifacts/`, all committed: `libm-parity-summary.json` (counts, ranges,
environment, SHA-256 digests over the COMPLETE streams), `libm-parity-sample.tsv` (a bounded
stratified sample as hex bit patterns) and `libm-parity-domain.json` (the interval each function is
called on). The full ~2M-row stream is not committed; `--full` regenerates it.

The ufuncs are monkeypatched inside this harness — production code is never touched for measurement,
and the wrapper delegates to the original so a recorded run produces identical output.

Usage:
    python scripts/measure_libm_parity.py [--seeds N] [--out DIR] [--full]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import struct
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.generation_workload import PROBE_SEEDS, run_workload

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
SAMPLE_NAME = "libm-parity-sample.tsv"
SUMMARY_NAME = "libm-parity-summary.json"
DOMAIN_NAME = "libm-parity-domain.json"
FULL_NAME = "libm-parity-full.tsv"

#: Rows committed per function: reviewable (~1 MB) and conclusive above a ~0.05% disagreement rate.
SAMPLE_PER_FN = 10_000

#: Dedup flush threshold — a memory bound only; the result is identical at any chunk size.
_DEDUP_CHUNK = 4_000_000

_FUNCTIONS = ("exp", "log")


def hex64(value: float) -> str:
    """A double's exact IEEE-754 bit pattern, big-endian, as `0x` + 16 hex digits."""
    return "0x" + struct.pack(">d", float(value)).hex()


@dataclass
class Collector:
    """Deduplicating store of the doubles that reached one ufunc."""

    name: str
    calls: int = 0
    values: int = 0
    _pending: list[np.ndarray] = field(default_factory=list)
    _pending_size: int = 0
    _unique: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.uint64))

    def add(self, arg: Any) -> None:
        arr = np.asarray(arg, dtype=np.float64).ravel()
        self.calls += 1
        self.values += arr.size
        if arr.size:
            # The BIT PATTERN, not the value: keeps -0.0 distinct from +0.0, as bit parity needs.
            self._pending.append(arr.view(np.uint64).copy())
            self._pending_size += arr.size
        if self._pending_size >= _DEDUP_CHUNK:
            self._compact()

    def _compact(self) -> None:
        if not self._pending:
            return
        self._unique = np.unique(np.concatenate([self._unique, *self._pending]))
        self._pending = []
        self._pending_size = 0

    def unique_bits(self) -> np.ndarray:
        """Distinct inputs, sorted by bit pattern — a total order, so the artifact is byte-stable."""
        self._compact()
        return self._unique


@contextmanager
def recording(*, exp: Collector, log: Collector) -> Iterator[None]:
    """Intercept `np.exp`/`np.log` for the duration, delegating to the untouched originals."""
    real_exp, real_log = np.exp, np.log

    def wrapped_exp(x: Any, *args: Any, **kwargs: Any) -> Any:
        exp.add(x)
        return real_exp(x, *args, **kwargs)

    def wrapped_log(x: Any, *args: Any, **kwargs: Any) -> Any:
        log.add(x)
        return real_log(x, *args, **kwargs)

    np.exp = wrapped_exp  # type: ignore[assignment]
    np.log = wrapped_log  # type: ignore[assignment]
    try:
        yield
    finally:
        np.exp = real_exp
        np.log = real_log


@dataclass
class Measured:
    """One function's distinct inputs and both implementations' results, index-aligned."""

    name: str
    inputs: np.ndarray  # uint64 bit patterns, ascending
    numpy_out: np.ndarray  # uint64 bit patterns
    libm_out: np.ndarray  # uint64 bit patterns
    calls: int
    values: int

    @property
    def mismatch_index(self) -> np.ndarray:
        return np.asarray(np.nonzero(self.numpy_out != self.libm_out)[0], dtype=np.int64)


def _evaluate(name: str, bits: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(numpy result bits, libm result bits) for every input bit pattern, order preserved."""
    inputs = bits.view(np.float64)
    ufunc = np.exp if name == "exp" else np.log
    with np.errstate(all="ignore"):
        numpy_out = np.asarray(ufunc(inputs), dtype=np.float64)
    scalar = math.exp if name == "exp" else math.log
    libm_out = np.empty_like(inputs)
    for i, value in enumerate(inputs.tolist()):
        try:
            libm_out[i] = scalar(value)
        except (ValueError, OverflowError):
            # `math` raises where the ufunc returns NaN/inf; mirror the ufunc so the columns compare.
            with np.errstate(all="ignore"):
                libm_out[i] = float(np.asarray(ufunc(np.float64(value))))
    return numpy_out.view(np.uint64), libm_out.view(np.uint64)


def _digest(bits: np.ndarray) -> str:
    """SHA-256 over the big-endian bytes of a bit-pattern stream, in the stream's own order."""
    return hashlib.sha256(bits.astype(">u8").tobytes()).hexdigest()


def _stats(m: Measured) -> dict[str, object]:
    inputs = m.inputs.view(np.float64)
    finite = inputs[np.isfinite(inputs)]
    tiny = np.finfo(np.float64).tiny
    differing = m.mismatch_index
    first = [
        {
            "input": hex64(inputs[i]),
            "input_decimal": repr(float(inputs[i])),
            "numpy": hex64(m.numpy_out[i : i + 1].view(np.float64)[0]),
            "libm": hex64(m.libm_out[i : i + 1].view(np.float64)[0]),
        }
        for i in differing[:8]
    ]
    return {
        "calls": m.calls,
        "values_seen": m.values,
        "distinct_inputs": int(m.inputs.size),
        "finite_input_min": float(finite.min()) if finite.size else None,
        "finite_input_max": float(finite.max()) if finite.size else None,
        "nan_inputs": int(np.isnan(inputs).sum()),
        "positive_infinity_inputs": int((inputs == np.inf).sum()),
        "negative_infinity_inputs": int((inputs == -np.inf).sum()),
        "subnormal_inputs": int(((inputs != 0.0) & (np.abs(inputs) < tiny)).sum()),
        # `log` of a non-positive argument would put a NaN into a price path — hence its own counter.
        "domain_error_inputs": int((inputs <= 0.0).sum()) if m.name == "log" else 0,
        "numpy_vs_libm_mismatches": int(differing.size),
        "first_mismatches": first,
        "digests": {
            "inputs": _digest(m.inputs),
            "numpy": _digest(m.numpy_out),
            "libm": _digest(m.libm_out),
        },
    }


def _sample_index(m: Measured, per_fn: int) -> np.ndarray:
    """Rows to commit: an even stride over the sorted domain, both endpoints, plus every disagreement."""
    n = int(m.inputs.size)
    if n == 0:
        return np.empty(0, dtype=np.int64)
    stride = max(1, n // per_fn)
    idx = np.arange(0, n, stride, dtype=np.int64)
    keep = np.concatenate([idx, np.array([0, n - 1], dtype=np.int64), m.mismatch_index])
    return np.unique(keep)


_TSV_HEADER = (
    "# TradeSchool Phase W1 — libm parity artifact\n"
    "# Produced by backend/scripts/measure_libm_parity.py. The contract the Android port reads is\n"
    "# contracts/libm-parity/README.md, staged by scripts/export_libm_parity.py; the runnable\n"
    "# reference is kotlin_side/LibmParityCheck.java, which ships beside it.\n"
    "# Columns: fn, input, numpy, libm — each an IEEE-754 double's exact bit pattern, big-endian.\n"
    "# `numpy` is the value the goldens were captured from and the value a port must reproduce.\n"
    "# `libm` is math.exp/math.log, i.e. the platform C library, recorded so the artifact shows\n"
    "# whether NumPy's own kernel IS the libm on the machine that produced it.\n"
)


def _write_tsv(path: Path, rows: list[tuple[Measured, np.ndarray]], note: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(_TSV_HEADER)
        fh.write(f"# {note}\n")
        fh.write("fn\tinput\tnumpy\tlibm\n")
        for m, index in rows:
            inputs = m.inputs.view(np.float64)
            np_out = m.numpy_out.view(np.float64)
            libm_out = m.libm_out.view(np.float64)
            for i in index.tolist():
                fh.write(
                    f"{m.name}\t{hex64(inputs[i])}\t{hex64(np_out[i])}\t{hex64(libm_out[i])}\n"
                )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--seeds", type=int, default=len(PROBE_SEEDS),
        help=f"probe seeds per injector kind (default {len(PROBE_SEEDS)}, the contract floor)",
    )
    parser.add_argument("--out", type=Path, default=ARTIFACT_DIR, help="artifact directory")
    parser.add_argument(
        "--full", action="store_true",
        help=f"also write {FULL_NAME} — every distinct input, ~120 MB, NOT committed",
    )
    args = parser.parse_args(argv)

    seeds = tuple(range(args.seeds))
    collectors = {name: Collector(name) for name in _FUNCTIONS}

    print(f"sweeping the generation path over {len(seeds)} probe seeds per injector kind ...")
    started = time.monotonic()
    with recording(exp=collectors["exp"], log=collectors["log"]):
        report = run_workload(seeds)
    sweep_seconds = time.monotonic() - started

    measured: list[Measured] = []
    for name in _FUNCTIONS:
        c = collectors[name]
        bits = c.unique_bits()
        numpy_out, libm_out = _evaluate(name, bits)
        measured.append(Measured(name, bits, numpy_out, libm_out, c.calls, c.values))

    args.out.mkdir(parents=True, exist_ok=True)
    sampled = [(m, _sample_index(m, SAMPLE_PER_FN)) for m in measured]
    sample_rows = sum(int(idx.size) for _, idx in sampled)
    total_rows = sum(int(m.inputs.size) for m in measured)
    _write_tsv(
        args.out / SAMPLE_NAME,
        sampled,
        f"SAMPLE: {sample_rows} of {total_rows} distinct inputs (even stride over the sorted domain, "
        f"both endpoints, plus every numpy/libm disagreement). Regenerate the complete stream with "
        f"--full; verify it against the summary's digests.",
    )
    if args.full:
        _write_tsv(
            args.out / FULL_NAME,
            [(m, np.arange(m.inputs.size, dtype=np.int64)) for m in measured],
            f"COMPLETE: all {total_rows} distinct inputs.",
        )

    stats = {m.name: _stats(m) for m in measured}
    summary: dict[str, object] = {
        "probe_seeds": len(seeds),
        "documents_generated": report.produced,
        "documents_refused": len(report.failures),
        "refusals": report.failures[:40],
        "sweep_seconds": round(sweep_seconds, 1),
        "sample_artifact": SAMPLE_NAME,
        "sample_rows": sample_rows,
        "sample_rows_per_function_cap": SAMPLE_PER_FN,
        "total_distinct_inputs": total_rows,
        "functions": stats,
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "libc": " ".join(platform.libc_ver()),
        },
    }
    (args.out / SUMMARY_NAME).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    domain = {
        m.name: {
            "min": float(m.inputs.view(np.float64)[np.isfinite(m.inputs.view(np.float64))].min()),
            "max": float(m.inputs.view(np.float64)[np.isfinite(m.inputs.view(np.float64))].max()),
            "distinct_inputs": int(m.inputs.size),
        }
        for m in measured
        if m.inputs.size
    }
    (args.out / DOMAIN_NAME).write_text(
        json.dumps(
            {
                "note": (
                    "The closed interval each function is actually called on in the generation path. "
                    "A from-scratch exp/log only has to be right here — but it has to be right for "
                    "every double in here, not just the ones this sweep happened to hit."
                ),
                "domains": domain,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print(f"documents generated : {report.produced} ({len(report.failures)} refused)")
    for m in measured:
        s = stats[m.name]
        print(
            f"np.{m.name:<4} calls={s['calls']:<10} values={s['values_seen']:<12}"
            f" distinct={s['distinct_inputs']:<10} numpy!=libm={s['numpy_vs_libm_mismatches']}"
        )
        print(
            f"          finite range [{s['finite_input_min']!r}, {s['finite_input_max']!r}]"
            f"  nan={s['nan_inputs']} +inf={s['positive_infinity_inputs']}"
            f" -inf={s['negative_infinity_inputs']} subnormal={s['subnormal_inputs']}"
            f" domain_errors={s['domain_error_inputs']}"
        )
        print(f"          digest inputs={s['digests']['inputs'][:16]}… numpy={s['digests']['numpy'][:16]}…")  # type: ignore[index]
    print(f"distinct inputs     : {total_rows}")
    print(f"committed sample    : {sample_rows} rows -> {args.out / SAMPLE_NAME}")
    if args.full:
        print(f"complete stream     : {total_rows} rows -> {args.out / FULL_NAME} (not committed)")
    print(f"summary             : {args.out / SUMMARY_NAME}")
    print(f"domain              : {args.out / DOMAIN_NAME}")
    print(f"sweep elapsed       : {sweep_seconds:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
