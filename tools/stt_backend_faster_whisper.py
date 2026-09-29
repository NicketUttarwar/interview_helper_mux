#!/usr/bin/env python3
"""CUDA/CPU STT backend (faster-whisper) with the MLX path's words contract.

Used on hosts without MLX (Windows / Linux / Intel Mac). ``stt_transcribe.py``
prefers ``mlx_audio`` when it imports and falls back here, so the
``{"text", "words": [...]}`` contract in ``stt_runner.transcribe_audio`` is
unchanged either way.

Speaker labels come from pyannote when it is installed and a HF token is
present; otherwise every word is ``spk_0``, matching the MLX whisper path.
"""

from __future__ import annotations

import glob
import os
import sys
from pathlib import Path
from typing import Any

# CTranslate2 on Windows needs the cuBLAS / cuDNN DLLs that ship in the
# `nvidia-*-cu12` wheels; they are not on PATH, so register them before import.
_DLL_DIRS_ADDED = False


def _add_cuda_dll_dirs() -> None:
    """Make the `nvidia-*-cu12` wheel DLLs loadable by CTranslate2.

    CTranslate2 resolves cuBLAS/cuDNN with a bare ``LoadLibrary`` from its own
    C++ code, which ignores ``os.add_dll_directory`` and uses the process DLL
    search order instead. So prepend the wheel bin dirs to PATH as well, because
    ``add_dll_directory`` alone leaves ``cublas64_12.dll`` unfound.
    """
    global _DLL_DIRS_ADDED
    if _DLL_DIRS_ADDED or os.name != "nt":
        return
    _DLL_DIRS_ADDED = True
    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    found: list[str] = []
    for pattern in ("nvidia/*/bin", "nvidia/*/lib"):
        found.extend(glob.glob(str(site_packages / pattern)))
    for path in found:
        try:
            os.add_dll_directory(path)
        except (OSError, AttributeError):
            pass
    if found:
        os.environ["PATH"] = os.pathsep.join([*found, os.environ.get("PATH", "")])


#: MLX model ids the pipeline ships → CTranslate2 equivalents on the HF hub.
_MODEL_ALIASES = {
    "mlx-community/whisper-large-v3-turbo": "large-v3-turbo",
    "mlx-community/whisper-large-v3-turbo-asr-fp16": "large-v3-turbo",
    "mlx-community/whisper-large-v3": "large-v3",
    "mlx-community/whisper-medium": "medium",
    "mlx-community/whisper-small": "small",
}


def resolve_model_id(model_id: str) -> str:
    """Map an MLX/whisper model id onto a faster-whisper size or CT2 repo."""
    raw = (model_id or "").strip()
    if not raw:
        return "large-v3-turbo"
    if raw in _MODEL_ALIASES:
        return _MODEL_ALIASES[raw]
    low = raw.lower()
    if low.startswith("mlx-community/"):
        # Unknown MLX id, so fall back on the size hint in its name.
        for needle, size in (
            ("large-v3-turbo", "large-v3-turbo"),
            ("large-v3", "large-v3"),
            ("large", "large-v3"),
            ("medium", "medium"),
            ("small", "small"),
            ("base", "base"),
            ("tiny", "tiny"),
        ):
            if needle in low:
                return size
        return "large-v3-turbo"
    return raw


def _device_and_compute_type() -> tuple[str, str]:
    """Pick CUDA when CTranslate2 can see a GPU, else CPU, with a fitting dtype."""
    override_device = (os.environ.get("MUX_STT_DEVICE") or "").strip()
    override_ctype = (os.environ.get("MUX_STT_COMPUTE_TYPE") or "").strip()
    _add_cuda_dll_dirs()
    device = override_device
    if not device:
        try:
            import ctranslate2

            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"
    if override_ctype:
        return device, override_ctype
    # int8_float16 keeps large-v3-turbo inside ~6 GB of VRAM; int8 is the CPU pick.
    return device, ("int8_float16" if device == "cuda" else "int8")


