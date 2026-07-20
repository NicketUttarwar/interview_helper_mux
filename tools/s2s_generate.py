#!/usr/bin/env python3
"""Local MLX S2S/TTS CLI — synthesize / convert / tone modes."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def _verify() -> int:
    try:
        import mlx_audio  # noqa: F401
    except ImportError as exc:
        print(json.dumps({"error": f"mlx_audio missing: {exc}"}))
        return 1
    print(json.dumps({"ok": True, "stack": "mlx-audio-tts"}))
    return 0


def _tone_prefix(tone: str | None) -> str:
    tone = str(tone or "neutral").lower()
    hints = {
        "analytical": "Deliver in a thoughtful, analytical host tone: ",
        "consumer": "Deliver in a warm, audience-facing consumer tone: ",
        "neutral": "",
    }
    return hints.get(tone, "")


def _run_tts(
    *,
    model_id: str,
    text: str,
    ref_audio: Path,
    out_wav: Path,
    context_audio: Path | None = None,
) -> None:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        cmd = [
            sys.executable,
            "-m",
            "mlx_audio.tts.generate",
            "--model",
            model_id,
            "--text",
            text,
            "--ref_audio",
            str(ref_audio),
            "--output",
            str(out_dir),
        ]
        if context_audio and context_audio.is_file():
            cmd.extend(["--context", str(context_audio)])
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "tts failed")[:500])
        generated = sorted(out_dir.glob("*.wav"))
        if not generated:
            raise RuntimeError("tts produced no wav output")
        generated[0].replace(out_wav)


def run_payload(payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("mode") or "synthesize").lower()
    model_id = str(payload.get("model_id") or payload.get("model") or "").strip()
    text = str(payload.get("text") or "").strip()
    ref = Path(str(payload.get("ref_audio") or ""))
    out_wav = Path(str(payload.get("out_wav") or payload.get("output") or ""))
    context = payload.get("context_audio")
    context_path = Path(str(context)) if context else None
    tone = payload.get("tone")

    if not model_id:
        raise ValueError("model_id required")
    if not ref.is_file():
        raise ValueError(f"ref_audio missing: {ref}")
    if not out_wav:
        raise ValueError("out_wav required")
    if mode in ("synthesize", "tone") and not text:
        raise ValueError("text required for synthesize/tone")

    spoken = _tone_prefix(tone) + text if mode == "tone" else text
    if mode == "convert":
        source = Path(str(payload.get("source_audio") or ""))
        if not source.is_file():
            raise ValueError(f"source_audio missing for convert: {source}")
        spoken = text or "Voice conversion reference take."

    _run_tts(
        model_id=model_id,
        text=spoken,
        ref_audio=ref,
        out_wav=out_wav,
        context_audio=context_path,
    )
    return {
        "ok": True,
        "mode": mode,
        "out_wav": str(out_wav),
        "model_id": model_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    if args.verify:
        return _verify()

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        print(json.dumps({"error": "invalid stdin JSON"}))
        return 1

    try:
        result = run_payload(payload)
    except Exception as exc:
        print(json.dumps({"error": str(exc)[:500]}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
