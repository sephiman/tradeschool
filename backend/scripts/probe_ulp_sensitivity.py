# SPDX-License-Identifier: AGPL-3.0-only
"""Does a 1-ulp `exp`/`log` difference actually move a fingerprint? Measure it, don't argue it.

glibc and fdlibm/`StrictMath` disagree by exactly 1 ulp on 4.86% of this course's `exp` arguments and
0.79% of its `log` arguments. That is a fact about the libraries, not an answer about the output —
everything published is rounded, so a 1-ulp wobble only shows if a value sits on a rounding boundary
or flips a discrete decision (a retry loop, an `argmax`, an `int()`).

This replaces the ufuncs with the real result plus a deterministic 1-ulp perturbation on a chosen
FRACTION of values, keyed on the input's bits so it is a pure function of the argument as a real
libm's error is, then re-fingerprints the 84 goldens plus a wide sweep. It reproduces the RATE and
MAGNITUDE of the disagreement, not which inputs disagree — the right instrument for "how fragile is
the output?" and the wrong one for a parity claim.

`--ulps` above 1 is the headroom probe: how much error the output could absorb before anything moved.

Usage:
    python scripts/probe_ulp_sensitivity.py [--trials N] [--seeds N] [--ulps N]
                                            [--exp-rate F] [--log-rate F]
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from scripts.generation_workload import fingerprints  # noqa: E402

sys.path.insert(0, str(_BACKEND / "tests"))

from test_golden_exercise_mode import GOLDEN, _current  # type: ignore[import-not-found]  # noqa: E402

#: The measured glibc-vs-fdlibm disagreement rates over this path's distinct inputs.
MEASURED_EXP_RATE = 47_040 / 962_953
MEASURED_LOG_RATE = 8_455 / 1_071_664

#: SplitMix64's multiplier, so consecutive bit patterns scatter instead of banding.
_MIX = 0x9E3779B97F4A7C15


def _perturb(out: np.ndarray, arg: np.ndarray, rate: float, salt: int, ulps: int) -> np.ndarray:
    """Move `rate` of `out` by `ulps` ulp, selected from the INPUT's bits so it is a pure function of
    the argument — calling `exp(x)` twice in one run cannot give two answers."""
    if out.ndim == 0:
        out = out.reshape(1)
        scalar = True
    else:
        scalar = False
    bits = np.ascontiguousarray(arg, dtype=np.float64).ravel().view(np.uint64)
    if bits.size != out.size:
        return out.reshape(()) if scalar else out
    mixed = (bits ^ np.uint64(salt)) * np.uint64(_MIX)
    mixed ^= mixed >> np.uint64(29)
    # Two independent decisions from one hash: whether this value differs, and which way.
    selected = (mixed % np.uint64(1_000_000)) < np.uint64(int(rate * 1_000_000))
    upward = (mixed >> np.uint64(40)) & np.uint64(1) == np.uint64(1)
    target = np.where(upward, np.inf, -np.inf)
    moved = out
    for _ in range(ulps):  # successive steps, so the walk stays exact at any magnitude
        moved = np.nextafter(moved, target)
    result = np.where(selected & np.isfinite(out), moved, out)
    return result.reshape(()) if scalar else result


@contextmanager
def perturbed(exp_rate: float, log_rate: float, salt: int, ulps: int = 1) -> Iterator[None]:
    """Run the block with `np.exp`/`np.log` off by `ulps` ulp on the given fraction of results."""
    real_exp, real_log = np.exp, np.log

    def wrapped_exp(x: Any, *args: Any, **kwargs: Any) -> Any:
        arg = np.asarray(x, dtype=np.float64)
        got = np.asarray(real_exp(arg, *args, **kwargs), dtype=np.float64)
        return _perturb(got, arg, exp_rate, salt, ulps)

    def wrapped_log(x: Any, *args: Any, **kwargs: Any) -> Any:
        arg = np.asarray(x, dtype=np.float64)
        got = np.asarray(real_log(arg, *args, **kwargs), dtype=np.float64)
        return _perturb(got, arg, log_rate, salt, ulps)

    np.exp = wrapped_exp  # type: ignore[assignment]
    np.log = wrapped_log  # type: ignore[assignment]
    try:
        yield
    finally:
        np.exp = real_exp
        np.log = real_log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--trials", type=int, default=12, help="independent perturbation patterns")
    parser.add_argument("--exp-rate", type=float, default=MEASURED_EXP_RATE)
    parser.add_argument("--log-rate", type=float, default=MEASURED_LOG_RATE)
    parser.add_argument(
        "--ulps", type=int, default=1,
        help="size of the perturbation in ulp (1 is what two correct libms can differ by; larger "
             "values map out how much headroom the fingerprints have)",
    )
    parser.add_argument(
        "--seeds", type=int, default=4,
        help="probe seeds per injector kind for the WIDE sweep, which covers figure mode too "
             "(the committed 84 exercise goldens are always checked as well)",
    )
    args = parser.parse_args(argv)

    def measure() -> dict[str, str]:
        # Both halves: the committed goldens, and a wide sweep covering figure mode's own hooks.
        out = {f"golden:{k}": v for k, v in _current().items()}
        out.update(fingerprints(tuple(range(args.seeds))))
        return out

    baseline = measure()
    drift = {
        k[len("golden:"):]: v
        for k, v in baseline.items()
        if k.startswith("golden:") and v != GOLDEN.get(k[len("golden:"):])
    }
    if drift:
        print(f"WARNING: {len(drift)} fingerprints already differ from GOLDEN before perturbing:")
        for k in sorted(drift):
            print(f"  {k}: golden={GOLDEN.get(k)} current={drift[k]}")

    print(
        f"perturbing exp on {args.exp_rate:.3%} of results and log on {args.log_rate:.3%}, "
        f"by exactly {args.ulps} ulp, over {args.trials} independent patterns"
    )
    print(f"watching {len(baseline)} fingerprints ({len(GOLDEN)} committed goldens + a wide sweep)")
    moved_any: set[str] = set()
    per_trial: list[int] = []
    for trial in range(args.trials):
        with perturbed(args.exp_rate, args.log_rate, salt=0xA5A5_0000 + trial, ulps=args.ulps):
            current = measure()
        moved = {k for k in baseline if current.get(k) != baseline[k]}
        moved_any |= moved
        per_trial.append(len(moved))
        print(f"  trial {trial:>2}: {len(moved):>4}/{len(baseline)} fingerprints moved")

    total = len(baseline)
    goldens_moved = sorted(k for k in moved_any if k.startswith("golden:"))
    print()
    print(f"fingerprints per trial : {total}")
    print(f"moved, worst trial     : {max(per_trial)}")
    print(f"moved, best trial      : {min(per_trial)}")
    print(f"moved in >=1 trial     : {len(moved_any)}/{total}  (committed goldens: {len(goldens_moved)})")
    if moved_any:
        print("  " + ", ".join(sorted(moved_any)[:12]) + (" ..." if len(moved_any) > 12 else ""))
    print()
    print(
        f"VERDICT: generated output IS sensitive to a {args.ulps}-ulp exp/log difference."
        if moved_any
        else f"VERDICT: nothing moved — the output survives a {args.ulps}-ulp exp/log difference."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
