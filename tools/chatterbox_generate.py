#!/usr/bin/env python3
"""Chatterbox zero-shot TTS CLI — JSON stdin, JSON stdout."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    raw = sys.stdin.read()
    payload = json.loads(raw or "{}")
    text = str(payload.get("text") or "").strip()
    ref_audio = Path(str(payload.get("ref_audio") or ""))
    out_wav = Path(str(payload.get("out_wav") or ""))
    model_id = str(payload.get("model_id") or "ResembleAI/chatterbox")

    if not text:
        print(json.dumps({"ok": False, "error": "text required"}))
        return 1
    if not ref_audio.is_file():
        print(json.dumps({"ok": False, "error": f"missing ref_audio: {ref_audio}"}))
        return 1
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    try:
        import torch
        import torchaudio
        from chatterbox.tts import ChatterboxTTS
    except ImportError as exc:
        print(json.dumps({"ok": False, "error": f"chatterbox import failed: {exc}"}))
        return 1

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = ChatterboxTTS.from_pretrained(model_id, device=device)
    wav = model.generate(text, audio_prompt_path=str(ref_audio))
    if wav.ndim > 1:
        wav = wav.squeeze(0)
    torchaudio.save(str(out_wav), wav.unsqueeze(0).cpu(), model.sr)
    print(json.dumps({"ok": True, "out_wav": str(out_wav), "model_id": model_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
