"""Local MusicGen runner for music-only theme stems."""

from __future__ import annotations

import hashlib
import json
import math
import struct
import subprocess
import wave
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config, repo_root


class MusicGenUnavailable(RuntimeError):
    """MusicGen venv/model not available."""


def musicgen_cfg() -> dict[str, Any]:
    cfg = merged_config().get("musicgen") or {}
    return cfg if isinstance(cfg, dict) else {}


def musicgen_enabled() -> bool:
    return bool(musicgen_cfg().get("enabled", True))


def fail_closed_on_stub() -> bool:
    return bool(musicgen_cfg().get("fail_closed_on_stub", True))


def musicgen_venv_python() -> Path | None:
    rt = (merged_config().get("local_runtimes") or {}).get("musicgen") or {}
    venv = str(rt.get("venv_dir") or "ASSETS/local_musicgen/venv")
    root = repo_root()
    py = root / venv / "bin" / "python"
    if py.is_file():
        return py
    # Fall back to main .venv for lightweight stub / optional installs
    main = root / ".venv" / "bin" / "python"
    return main if main.is_file() else None


def clamp_music_duration(seconds: float, *, role: str | None = None) -> float:
    cfg = musicgen_cfg()
    lo = float(cfg.get("min_duration_sec") or 4.0)
    hi = float(cfg.get("max_duration_sec") or 20.0)
    bands = (merged_config().get("mmaudio") or {}).get("duration_bands_by_role") or {}
    if role and isinstance(bands.get(role), (list, tuple)) and len(bands[role]) >= 2:
        lo = max(lo, float(bands[role][0]))
        hi = min(hi, float(bands[role][1]))
        if lo > hi:
            lo, hi = float(bands[role][0]), float(bands[role][1])
    return max(lo, min(hi, float(seconds)))


def prompt_hash(prompt: str, *, negative: str = "", model_id: str = "") -> str:
    blob = f"{model_id}|{prompt}|{negative}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def best_of_n_for_role(role: str | None) -> int:
    cfg = musicgen_cfg()
    role_s = str(role or "")
    if role_s in {"theme_underscore"} or "underscore" in role_s:
        return max(1, int(cfg.get("best_of_n_underscore") or 2))
    return max(1, int(cfg.get("best_of_n_speech_free") or 3))


def _write_musical_stub_wav(path: Path, *, duration_sec: float, seed: int = 0) -> None:
    """Deterministic rhythmic multi-note stub when MusicGen weights unavailable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 48000
    n = max(1, int(duration_sec * rate))
    # Pentatonic-ish motif frequencies + pulse
    base = 220.0 + (seed % 7) * 8.0
    motif = [base, base * 1.25, base * 1.5, base * 1.33, base * 2.0]
    bpm = 100 + (seed % 5) * 4
    beat_len = max(1, int(rate * 60.0 / bpm))
    samples: list[float] = []
    note_len = max(1, n // len(motif))
    for i in range(n):
        ni = min(len(motif) - 1, i // note_len)
        f = motif[ni]
        t = i / rate
        local = (i % note_len) / note_len
        env = min(1.0, local * 8.0) * (1.0 - 0.35 * local)
        # Fundamental + fifth
        val = 0.20 * math.sin(2 * math.pi * f * t) * env
        val += 0.07 * math.sin(2 * math.pi * f * 1.5 * t) * env
        # Audible rhythmic pulse (never pad-only)
        beat_pos = (i % beat_len) / beat_len
        pulse = math.exp(-beat_pos * 8.0) * 0.18
        val += pulse * math.sin(2 * math.pi * (base * 0.5) * t)
        samples.append(max(-1.0, min(1.0, val)))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = b"".join(struct.pack("<h", int(s * 32767)) for s in samples)
        wf.writeframes(frames)


def _write_generation_meta(out_wav: Path, meta: dict[str, Any]) -> None:
    meta_path = out_wav.with_suffix(".gen.json")
    try:
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def generate_music_clip(
    *,
    prompt: str,
    negative_prompt: str,
    duration_sec: float,
    out_wav: Path,
    role: str | None = None,
    seed: int | None = None,
    melody_wav: Path | None = None,
) -> dict[str, Any]:
    """Generate instrumental music WAV via MusicGen subprocess or musical stub."""
    if not musicgen_enabled():
        raise MusicGenUnavailable("musicgen.enabled is false")
    dur = clamp_music_duration(duration_sec, role=role)
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    py = musicgen_venv_python()
    script = repo_root() / "tools" / "musicgen_generate.py"
    model_id = str(musicgen_cfg().get("model_id") or "facebook/musicgen-large")
    melody_model_id = str(
        musicgen_cfg().get("melody_model_id") or "facebook/musicgen-melody-large"
    )
    use_melody = bool(musicgen_cfg().get("use_melody_conditioning", True))
    ph = prompt_hash(prompt, negative=negative_prompt, model_id=model_id)
    meta: dict[str, Any] = {
        "duration_sec": dur,
        "role": role,
        "model_id": model_id,
        "melody_model_id": melody_model_id if melody_wav else None,
        "prompt": prompt[:240],
        "prompt_hash": ph,
        "seed": seed,
        "negative_prompt": (negative_prompt or "")[:200],
    }
    if py and script.is_file():
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "duration_sec": dur,
            "out_wav": str(out_wav),
            "model_id": model_id,
            "melody_model_id": melody_model_id,
            "seed": seed,
            "melody_wav": str(melody_wav) if melody_wav and Path(melody_wav).is_file() else None,
            "use_melody_conditioning": use_melody,
        }
        req = out_wav.with_suffix(".request.json")
        req.write_text(json.dumps(payload), encoding="utf-8")
        timeout = int(musicgen_cfg().get("request_timeout_sec") or 1200)
        try:
            proc = subprocess.run(
                [str(py), str(script), str(req)],
                cwd=str(repo_root()),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if proc.returncode == 0 and out_wav.is_file() and out_wav.stat().st_size > 1000:
                meta["backend"] = "musicgen"
                meta["stdout_tail"] = (proc.stdout or "")[-400:]
                _write_generation_meta(out_wav, meta)
                return meta
            meta["musicgen_stderr"] = (proc.stderr or "")[-800:]
            meta["musicgen_returncode"] = proc.returncode
        except Exception as exc:
            meta["musicgen_error"] = str(exc)[:400]

    if fail_closed_on_stub():
        meta["backend"] = "unavailable"
        _write_generation_meta(out_wav, meta)
        raise MusicGenUnavailable(
            "MusicGen unavailable and fail_closed_on_stub=true "
            f"(role={role}, stderr={(meta.get('musicgen_stderr') or meta.get('musicgen_error') or '')[:200]})"
        )

    # Musical stub fallback (notes only) — never whoosh/tick. Dev/offline only.
    _write_musical_stub_wav(out_wav, duration_sec=dur, seed=int(seed or 0))
    meta["backend"] = "musical_stub"
    meta["warning"] = "MusicGen unavailable; wrote deterministic musical-note stub"
    _write_generation_meta(out_wav, meta)
    return meta
