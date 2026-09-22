#!/usr/bin/env python3
"""Chatterbox zero-shot TTS CLI — JSON stdin, JSON stdout.

API contract (chatterbox 0.1.x): ChatterboxTTS.from_pretrained(device) only.
``model_id`` in the payload is echoed for audit; weights come from the package default.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"invalid stdin JSON: {exc}"}))
        return 1

    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "error": "payload must be object"}))
        return 1

    text = str(payload.get("text") or "").strip()
    ref_audio = Path(str(payload.get("ref_audio") or ""))
    out_wav = Path(str(payload.get("out_wav") or ""))
    # Audit-only; chatterbox 0.1.x from_pretrained(device) does not take model_id.
    model_id = str(payload.get("model_id") or "ResembleAI/chatterbox")

    if not text:
        print(json.dumps({"ok": False, "error": "text required"}))
        return 1
    if not ref_audio.is_file():
        print(json.dumps({"ok": False, "error": f"missing ref_audio: {ref_audio}"}))
        return 1
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    try:
        import os
        import torch
        import torchaudio
        import perth
        # perth may leave PerthImplicitWatermarker=None when perth_net deps missing
        # (e.g. pkg_resources). ChatterboxTTS.__init__ calls it unconditionally.
        if getattr(perth, "PerthImplicitWatermarker", None) is None:
            from perth.dummy_watermarker import DummyWatermarker

            perth.PerthImplicitWatermarker = DummyWatermarker  # type: ignore[misc, assignment]
        from chatterbox.tts import ChatterboxTTS
    except ImportError as exc:
        print(json.dumps({"ok": False, "error": f"chatterbox import failed: {exc}"}))
        return 1

    try:
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        device_pref = str(payload.get("device") or "auto").strip().lower()
        mps_ok = bool(torch.backends.mps.is_available() and torch.backends.mps.is_built())
        if device_pref in {"", "auto"}:
            device = "mps" if mps_ok else "cpu"
        elif device_pref == "mps":
            device = "mps" if mps_ok else "cpu"
        else:
            device = "cpu"
        # chatterbox 0.1.7: from_pretrained(device) — do NOT pass model_id.
        # Keep contract JSON on stdout: libraries dump progress/warnings there.
        _stdout = sys.stdout
        try:
            sys.stdout = sys.stderr
            try:
                model = ChatterboxTTS.from_pretrained(device)
            except Exception as mps_exc:
                if device != "cpu":
                    print(
                        f"chatterbox_mps_failed falling_back=cpu err={mps_exc}",
                        file=sys.stderr,
                    )
                    device = "cpu"
                    model = ChatterboxTTS.from_pretrained(device)
                else:
                    raise
            wav = model.generate(text, audio_prompt_path=str(ref_audio))
            if wav.ndim > 1:
                wav = wav.squeeze(0)
            # Pipeline VO QA / wave.open require PCM s16le (not float32).
            audio = wav.detach().cpu().float().clamp(-1.0, 1.0).unsqueeze(0)
            torchaudio.save(
                str(out_wav),
                audio,
                int(model.sr),
                encoding="PCM_S",
                bits_per_sample=16,
            )
        finally:
            sys.stdout = _stdout
    except Exception as exc:  # noqa: BLE001 — CLI must always emit JSON
        print(json.dumps({"ok": False, "error": str(exc)[:500], "model_id": model_id}))
        return 1

    print(json.dumps({"ok": True, "out_wav": str(out_wav), "model_id": model_id, "device": device}))
    # Hard-exit after successful write — avoid MPS cache teardown hang (WS4).
    try:
        import os

        os._exit(0)
    except Exception:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
