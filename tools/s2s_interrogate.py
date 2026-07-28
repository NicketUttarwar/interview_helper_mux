#!/usr/bin/env python3
"""Local speech interrogate CLI for the Audio Probe Platform.

Modes:
  verify     — mlx_audio import check
  warmup     — TTS system prompt to wav (neutral ref)
  classify   — listen to clip via STT; return evidence for parent answerer

Certified listen-and-answer path (v1): STT-listen.
  clip_wav → mlx Whisper STT → {ok, stt_text, words, source: stt_listen}
Parent (audio_probe_listen.answer_from_listen_evidence) maps evidence → YES/NO|KEYWORDS|…

Warm-up wav is recorded in the response for future end-to-end audio L&A models;
STT-listen does not require it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Allow imports of sibling tools when invoked via local_runtime (cwd=repo root).
_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))


def _out(payload: dict[str, Any], code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return code


def _verify() -> int:
    try:
        import mlx_audio  # noqa: F401
    except ImportError as exc:
        return _out({"ok": False, "error": f"mlx_audio missing: {exc}", "fallback": "heuristic"}, 0)
    return _out(
        {
            "ok": True,
            "stack": "mlx-audio",
            "modes": ["warmup", "classify"],
            "listen_path": "stt_listen",
        }
    )


def _warmup(payload: dict[str, Any]) -> int:
    """Synthesize spoken system-prompt warm-up via mlx-audio TTS."""
    text = str(payload.get("text") or "").strip()
    out_wav = Path(str(payload.get("out_wav") or ""))
    model_id = str(payload.get("model_id") or "").strip()
    ref_audio = Path(str(payload.get("ref_audio") or ""))
    if not text or not out_wav:
        return _out({"ok": False, "error": "text and out_wav required", "fallback": "heuristic"}, 0)
    if not model_id:
        return _out({"ok": False, "error": "model_id empty", "fallback": "heuristic"}, 0)
    try:
        import mlx_audio  # noqa: F401
    except ImportError as exc:
        return _out({"ok": False, "error": f"mlx_audio missing: {exc}", "fallback": "heuristic"}, 0)

    try:
        from s2s_generate import build_tts_argv, discover_generated_wav
    except ImportError:
        build_tts_argv = None  # type: ignore
        discover_generated_wav = None  # type: ignore

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    work = out_wav.parent
    prefix = out_wav.stem
    if not ref_audio.is_file():
        return _out(
            {
                "ok": False,
                "error": f"missing ref_audio: {ref_audio}",
                "fallback": "heuristic",
            },
            0,
        )

    if build_tts_argv is None:
        return _out({"ok": False, "error": "s2s_generate helpers missing", "fallback": "heuristic"}, 0)

    import subprocess

    argv = build_tts_argv(model_id=model_id, text=text[:500], ref_audio=ref_audio, file_prefix=prefix)
    try:
        proc = subprocess.run(
            argv,
            cwd=str(work),
            capture_output=True,
            text=True,
            timeout=int(payload.get("timeout_sec") or 120),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _out({"ok": False, "error": str(exc), "fallback": "heuristic"}, 0)

    found = discover_generated_wav(work, prefix) if discover_generated_wav else None
    if found and found.is_file():
        if found.resolve() != out_wav.resolve():
            out_wav.write_bytes(found.read_bytes())
        return _out(
            {
                "ok": True,
                "out_wav": str(out_wav),
                "model_id": model_id,
                "bytes": out_wav.stat().st_size,
            }
        )
    err = (proc.stderr or proc.stdout or "no wav written")[:400]
    return _out({"ok": False, "error": err, "fallback": "heuristic"}, 0)


def _classify(payload: dict[str, Any]) -> int:
    """Listen to clip via STT; return evidence for parent-side contract answering."""
    clip = Path(str(payload.get("clip_wav") or ""))
    warmup = Path(str(payload.get("warmup_wav") or ""))
    model_id = str(
        payload.get("interrogate_model_id")
        or payload.get("stt_model_id")
        or payload.get("model_id")
        or ""
    ).strip()
    contract = str(payload.get("output_contract") or "YES_NO")
    probe_id = str(payload.get("probe_id") or "")
    mode = str(payload.get("listen_mode") or "stt_listen").strip() or "stt_listen"

    if not clip.is_file():
        return _out({"ok": False, "error": "clip_wav missing", "fallback": "heuristic"}, 0)

    if mode not in {"stt_listen", "stt"}:
        return _out(
            {
                "ok": False,
                "error": f"listen_mode '{mode}' not certified; use stt_listen",
                "fallback": "heuristic",
                "warmup_present": warmup.is_file(),
                "contract": contract,
            },
            0,
        )

    if not model_id:
        return _out(
            {
                "ok": False,
                "error": "interrogate/stt model_id empty",
                "fallback": "heuristic",
                "warmup_present": warmup.is_file(),
                "contract": contract,
            },
            0,
        )

    try:
        from stt_transcribe import transcribe
    except ImportError as exc:
        return _out(
            {
                "ok": False,
                "error": f"stt_transcribe import failed: {exc}",
                "fallback": "heuristic",
            },
            0,
        )

    try:
        result = transcribe(clip, model_id, diarization_mode="none")
    except Exception as exc:  # noqa: BLE001 — fail-open to parent heuristic
        return _out(
            {
                "ok": False,
                "error": f"stt_listen failed: {exc}"[:400],
                "fallback": "heuristic",
                "warmup_present": warmup.is_file(),
                "model_id": model_id,
                "clip_wav": str(clip),
            },
            0,
        )

    stt_text = str(result.get("text") or "").strip()
    words = result.get("words") if isinstance(result.get("words"), list) else []
    if not stt_text and not words:
        return _out(
            {
                "ok": False,
                "error": "stt_listen returned empty transcript",
                "fallback": "heuristic",
                "warmup_present": warmup.is_file(),
                "model_id": model_id,
            },
            0,
        )

    return _out(
        {
            "ok": True,
            "source": "stt_listen",
            "listen_mode": "stt_listen",
            "stt_text": stt_text,
            "text": stt_text,  # alias for bridges expecting text
            "words": words[:400],
            "model_id": model_id,
            "probe_id": probe_id,
            "contract": contract,
            "warmup_present": warmup.is_file(),
            "warmup_wav": str(warmup) if warmup.is_file() else "",
            "clip_wav": str(clip),
            "confidence": 0.75,
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audio probe MLX interrogate helper")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--mode", choices=("warmup", "classify"), default="")
    args, _unknown = parser.parse_known_args(argv)
    if args.verify:
        return _verify()
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return _out({"ok": False, "error": "invalid JSON stdin", "fallback": "heuristic"}, 0)
    if not isinstance(payload, dict):
        return _out({"ok": False, "error": "payload must be object", "fallback": "heuristic"}, 0)
    mode = str(args.mode or payload.get("mode") or "").strip()
    if mode == "warmup":
        return _warmup(payload)
    if mode == "classify":
        return _classify(payload)
    return _out({"ok": False, "error": f"unknown mode: {mode}", "fallback": "heuristic"}, 0)


if __name__ == "__main__":
    raise SystemExit(main())
