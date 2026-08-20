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
    vad_ok = False
    vad_error = ""
    try:
        from mlx_audio.vad import load  # noqa: F401

        vad_ok = True
    except Exception as exc:  # noqa: BLE001
        vad_error = str(exc)[:200]
    payload = {
        "ok": True,
        "stack": "mlx-audio",
        "modes": ["warmup", "classify", "speaker_pair"],
        "listen_path": "stt_listen",
        "vad_ok": vad_ok,
    }
    if vad_error:
        payload["vad_error"] = vad_error
    return _out(payload)


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


def _concat_pair(a: Path, b: Path, dest: Path, silence_ms: int = 300) -> str | None:
    import subprocess

    dest.parent.mkdir(parents=True, exist_ok=True)
    sil_s = max(silence_ms, 1) / 1000.0
    proc = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(a),
            "-f", "lavfi", "-t", f"{sil_s:.3f}", "-i", "anullsrc=r=48000:cl=mono",
            "-i", str(b),
            "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]",
            "-map", "[out]",
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            str(dest),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0 or not dest.is_file():
        return (proc.stderr or proc.stdout or "concat failed")[-400:]
    return None


def _speaker_pair(payload: dict[str, Any]) -> int:
    """Identity YES/NO from two clips via Sortformer (not STT text)."""
    clip_a = Path(str(payload.get("clip_a_wav") or ""))
    clip_b = Path(str(payload.get("clip_b_wav") or ""))
    concat = Path(str(payload.get("clip_wav") or ""))
    model_id = str(
        payload.get("diarization_model_id")
        or "mlx-community/diar_sortformer_4spk-v1-fp32"
    ).strip()
    probe_id = str(payload.get("probe_id") or "vprobe.same_speaker_pair")
    if not concat.is_file():
        if not (clip_a.is_file() and clip_b.is_file()):
            return _out({"ok": False, "error": "clip_a_wav and clip_b_wav required", "fallback": "heuristic"}, 0)
        concat = clip_a.parent / "pair_concat.wav"
        err = _concat_pair(clip_a, clip_b, concat)
        if err:
            return _out({"ok": False, "error": f"pair concat failed: {err}", "fallback": "heuristic"}, 0)

    try:
        from mlx_audio.vad import load
    except Exception as exc:  # noqa: BLE001
        return _out(
            {
                "ok": False,
                "error": f"mlx_audio.vad unavailable: {exc}",
                "fallback": "heuristic",
                "probe_id": probe_id,
            },
            0,
        )

    try:
        model = load(model_id)
        result = model.generate(str(concat), threshold=0.4, min_duration=0.15, merge_gap=0.4)
    except Exception as exc:  # noqa: BLE001
        return _out(
            {
                "ok": False,
                "error": f"sortformer generate failed: {exc}"[:400],
                "fallback": "heuristic",
                "model_id": model_id,
            },
            0,
        )

    segs: list[dict[str, Any]] = []
    for seg in getattr(result, "segments", None) or []:
        speaker = getattr(seg, "speaker", None)
        start = getattr(seg, "start", None)
        end = getattr(seg, "end", None)
        if isinstance(seg, dict):
            speaker = speaker or seg.get("speaker") or seg.get("speaker_id")
            start = start if start is not None else seg.get("start")
            end = end if end is not None else seg.get("end")
        segs.append({"speaker": str(speaker), "start_s": float(start or 0), "end_s": float(end or 0)})

    ids = sorted({s["speaker"] for s in segs})
    if not segs:
        return _out({"ok": False, "error": "sortformer returned no segments", "fallback": "heuristic", "model_id": model_id}, 0)
    if len(ids) <= 1:
        verdict = "YES"
        reason = "one speaker on the concatenated pair"
    else:
        # Split at midpoint of concat (clip A | silence | clip B).
        mid = (max(s["end_s"] for s in segs) + min(s["start_s"] for s in segs)) / 2.0
        left = sorted({s["speaker"] for s in segs if s["start_s"] < mid - 0.05})
        right = sorted({s["speaker"] for s in segs if s["end_s"] > mid + 0.05})
        if left and right and set(left) == set(right) and len(left) == 1:
            verdict = "YES"
            reason = "same sortformer speaker id on both sides"
        elif left and right and set(left).isdisjoint(set(right)):
            verdict = "NO"
            reason = "different sortformer speaker ids on each side"
        else:
            return _out(
                {
                    "ok": False,
                    "error": "ambiguous sortformer speaker overlap",
                    "fallback": "heuristic",
                    "segments": segs[:40],
                    "model_id": model_id,
                },
                0,
            )

    return _out(
        {
            "ok": True,
            "source": "sortformer_pair",
            "listen_mode": "speaker_pair",
            "verdict": verdict,
            "answer": verdict,
            "text": verdict,
            "reason": reason,
            "model_id": model_id,
            "probe_id": probe_id,
            "contract": "YES_NO",
            "segments": segs[:40],
            "clip_a_wav": str(clip_a) if clip_a.is_file() else "",
            "clip_b_wav": str(clip_b) if clip_b.is_file() else "",
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audio probe MLX interrogate helper")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--mode", choices=("warmup", "classify", "speaker_pair"), default="")
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
    if mode == "speaker_pair":
        return _speaker_pair(payload)
    return _out({"ok": False, "error": f"unknown mode: {mode}", "fallback": "heuristic"}, 0)


if __name__ == "__main__":
    raise SystemExit(main())
