"""Local MLX MusicGen runner for music-only theme stems."""

from __future__ import annotations

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


def _write_musical_stub_wav(path: Path, *, duration_sec: float, seed: int = 0) -> None:
    """Deterministic multi-note stub (musical, not foley) when MusicGen weights unavailable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 48000
    n = max(1, int(duration_sec * rate))
    # Pentatonic-ish motif frequencies
    base = 220.0 + (seed % 7) * 8.0
    motif = [base, base * 1.25, base * 1.5, base * 1.33, base * 2.0]
    samples: list[float] = []
    note_len = max(1, n // len(motif))
    for i in range(n):
        ni = min(len(motif) - 1, i // note_len)
        f = motif[ni]
        t = i / rate
        # Soft attack envelope per note
        local = (i % note_len) / note_len
        env = min(1.0, local * 8.0) * (1.0 - 0.35 * local)
        # Fundamental + gentle fifth harmonic (musical undertone)
        val = 0.22 * math.sin(2 * math.pi * f * t) * env
        val += 0.08 * math.sin(2 * math.pi * f * 1.5 * t) * env
        samples.append(max(-1.0, min(1.0, val)))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = b"".join(struct.pack("<h", int(s * 32767)) for s in samples)
        wf.writeframes(frames)


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
    meta: dict[str, Any] = {
        "duration_sec": dur,
        "role": role,
        "model_id": musicgen_cfg().get("model_id"),
        "prompt": prompt[:240],
    }
    if py and script.is_file():
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "duration_sec": dur,
            "out_wav": str(out_wav),
            "model_id": musicgen_cfg().get("model_id") or "facebook/musicgen-medium",
            "seed": seed,
            "melody_wav": str(melody_wav) if melody_wav and Path(melody_wav).is_file() else None,
            "use_melody_conditioning": bool(musicgen_cfg().get("use_melody_conditioning", True)),
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
                return meta
            meta["musicgen_stderr"] = (proc.stderr or "")[-800:]
            meta["musicgen_returncode"] = proc.returncode
        except Exception as exc:
            meta["musicgen_error"] = str(exc)[:400]

    # Musical stub fallback (notes only) — never whoosh/tick.
    _write_musical_stub_wav(out_wav, duration_sec=dur, seed=int(seed or 0))
    meta["backend"] = "musical_stub"
    meta["warning"] = "MusicGen unavailable; wrote deterministic musical-note stub"
    return meta
