#!/usr/bin/env python3
"""Generate instrumental music with MusicGen (MLX or transformers) from a JSON request file."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: musicgen_generate.py <request.json>", file=sys.stderr)
        return 2
    req_path = Path(sys.argv[1])
    req = json.loads(req_path.read_text(encoding="utf-8"))
    prompt = str(req.get("prompt") or "")
    duration = float(req.get("duration_sec") or 12.0)
    out_wav = Path(str(req.get("out_wav")))
    model_id = str(req.get("model_id") or "facebook/musicgen-medium")
    seed = req.get("seed")
    melody_wav = req.get("melody_wav")
    use_melody = bool(req.get("use_melody_conditioning", True))

    # Prefer MLX ports when installed.
    try:
        return _generate_mlx(
            prompt=prompt,
            duration=duration,
            out_wav=out_wav,
            model_id=model_id,
            seed=seed,
            melody_wav=melody_wav if use_melody else None,
        )
    except Exception as mlx_exc:
        print(f"mlx_musicgen_unavailable: {mlx_exc}", file=sys.stderr)

    try:
        return _generate_transformers(
            prompt=prompt,
            duration=duration,
            out_wav=out_wav,
            model_id=model_id,
            seed=seed,
        )
    except Exception as tf_exc:
        print(f"transformers_musicgen_unavailable: {tf_exc}", file=sys.stderr)
        return 1


def _generate_mlx(
    *,
    prompt: str,
    duration: float,
    out_wav: Path,
    model_id: str,
    seed: object,
    melody_wav: str | None,
) -> int:
    # musicgen-mlx / mlx-audiocraft style APIs vary; try common entry points.
    try:
        from mlx_audiocraft import MusicGen  # type: ignore

        model = MusicGen.get_pretrained(model_id.replace("facebook/", ""))
        model.set_generation_params(duration=float(duration))
        wav = model.generate([prompt])
        _save_tensor_wav(wav, out_wav, sr=32000)
        return 0
    except Exception:
        pass
    try:
        import musicgen_mlx  # type: ignore

        audio = musicgen_mlx.generate(prompt=prompt, duration=float(duration), model=model_id)
        _save_array_wav(audio, out_wav, sr=32000)
        return 0
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


def _generate_transformers(
    *,
    prompt: str,
    duration: float,
    out_wav: Path,
    model_id: str,
    seed: object,
) -> int:
    import numpy as np
    import torch
    from transformers import AutoProcessor, MusicgenForConditionalGeneration

    processor = AutoProcessor.from_pretrained(model_id)
    model = MusicgenForConditionalGeneration.from_pretrained(model_id)
    if seed is not None:
        torch.manual_seed(int(seed))
    inputs = processor(text=[prompt], padding=True, return_tensors="pt")
    # ~50 tokens/sec of audio at 32k for MusicGen; approximate.
    max_new = max(64, int(float(duration) * 50))
    with torch.no_grad():
        audio_values = model.generate(**inputs, max_new_tokens=max_new)
    data = audio_values[0, 0].cpu().numpy()
    sr = int(getattr(model.config, "audio_encoder", None) and getattr(model.config.audio_encoder, "sampling_rate", 32000) or 32000)
    _save_array_wav(data, out_wav, sr=sr)
    return 0


def _save_tensor_wav(wav: object, out_wav: Path, *, sr: int) -> None:
    import numpy as np

    arr = np.array(wav).squeeze()
    _save_array_wav(arr, out_wav, sr=sr)


def _save_array_wav(data: object, out_wav: Path, *, sr: int) -> None:
    import numpy as np
    from scipy.io import wavfile

    arr = np.asarray(data, dtype=np.float32).squeeze()
    if arr.ndim > 1:
        arr = arr[0]
    # Resample to 48k mono for pipeline consistency when possible.
    target = 48000
    if sr != target and arr.size > 0:
        x_old = np.linspace(0.0, 1.0, num=arr.shape[0], endpoint=False)
        n_new = int(arr.shape[0] * target / sr)
        x_new = np.linspace(0.0, 1.0, num=n_new, endpoint=False)
        arr = np.interp(x_new, x_old, arr).astype(np.float32)
        sr = target
    peak = float(np.max(np.abs(arr))) or 1.0
    arr = (arr / peak * 0.9 * 32767.0).astype(np.int16)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(str(out_wav), sr, arr)


if __name__ == "__main__":
    raise SystemExit(main())
