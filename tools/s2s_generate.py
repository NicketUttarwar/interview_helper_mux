#!/usr/bin/env python3
"""Local MLX S2S/TTS CLI — synthesize / convert / tone modes."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
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


def build_tts_argv(
    *,
    model_id: str,
    text: str,
    ref_audio: Path,
    file_prefix: str,
) -> list[str]:
    """Argv for mlx-audio 0.2.10 `python -m mlx_audio.tts.generate`.

    Uses ``--file_prefix`` (writes under cwd). Does not pass invalid
    ``--output`` / ``--context`` flags from older scaffolding.
    """
    return [
        sys.executable,
        "-m",
        "mlx_audio.tts.generate",
        "--model",
        model_id,
        "--text",
        text,
        "--ref_audio",
        str(ref_audio),
        "--file_prefix",
        file_prefix,
        "--join_audio",
        "--audio_format",
        "wav",
    ]


def discover_generated_wav(work_dir: Path, file_prefix: str) -> Path | None:
    """Find wav written by mlx-audio for a given file_prefix under work_dir."""
    joined = work_dir / f"{file_prefix}.wav"
    if joined.is_file():
        return joined
    numbered = sorted(work_dir.glob(f"{file_prefix}_*.wav"))
    if numbered:
        return numbered[0]
    loose = sorted(work_dir.glob(f"{file_prefix}*.wav"))
    return loose[0] if loose else None


def _run_tts(
    *,
    model_id: str,
    text: str,
    ref_audio: Path,
    out_wav: Path,
) -> None:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    work_dir = out_wav.parent
    # Prefix only (no path) — mlx-audio writes relative to cwd.
    file_prefix = out_wav.stem
    cmd = build_tts_argv(
        model_id=model_id,
        text=text,
        ref_audio=ref_audio,
        file_prefix=file_prefix,
    )
    proc = subprocess.run(
        cmd,
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "tts failed")[:500])
    generated = discover_generated_wav(work_dir, file_prefix)
    if generated is None:
        raise RuntimeError("tts produced no wav output")
    if generated.resolve() != out_wav.resolve():
        generated.replace(out_wav)


def run_payload(payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("mode") or "synthesize").lower()
    model_id = str(payload.get("model_id") or payload.get("model") or "").strip()
    text = str(payload.get("text") or "").strip()
    ref = Path(str(payload.get("ref_audio") or ""))
    out_wav = Path(str(payload.get("out_wav") or payload.get("output") or ""))
    tone = payload.get("tone")

    if not model_id:
        raise ValueError("model_id required")
    if not ref.is_file():
        raise ValueError(f"ref_audio missing: {ref}")
    if not out_wav:
        raise ValueError("out_wav required")
    if mode in ("synthesize", "tone") and not text:
        raise ValueError("text required for synthesize/tone")
    if mode == "convert":
        # Convert/timbre-match is DSP at the orchestration layer — never invent TTS here.
        raise ValueError(
            "convert mode is not supported in s2s_generate; use DSP timbre_match for matched/"
        )

    # Tone is orchestration metadata. Never prepend delivery instructions to
    # --text: mlx-audio treats that argument as literal listener-facing speech.
    spoken = text
    # context_audio is intentionally ignored (mlx-audio 0.2.10 has no --context).
    _run_tts(
        model_id=model_id,
        text=spoken,
        ref_audio=ref,
        out_wav=out_wav,
    )
    return {
        "ok": True,
        "mode": mode,
        "out_wav": str(out_wav),
        "model_id": model_id,
        "tone": tone,
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
        print(json.dumps({"ok": False, "error": "invalid stdin JSON"}))
        return 1

    try:
        result = run_payload(payload)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:500]}))
        return 1
    if isinstance(result, dict) and "ok" not in result:
        result = {**result, "ok": True}
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
