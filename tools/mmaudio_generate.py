#!/usr/bin/env python3
"""MMAudio text-to-audio CLI — runs inside ASSETS/local_mmaudio/venv."""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def _ffmpeg_to_wav(src: Path, dst: Path, sample_rate: int = 48000) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-sample_fmt",
            "s16",
            str(dst),
        ],
        check=True,
        capture_output=True,
    )


def _resolve_device(requested: str) -> str:
    import torch

    if requested and requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    log.warning("CUDA/MPS not available — running MMAudio on CPU")
    return "cpu"


def _native_generate(
    *,
    variant: str,
    prompt: str,
    negative_prompt: str,
    duration: float,
    cfg_strength: float,
    num_steps: int,
    seed: int,
    output_wav: Path,
    full_precision: bool,
    device: str,
) -> None:
    import torch
    import torchaudio
    from mmaudio.eval_utils import all_model_cfg, generate
    from mmaudio.model.flow_matching import FlowMatching
    from mmaudio.model.networks import get_my_mmaudio
    from mmaudio.model.utils.features_utils import FeaturesUtils

    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    if variant not in all_model_cfg:
        raise ValueError(f"Unknown MMAudio variant: {variant}")

    model = all_model_cfg[variant]
    model.download_if_needed()
    seq_cfg = model.seq_cfg

    resolved_device = _resolve_device(device)
    dtype = torch.float32 if full_precision or resolved_device == "cpu" else torch.bfloat16

    net = get_my_mmaudio(model.model_name).to(resolved_device, dtype).eval()
    net.load_weights(
        torch.load(model.model_path, map_location=resolved_device, weights_only=True),
    )

    rng = torch.Generator(device=resolved_device)
    rng.manual_seed(seed)
    fm = FlowMatching(min_sigma=0, inference_mode="euler", num_steps=num_steps)

    feature_utils = FeaturesUtils(
        tod_vae_ckpt=model.vae_path,
        synchformer_ckpt=model.synchformer_ckpt,
        enable_conditions=True,
        mode=model.mode,
        bigvgan_vocoder_ckpt=model.bigvgan_16k_path,
        need_vae_encoder=False,
    )
    feature_utils = feature_utils.to(resolved_device, dtype).eval()

    log.info("text-to-audio mode (no video)")
    clip_frames = sync_frames = None
    seq_cfg.duration = duration
    net.update_seq_lengths(seq_cfg.latent_seq_len, seq_cfg.clip_seq_len, seq_cfg.sync_seq_len)

    audios = generate(
        clip_frames,
        sync_frames,
        [prompt],
        negative_text=[negative_prompt],
        feature_utils=feature_utils,
        net=net,
        fm=fm,
        rng=rng,
        cfg_strength=cfg_strength,
    )
    audio = audios.float().cpu()[0]

    tmp_flac = output_wav.with_suffix(".mmaudio.flac")
    torchaudio.save(tmp_flac, audio, seq_cfg.sampling_rate)
    _ffmpeg_to_wav(tmp_flac, output_wav)
    if tmp_flac.is_file():
        tmp_flac.unlink()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Generate audio from text with MMAudio")
    parser.add_argument("--variant", type=str, default="large_44k_v2")
    parser.add_argument("--prompt", type=str, default="")
    parser.add_argument("--negative-prompt", type=str, default="")
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--cfg-strength", type=float, default=4.5)
    parser.add_argument("--num-steps", type=int, default=25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--output-wav", type=str, required=False)
    parser.add_argument("--repo", type=str, default="")
    parser.add_argument("--work-dir", type=str, default="")
    parser.add_argument("--model", type=str, default="")
    parser.add_argument("--full-precision", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--smoke-generate", action="store_true")
    args = parser.parse_args()

    variant = args.variant or args.model or "large_44k_v2"
    repo = Path(args.repo) if args.repo else None

    if args.verify:
        if repo and (repo / "mmaudio").is_dir():
            print("OK — MMAudio repo present")
        try:
            import mmaudio  # noqa: F401

            print("OK — mmaudio importable")
        except ImportError as exc:
            print(f"MMAudio verify failed: {exc}", file=sys.stderr)
            return 1
        if not args.smoke_generate:
            return 0
        smoke_out = Path(args.work_dir or "/tmp") / "mmaudio_smoke.wav"
        smoke_out.parent.mkdir(parents=True, exist_ok=True)
        try:
            _native_generate(
                variant=variant,
                prompt="soft documentary room tone, no vocals",
                negative_prompt="no vocals, no speech, no lyrics",
                duration=3.0,
                cfg_strength=4.0,
                num_steps=10,
                seed=42,
                output_wav=smoke_out,
                full_precision=args.full_precision,
                device=args.device,
            )
            print(f"OK — smoke generation wrote {smoke_out}")
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"MMAudio smoke generation failed: {exc}", file=sys.stderr)
            return 1

    if not args.output_wav:
        print("--output-wav required", file=sys.stderr)
        return 1

    out_wav = Path(args.output_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    try:
        _native_generate(
            variant=variant,
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            duration=args.duration,
            cfg_strength=args.cfg_strength,
            num_steps=args.num_steps,
            seed=args.seed,
            output_wav=out_wav,
            full_precision=args.full_precision,
            device=args.device,
        )
        return 0
    except ImportError as exc:
        print(f"MMAudio import failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