def verify() -> dict[str, Any]:
    _add_cuda_dll_dirs()
    try:
        import faster_whisper  # noqa: F401
    except ImportError as exc:
        return {"error": f"faster_whisper missing: {exc}"}
    device, compute_type = _device_and_compute_type()
    return {
        "ok": True,
        "stack": "faster-whisper",
        "device": device,
        "compute_type": compute_type,
    }


#: Env override for the isolated diarization venv interpreter.
DIARIZE_PY_ENV = "MUX_DIARIZE_PYTHON"


def _diarize_python() -> str:
    """Interpreter for the isolated diarization venv, or "" when unavailable.

    Diarization lives in its own venv because NeMo pulls torch and a large tree,
    while this venv is deliberately lean (faster-whisper runs on CTranslate2 and
    has no torch). Resolved from config so it follows local_runtimes like every
    other runtime, with an env override for direct runs.
    """
    import os as _os

    override = str(_os.environ.get(DIARIZE_PY_ENV) or "").strip()
    if override and Path(override).is_file():
        return override
    try:
        from interview_mux.local_runtime import resolve_venv_dir
        from interview_mux.venv_paths import venv_python

        py = venv_python(resolve_venv_dir("diarize"))
        return str(py) if py.is_file() else ""
    except Exception:
        # This module also runs inside a venv with no interview_mux installed,
        # so fall back to the conventional location next to the other runtimes.
        for base in (r"C:/mux-local/local_diarize/venv", "ASSETS/local_diarize/venv"):
            cand = Path(base) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            if cand.is_file():
                return str(cand)
    return ""


