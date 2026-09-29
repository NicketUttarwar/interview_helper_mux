#!/usr/bin/env python3
"""Speaker diarization via NVIDIA Sortformer, for hosts without MLX.

  python tools/diarize_sortformer.py --audio in.wav --output turns.json
  python tools/diarize_sortformer.py --verify

Runs inside its own venv (``local_diarize``) because NeMo pulls torch and a large
dependency tree, while the speech venv is deliberately lean: faster-whisper runs
on CTranslate2 and has no torch at all. Keeping them apart means installing
diarization cannot break working transcription.

Model is ``nvidia/diar_sortformer_4spk-v1``, the same model Apple Silicon uses
through its MLX port (``mlx-community/diar_sortformer_4spk-v1-fp32``), so both
platforms diarize with the same weights. It is **ungated**, so no Hugging Face
token or licence click is needed, unlike pyannote.

Licence note: the model is CC-BY-NC-4.0, non-commercial. That is inherited from
the macOS default rather than introduced here, but it applies to a commercially
published episode and is worth a decision before shipping one.

Output contract, consumed by ``tools/stt_backend_faster_whisper.py``:

    {"turns": [{"start_ms": int, "end_ms": int, "speaker_id": "spk_N"}, ...],
     "speakers": ["spk_0", ...], "model_id": "...", "device": "cuda|cpu"}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

MODEL_ID = "nvidia/diar_sortformer_4spk-v1"


def _device() -> str:
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def verify() -> dict[str, Any]:
    try:
        import nemo  # noqa: F401
        from nemo.collections.asr.models import SortformerEncLabelModel  # noqa: F401
    except ImportError as exc:
        return {"error": f"nemo_toolkit missing: {exc}"}
    return {"ok": True, "stack": "nemo-sortformer", "model_id": MODEL_ID, "device": _device()}


def _normalise_speaker(raw: str) -> str:
    """Sortformer emits ``speaker_0``; the words contract wants ``spk_0``."""
    s = str(raw or "").strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    return f"spk_{int(digits)}" if digits else (s or "spk_0")


def diarize(audio: Path) -> dict[str, Any]:
    from nemo.collections.asr.models import SortformerEncLabelModel

    model = SortformerEncLabelModel.from_pretrained(MODEL_ID)
    model.eval()
    raw = model.diarize(audio=[str(audio)], batch_size=1)
    rows = raw[0] if raw and isinstance(raw, list) else []

    turns: list[dict[str, Any]] = []
    for row in rows:
        # Each row is an RTTM-ish "start end speaker" string.
        parts = str(row).split()
        if len(parts) < 3:
            continue
        try:
            start_s, end_s = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        if end_s <= start_s:
            continue
        turns.append(
            {
                "start_ms": int(start_s * 1000),
                "end_ms": int(end_s * 1000),
                "speaker_id": _normalise_speaker(parts[2]),
            }
        )
    turns.sort(key=lambda t: (t["start_ms"], t["end_ms"]))
    speakers = sorted({t["speaker_id"] for t in turns})
    return {
        "turns": turns,
        "speakers": speakers,
        "model_id": MODEL_ID,
        "device": _device(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--audio", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    if args.verify:
        payload = verify()
        print(json.dumps(payload))
        return 0 if payload.get("ok") else 1

    if not args.audio or not args.audio.is_file():
        print(json.dumps({"error": "missing --audio"}))
        return 1
    try:
        payload = diarize(args.audio)
    except Exception as exc:  # noqa: BLE001 - CLI boundary, report as JSON
        print(json.dumps({"error": f"{type(exc).__name__}: {str(exc)[:400]}"}))
        return 1

    out = json.dumps(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out + "\n", encoding="utf-8")
        # Keep stdout small; NeMo is extremely chatty on stderr.
        print(json.dumps({"ok": True, "turns": len(payload["turns"]), "speakers": payload["speakers"]}))
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
