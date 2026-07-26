#!/usr/bin/env python3
"""QA check for mastered WAV (BUILD-052/070)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.master_qc import TARGETS, FlowName, verify_master  # noqa: E402


def _parse_flow(raw: str | None) -> FlowName | None:
    if raw is None:
        return None
    if raw not in TARGETS:
        valid = ", ".join(sorted(TARGETS.keys()))
        raise ValueError(f"Invalid --flow {raw!r}; expected one of: {valid}")
    return raw  # type: ignore[return-value]


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python tools/verify_master.py <master.wav> [--flow podcast]")
        sys.exit(1)

    args = sys.argv[1:]
    path = Path(args[0])
    flow_arg: str | None = None
    if len(args) >= 3 and args[1] == "--flow":
        flow_arg = args[2]

    if not path.is_file():
        print(f"Not found: {path}")
        sys.exit(1)

    try:
        result = verify_master(path, flow=_parse_flow(flow_arg))
    except Exception as exc:
        print(f"FAIL: {path}")
        print(f"  reason: {exc}")
        sys.exit(1)

    m = result.metrics
    print(f"QA target: {result.flow}")
    print(
        f"  metrics: duration={m.duration_seconds:.2f}s sample_rate={m.sample_rate_hz}Hz "
        f"channels={m.channels} integrated_lufs={m.integrated_lufs:.2f} true_peak_dbtp={m.true_peak_dbtp:.2f}"
    )
    for line in result.checks:
        print(f"  - {line}")

    if result.ok:
        print(f"OK: {path}")
        sys.exit(0)

    print(f"FAIL: {path}")
    for err in result.failures:
        print(f"  - {err}")
    sys.exit(1)


if __name__ == "__main__":
    main()
