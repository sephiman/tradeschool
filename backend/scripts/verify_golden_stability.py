# SPDX-License-Identifier: AGPL-3.0-only
"""Is this machine's chart generation bit-identical to another machine's? One digest answers it.

Phase W1's done-criterion. Two things here dispatch on the CPU without showing it in the source:
NumPy links `scipy-openblas` built with `DYNAMIC_ARCH`, and its `exp`/`log` kernels pick a SIMD width.
So the only honest test is to run the same sweep on two microarchitectures and compare.

Prints one digest over every fingerprint of the whole workload (both modes, every injector and label,
50 probe seeds, plus the frozen content figures) with the environment that produced it, and re-checks
all 90 COMMITTED fingerprints — the 84 in `test_golden_exercise_mode.py` and the 6 pins in
`test_generation_numerics.py` — separately, since "the digest differs but the pins hold" and "both
differ" are different diagnoses. Exit code is 0 only if all 90 hold.

The digest hashes whole documents while a pin hashes a sub-structure, so it cannot contain their
values; what it contains is the same DOCUMENTS, all 84 golden ones verified byte-identical inside the
sweep — which is why the workload sweeps the goldens' own divergence target list as its own config.

Usage:
    python scripts/verify_golden_stability.py [--seeds N] [--dump FILE]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.generation_workload import PROBE_SEEDS, fingerprints

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from test_generation_numerics import PINNED, current_pins  # type: ignore[import-not-found]
from test_golden_exercise_mode import GOLDEN, _current  # type: ignore[import-not-found]


def _cpu_model() -> str:
    """The CPU's marketing name — what tells a reader the two machines really differ."""
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def _numpy_build_summary() -> dict[str, str]:
    """The BLAS/LAPACK NumPy is linked against and the SIMD it chose — what can move the numbers
    without anything in the repo changing."""
    out: dict[str, str] = {"numpy": np.__version__}
    cfg = getattr(np.__config__, "CONFIG", None)
    if isinstance(cfg, dict):
        for kind in ("blas", "lapack"):
            info = cfg.get("Build Dependencies", {}).get(kind, {})
            if isinstance(info, dict):
                out[kind] = " ".join(
                    str(info.get(k, "")) for k in ("name", "version", "openblas configuration")
                ).strip()
        simd = cfg.get("SIMD Extensions", {})
        if isinstance(simd, dict):
            out["simd_baseline"] = ",".join(simd.get("baseline") or []) or "-"
            out["simd_found"] = ",".join(simd.get("found") or []) or "-"
    return out


def _digest(prints: dict[str, str]) -> str:
    """SHA-256 over `key=value` lines in sorted key order."""
    body = "\n".join(f"{k}={prints[k]}" for k in sorted(prints))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--seeds", type=int, default=len(PROBE_SEEDS),
        help=f"probe seeds per injector kind (default {len(PROBE_SEEDS)}; the digest is only "
             f"comparable between runs that used the SAME count)",
    )
    parser.add_argument(
        "--dump", type=Path, default=None,
        help="also write every per-document fingerprint here, for diffing two machines",
    )
    args = parser.parse_args(argv)

    seeds = tuple(range(args.seeds))
    print(f"sweeping the generation path over {len(seeds)} probe seeds per injector kind ...")
    started = time.monotonic()
    prints = fingerprints(seeds)
    elapsed = time.monotonic() - started

    # Checked against their committed baselines, not each other: a mismatch here beats a digest diff.
    committed: list[tuple[str, dict[str, str], dict[str, str]]] = [
        ("golden", GOLDEN, _current()),
        ("pinned", PINNED, current_pins()),
    ]
    moved: dict[str, tuple[str | None, str]] = {}
    missing: list[str] = []
    for label, baseline, current in committed:
        moved.update(
            {f"{label}/{k}": (baseline.get(k), v) for k, v in current.items() if baseline.get(k) != v}
        )
        missing.extend(f"{label}/{k}" for k in sorted(set(baseline) - set(current)))
    checked = sum(len(current) for _, _, current in committed)

    exercise = sum(1 for k in prints if k.startswith("exercise:"))
    figure = sum(1 for k in prints if k.startswith("figure:"))
    refused = sorted(k for k, v in prints.items() if v == "REFUSED")
    digest = _digest(prints)
    env = {
        "cpu": _cpu_model(),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "libc": " ".join(platform.libc_ver()),
        **_numpy_build_summary(),
    }

    print()
    print("=" * 78)
    print(f"GENERATION DIGEST  {digest}")
    print("=" * 78)
    print(f"documents          {len(prints)} ({exercise} exercise + {figure} figure)")
    print(f"probe seeds        {len(seeds)}")
    print(f"refused            {len(refused)}" + (f"  {refused[:6]}" if refused else ""))
    print(f"committed          {'OK' if not moved and not missing else 'MOVED'}"
          f"  ({checked} fingerprints checked: {len(GOLDEN)} golden + {len(PINNED)} pinned)")
    for key, (was, now) in sorted(moved.items()):
        print(f"    {key}: committed={was} current={now}")
    for key in missing:
        print(f"    {key}: MISSING from the current run")
    print(f"elapsed            {elapsed:.1f}s")
    print()
    for key in sorted(env):
        print(f"  {key:<16} {env[key]}")
    print()
    print("Compare the digest with a second machine of a different microarchitecture. Identical")
    print("digests AND a zero exit code together certify the contract surface; if the digests")
    print("differ, run both with --dump and diff the files.")

    if args.dump:
        args.dump.write_text(
            json.dumps(
                {
                    "digest": digest,
                    "probe_seeds": len(seeds),
                    "environment": env,
                    "committed_moved": {k: list(v) for k, v in moved.items()},
                    "committed_missing": missing,
                    "fingerprints": prints,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nper-document fingerprints written to {args.dump}")

    return 0 if not moved and not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