def _diarize_sortformer(audio: Path) -> list[tuple[float, float, str]]:
    """Run Sortformer in its own venv; returns [] when unavailable."""
    import json as _json
    import subprocess as _sp
    import tempfile as _tf

    py = _diarize_python()
    if not py:
        return []
    script = Path(__file__).resolve().parent / "diarize_sortformer.py"
    if not script.is_file():
        return []
    with _tf.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        out_path = Path(tmp.name)
    try:
        proc = _sp.run(
            [py, str(script), "--audio", str(audio), "--output", str(out_path)],
            capture_output=True,
            text=True,
            timeout=_diarize_timeout_sec(),
            check=False,
        )
        if proc.returncode != 0 or not out_path.is_file():
            return []
        doc = _json.loads(out_path.read_text(encoding="utf-8"))
        turns = doc.get("turns") or []
        out: list[tuple[float, float, str]] = []
        for t in turns:
            try:
                out.append(
                    (
                        float(t["start_ms"]) / 1000.0,
                        float(t["end_ms"]) / 1000.0,
                        str(t["speaker_id"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return out
    except Exception:
        return []
    finally:
        out_path.unlink(missing_ok=True)


def _diarize_timeout_sec() -> int:
    """Sortformer is ~1s per 40s of audio on GPU; allow generously for CPU."""
    import os as _os

    try:
        return max(300, int(str(_os.environ.get("MUX_DIARIZE_TIMEOUT_SEC") or "").strip() or 0))
    except ValueError:
        return 3600


def _load_diarizer():
    """Return a pyannote pipeline, or None when unavailable (fail-open to spk_0)."""
    if (os.environ.get("MUX_STT_DIARIZATION") or "").strip().lower() in {"0", "off", "none"}:
        return None
    token = (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        or ""
    ).strip()
    if not token:
        return None
    try:
        import torch
        from pyannote.audio import Pipeline
    except ImportError:
        return None
    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1", use_auth_token=token
        )
        if pipeline is None:
            return None
        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
        return pipeline
    except Exception:
        return None


def _diarize(audio: Path) -> list[tuple[float, float, str]]:
    """Return [(start_sec, end_sec, speaker_id)]; empty when diarization is off.

    Sortformer first: it is ungated, needs no Hugging Face token, and is the same
    model Apple Silicon uses via its MLX port. pyannote stays as a fallback for a
    host that has it configured.
    """
    if (os.environ.get("MUX_STT_DIARIZATION") or "").strip().lower() in {"0", "off", "none"}:
        return []
    turns = _diarize_sortformer(audio)
    if turns:
        return turns
    pipeline = _load_diarizer()
    if pipeline is None:
        return []
    try:
        annotation = pipeline(str(audio))
    except Exception:
        return []
    turns: list[tuple[float, float, str]] = []
    try:
        for turn, _, speaker in annotation.itertracks(yield_label=True):
            turns.append((float(turn.start), float(turn.end), str(speaker)))
    except Exception:
        return []
    return turns


def _speaker_at(turns: list[tuple[float, float, str]], start: float, end: float) -> str:
    """Speaker whose turn overlaps [start, end] most; spk_0 when none do."""
    if not turns:
        return "spk_0"
    best_label = ""
    best_overlap = 0.0
    for t_start, t_end, label in turns:
        overlap = min(end, t_end) - max(start, t_start)
        if overlap > best_overlap:
            best_overlap = overlap
            best_label = label
    if not best_label:
        return "spk_0"
    digits = "".join(ch for ch in best_label if ch.isdigit())
    return f"spk_{int(digits)}" if digits else str(best_label)


def transcribe(audio: Path, model_id: str, *, diarization_mode: str = "sortformer") -> dict[str, Any]:
    """Transcribe with faster-whisper; return the words/segments contract."""
    _add_cuda_dll_dirs()
    from faster_whisper import WhisperModel

    device, compute_type = _device_and_compute_type()
    resolved = resolve_model_id(model_id)
    try:
        model = WhisperModel(resolved, device=device, compute_type=compute_type)
    except Exception:
        if device != "cpu":
            # A CUDA load failure (missing DLL, OOM) should degrade, not abort.
            model = WhisperModel(resolved, device="cpu", compute_type="int8")
        else:
            raise

    segment_iter, _info = model.transcribe(
        str(audio),
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
    )
    segments = list(segment_iter)

    turns: list[tuple[float, float, str]] = []
    if (diarization_mode or "").strip().lower() not in {"", "off", "none"}:
        turns = _diarize(audio)

    words: list[dict[str, Any]] = []
    norm_segments: list[dict[str, Any]] = []
    text_parts: list[str] = []

    for seg in segments:
        seg_start = float(getattr(seg, "start", 0.0) or 0.0)
        seg_end = float(getattr(seg, "end", seg_start) or seg_start)
        seg_text = str(getattr(seg, "text", "") or "").strip()
        if seg_text:
            text_parts.append(seg_text)
        seg_speaker = _speaker_at(turns, seg_start, seg_end)
        norm_segments.append(
            {
                "text": seg_text,
                "start_time": seg_start,
                "end_time": seg_end,
                "speaker_id": seg_speaker,
            }
        )
        for item in getattr(seg, "words", None) or []:
            token = str(getattr(item, "word", "") or "").strip()
            if not token:
                continue
            w_start = float(getattr(item, "start", seg_start) or seg_start)
            w_end = float(getattr(item, "end", w_start) or w_start)
            words.append(
                {
                    "text": token,
                    "start_ms": int(w_start * 1000),
                    "end_ms": int(w_end * 1000),
                    "speaker_id": _speaker_at(turns, w_start, w_end) if turns else seg_speaker,
                    "confidence": getattr(item, "probability", None),
                }
            )

    text = " ".join(text_parts).strip()
    if not words and text:
        # Mirror the MLX whisper path: never return text with an empty word list.
        words = [
            {
                "text": tok,
                "start_ms": 0,
                "end_ms": 0,
                "speaker_id": "spk_0",
                "confidence": None,
            }
            for tok in text.split()
        ]
    return {"text": text, "words": words, "segments": norm_segments}
