#!/usr/bin/env python3
"""Real-world MusicGen ladder probe (GPU-first; large→medium→small by default).

Defaults follow shipped config (large primary, device=auto→MPS on Apple Silicon).

Examples:

  # Current ship path (large → medium → small on GPU)
  .venv/bin/python tools/musicgen_ladder_probe.py

  # Cold-open length bed
  .venv/bin/python tools/musicgen_ladder_probe.py --role theme_cold_open --palette-kind full_bed --duration 8
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--duration", type=float, default=6.0)
    ap.add_argument(
        "--primary-timeout",
        type=int,
        default=None,
        help="Hang budget for primary model (default: musicgen.request_timeout_sec)",
    )
    ap.add_argument(
        "--step-timeout",
        type=int,
        default=None,
        help="Hang budget for ladder step-downs (default: musicgen.step_down_timeout_sec or 300)",
    )
    ap.add_argument(
        "--force-large-ladder",
        action="store_true",
        help="Start ladder at facebook/musicgen-large (1765 diagnosis) instead of shipped primary",
    )
    ap.add_argument(
        "--device",
        default=None,
        help="Override device (default: shipped musicgen.device, usually auto→mps)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output wav (default ASSETS/local_musicgen/probe/stinger.wav)",
    )
    ap.add_argument("--role", default="theme_emphasis")
    ap.add_argument("--palette-kind", default="stinger")
    ap.add_argument("--seed", type=int, default=1765)
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))

    # Live probes should use the real GPU settle; tests set this to 0.
    os.environ.setdefault("INTERVIEW_MUX_GPU_COOLDOWN_SEC", "5")

    from interview_mux.music_motif import compile_musicgen_prompt, default_motif_family
    from interview_mux import musicgen_runner as mg

    brief = {
        "show_identity": {
            "genre_hint": "acoustic conversational documentary instrumental",
            "mood": "determined",
            "instrumentation_prefs": [
                "acoustic guitar",
                "punchy piano",
                "warm electric bass",
                "soft strings",
            ],
            "key_center": "G",
            "scale_or_mode": "major_bright",
        },
        "motif_seeds": {"keywords": ["conviction", "gratitude", "shared ownership"]},
        "narrative_spine": {
            "acts": [
                {"title": "Bootstrapped beginnings", "mood": "hopeful", "energy": "calm"},
                {"title": "Capital and stewardship", "mood": "tense", "energy": "rising"},
                {"title": "Employee payout gratitude", "mood": "triumphant", "energy": "lift"},
            ]
        },
    }
    motif = default_motif_family(brief)
    prompt, neg = compile_musicgen_prompt(
        brief=brief,
        motif=motif,
        role=args.role,
        palette_kind=args.palette_kind,
        wpm=140,
    )

    out = args.out or (root / "ASSETS" / "local_musicgen" / "probe" / "stinger.wav")
    out.parent.mkdir(parents=True, exist_ok=True)

    shipped = dict(mg.musicgen_cfg() or {})
    primary = (
        "facebook/musicgen-large"
        if args.force_large_ladder
        else str(shipped.get("model_id") or "facebook/musicgen-large")
    )
    device = str(args.device or shipped.get("device") or "auto")
    primary_timeout = int(
        args.primary_timeout
        if args.primary_timeout is not None
        else (shipped.get("request_timeout_sec") or 480)
    )
    step_timeout = int(
        args.step_timeout
        if args.step_timeout is not None
        else (shipped.get("step_down_timeout_sec") or 300)
    )

    base = dict(shipped)
    base.update(
        {
            "model_id": primary,
            "device": device,
            "prefer_medium_on_cpu": False,
            "request_timeout_sec": primary_timeout,
            "cpu_request_timeout_sec": min(
                primary_timeout, int(shipped.get("cpu_request_timeout_sec") or 300)
            ),
            "step_down_timeout_sec": step_timeout,
            "mmaudio_backup_on_stub": False,
        }
    )
    mg.musicgen_cfg = lambda: base  # type: ignore[assignment]

    effective = mg.effective_musicgen_device()
    ladder_preview = [primary]
    for lighter in ("facebook/musicgen-medium", "facebook/musicgen-small"):
        if lighter != primary and lighter not in ladder_preview:
            ladder_preview.append(lighter)

    print("prompt:", prompt)
    print(f"device_cfg={device} effective={effective}")
    print(f"ladder: {' → '.join(m.split('/')[-1] for m in ladder_preview)}")
    print(f"primary_timeout={primary_timeout}s step_timeout={step_timeout}s")
    t0 = time.monotonic()
    meta = mg.generate_music_clip(
        prompt=prompt,
        negative_prompt=neg,
        duration_sec=float(args.duration),
        out_wav=out,
        role=args.role,
        seed=int(args.seed),
    )
    elapsed = time.monotonic() - t0
    report = {
        "elapsed_sec": round(elapsed, 1),
        "device_cfg": device,
        "effective_device_at_start": effective,
        "device_used": meta.get("device"),
        "backend": meta.get("backend"),
        "winning_model_id": meta.get("model_id"),
        "fidelity_step": meta.get("fidelity_step"),
        "model_ladder": meta.get("model_ladder"),
        "primary_model_id": primary,
        "force_large_ladder": bool(args.force_large_ladder),
        "musicgen_timeout": meta.get("musicgen_timeout"),
        "musicgen_abort": meta.get("musicgen_abort"),
        "musicgen_error": (meta.get("musicgen_error") or "")[:240] or None,
        "out_wav": str(out),
        "bytes": out.stat().st_size if out.is_file() else 0,
        "role": args.role,
        "palette_kind": args.palette_kind,
        "duration_sec": float(args.duration),
        "inspired_by": "exec_1765_1311e28fffa1_20260811T230442Z cold_open hang → MMAudio",
    }
    report_path = out.with_suffix(".ladder_report.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"wrote {report_path}")

    if not out.is_file() or out.stat().st_size < 1000:
        print("FAIL: no listenable wav", file=sys.stderr)
        return 1
    if report["backend"] == "musicgen":
        print(
            f"SUCCESS on {report['winning_model_id']} "
            f"({report['fidelity_step']}) device={report.get('device_used')}"
        )
        if report["primary_model_id"] != report["winning_model_id"]:
            print(
                f"NOTE: primary {report['primary_model_id']} did not win; "
                f"ladder stepped down to {report['winning_model_id']}"
            )
    else:
        print(
            f"MusicGen ladder exhausted → {report['backend']} "
            f"(primary={report['primary_model_id']} failed; step-downs also failed)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
