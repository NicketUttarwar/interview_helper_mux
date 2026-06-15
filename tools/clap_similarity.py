#!/usr/bin/env python3
"""CLAP text–audio similarity — runs inside ASSETS/local_mmaudio/venv."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _respond(payload: dict[str, object], *, exit_code: int = 0) -> None:
    print(json.dumps(payload))
    raise SystemExit(exit_code)


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        _respond({"available": False, "error": f"invalid_json: {exc}"})

    if not isinstance(payload, dict):
        _respond({"available": False, "error": "payload_must_be_object"})

    wav_path = Path(str(payload.get("wav_path") or ""))
    text = str(payload.get("text") or "").strip()
    model_id = str(payload.get("model_id") or "laion/clap-htsat-fused")

    if not wav_path.is_file():
        _respond({"available": False, "error": f"missing_wav: {wav_path}"})
    if not text:
        _respond({"available": False, "error": "empty_text"})

    try:
        import librosa
        import torch
        from transformers import ClapModel, ClapProcessor
    except ImportError as exc:
        _respond({"available": False, "error": f"missing_deps: {exc}"})

    try:
        processor = ClapProcessor.from_pretrained(model_id)
        model = ClapModel.from_pretrained(model_id)
        model.eval()
        audio, _sr = librosa.load(str(wav_path), sr=48000, mono=True)
        inputs = processor(
            text=[text],
            audios=audio,
            sampling_rate=48000,
            return_tensors="pt",
            padding=True,
        )
        with torch.no_grad():
            outputs = model(**inputs)
            audio_embed = outputs.audio_embeds
            text_embed = outputs.text_embeds
            score = float(torch.nn.functional.cosine_similarity(audio_embed, text_embed).item())
    except Exception as exc:  # noqa: BLE001 — subprocess must always emit JSON
        _respond({"available": False, "error": str(exc)[:500]})

    _respond({"available": True, "score": round(score, 6), "model_id": model_id})


if __name__ == "__main__":
    main()
