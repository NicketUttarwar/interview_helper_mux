#!/usr/bin/env python3
"""Enhance multiple WAV files with a single DeepFilterNet model load (stdin JSON)."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _emit_progress(current: int, total: int) -> None:
    print(f"PROGRESS {current}/{total}", file=sys.stderr, flush=True)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON stdin: {exc}", file=sys.stderr)
        return 1

    jobs = payload.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        print("jobs array required", file=sys.stderr)
        return 1

    model = str(payload.get("model") or "DeepFilterNet3")
    postfilter = bool(payload.get("postfilter"))
    compensate_delay = bool(payload.get("compensate_delay", True))

    try:
        from df import enhance, init_df
        import soundfile as sf
        import torch
    except ImportError as exc:
        print(f"DeepFilterNet import failed: {exc}", file=sys.stderr)
        return 1

    model_obj, df_state, *_ = init_df(model_base_dir=model)
    total = len(jobs)
    for i, row in enumerate(jobs, start=1):
        if not isinstance(row, dict):
            print(f"Job {i} must be an object", file=sys.stderr)
            return 1
        input_wav = Path(str(row.get("input") or ""))
        output_wav = Path(str(row.get("output") or ""))
        if not input_wav.is_file():
            print(f"Input not found: {input_wav}", file=sys.stderr)
            return 1
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        _emit_progress(i, total)
        audio, sr = sf.read(str(input_wav), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        audio_t = torch.from_numpy(audio).unsqueeze(0)
        enhanced = enhance(model_obj, df_state, audio_t, pad=compensate_delay)
        out_np = enhanced.squeeze(0).detach().cpu().numpy()
        sf.write(str(output_wav), out_np, sr, subtype="PCM_16")
        print(f"Wrote {output_wav}", file=sys.stderr, flush=True)

    print(json.dumps({"ok": True, "count": total}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
