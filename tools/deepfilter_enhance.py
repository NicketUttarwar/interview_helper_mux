#!/usr/bin/env python3
"""DeepFilterNet enhance CLI — runs inside ASSETS/local_deepfilter/venv."""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Enhance speech WAV with DeepFilterNet")
    parser.add_argument("--input-wav", type=str, help="Input noisy WAV (48 kHz mono preferred)")
    parser.add_argument("--output-wav", type=str, help="Output enhanced WAV path")
    parser.add_argument("--model", type=str, default="DeepFilterNet3")
    parser.add_argument("--postfilter", action="store_true")
    parser.add_argument("--compensate-delay", action="store_true")
    parser.add_argument("--verify", action="store_true", help="Load model only")
    args = parser.parse_args()

    try:
        from df import enhance, init_df
        import soundfile as sf
        import torch
    except ImportError as exc:
        print(f"DeepFilterNet import failed: {exc}", file=sys.stderr)
        return 1

    model, df_state, *_ = init_df(model_base_dir=args.model)
    if args.verify:
        print("OK — DeepFilterNet model loadable")
        return 0

    if not args.input_wav or not args.output_wav:
        print("--input-wav and --output-wav required unless --verify", file=sys.stderr)
        return 1

    audio, sr = sf.read(args.input_wav, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    audio_t = torch.from_numpy(audio).unsqueeze(0)
    enhanced = enhance(model, df_state, audio_t, pad=args.compensate_delay)
    out_np = enhanced.squeeze(0).detach().cpu().numpy()
    out_path = args.output_wav
    sf.write(out_path, out_np, sr, subtype="PCM_16")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
