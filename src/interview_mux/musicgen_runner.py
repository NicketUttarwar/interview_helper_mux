"""Local MusicGen runner for music-only theme stems."""

from __future__ import annotations

import hashlib
import json
import math
import os
import signal
import struct
import subprocess
import wave
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config, repo_root

_BAN_MPS_ENV = "MUX_MUSICGEN_BAN_MPS"
_BAN_MPS_MARKER = ".musicgen_ban_mps"


class MusicGenUnavailable(RuntimeError):
    """MusicGen venv/model not available."""


def musicgen_cfg() -> dict[str, Any]:
    cfg = merged_config().get("musicgen") or {}
    return cfg if isinstance(cfg, dict) else {}


def musicgen_enabled() -> bool:
    return bool(musicgen_cfg().get("enabled", True))


def fail_closed_on_stub() -> bool:
    import os

    # E2E soft-escape after MusicGen OOM / quit loops (set by baba e2e driver).
    if str(os.environ.get("MUX_E2E_MUSICGEN_ALLOW_STUB") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return False
    return bool(musicgen_cfg().get("fail_closed_on_stub", True))


def musicgen_hf_home() -> Path:
    """Isolated Hugging Face cache used by bootstrap_musicgen.sh."""
    return repo_root() / "ASSETS" / "local_musicgen" / "hf_cache"


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


def cli_python_executable(py: Path) -> Path:
    """Prefer the framework CLI binary over Python.app (avoids macOS crash dialogs)."""
    try:
        resolved = py.resolve()
    except OSError:
        return py
    parts = list(resolved.parts)
    if "Python.app" not in parts or "Versions" not in parts:
        return py
    try:
        i = parts.index("Versions")
        version_root = Path(*parts[: i + 2])
    except Exception:
        return py
    for name in ("python3.12", "python3", "python"):
        cand = version_root / "bin" / name
        if cand.is_file():
            return cand
    return py


def is_abort_returncode(code: int | None) -> bool:
    if code is None:
        return False
    n = int(code)
    try:
        sigabrt = int(signal.SIGABRT)
    except Exception:
        sigabrt = 6
    return n in {-sigabrt, 128 + sigabrt, sigabrt}


def mps_banned(*, run_ctx: Any | None = None) -> bool:
    if str(os.environ.get(_BAN_MPS_ENV) or "").strip().lower() in {"1", "true", "yes"}:
        return True
    if run_ctx is None:
        return False
    try:
        marker = Path(run_ctx.run_dir) / _BAN_MPS_MARKER
        if marker.is_file():
            return True
        meta = run_ctx.read_json("run_meta.json") if run_ctx.artifact_exists("run_meta.json") else {}
        if isinstance(meta, dict) and meta.get("musicgen_ban_mps"):
            return True
    except Exception:
        return False
    return False


def ban_mps(*, run_ctx: Any | None = None, reason: str = "") -> None:
    os.environ[_BAN_MPS_ENV] = "1"
    if run_ctx is None:
        return
    try:
        (Path(run_ctx.run_dir) / _BAN_MPS_MARKER).write_text(reason or "abort", encoding="utf-8")
    except OSError:
        pass
    try:

        def _flag(m: dict) -> None:
            m["musicgen_ban_mps"] = True
            if reason:
                m["musicgen_ban_mps_reason"] = str(reason)[:200]

        run_ctx.mutate_run_meta(_flag)
    except Exception:
        pass


def effective_musicgen_device(*, requested: str | None = None, run_ctx: Any | None = None) -> str:
    """Resolve device. ``auto`` never selects MPS (Metal abort). Opt in with ``mps``."""
    pref = str(requested if requested is not None else (musicgen_cfg().get("device") or "cpu")).strip().lower()
    if pref in {"", "auto"}:
        pref = "cpu"
    if pref == "mps" and mps_banned(run_ctx=run_ctx):
        return "cpu"
    if pref in {"cuda", "gpu"}:
        return "cuda"
    if pref == "mlx":
        return "mlx"
    if pref == "mps":
        return "mps"
    return "cpu"


def _run_ctx_for_out_wav(out_wav: Path) -> Any | None:
    try:
        from interview_mux.run_context import RunContext

        parts = Path(out_wav).resolve().parts
        if "executions" in parts:
            return RunContext(parts[parts.index("executions") + 1], create=False)
    except Exception:
        return None
    return None


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
    cap = max(1, int(cfg.get("max_best_of_n") or 1))
    role_s = str(role or "")
    if role_s in {"theme_underscore"} or "underscore" in role_s:
        n = max(1, int(cfg.get("best_of_n_underscore") or 1))
    else:
        n = max(1, int(cfg.get("best_of_n_speech_free") or 1))
    return min(n, cap)


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


def _spawn_musicgen(
    *,
    py: Path,
    script: Path,
    req: Path,
    timeout: int,
    role: str | None,
    run_ctx: Any | None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    from interview_mux.operator_subprocess import touch_job_progress

    env = os.environ.copy()
    cache = musicgen_hf_home()
    try:
        cache.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    env.setdefault("HF_HOME", str(cache))
    env.setdefault("TRANSFORMERS_CACHE", str(cache))
    env.setdefault("HUGGINGFACE_HUB_CACHE", str(cache / "hub"))
    if extra_env:
        env.update(extra_env)
    proc_h = subprocess.Popen(
        [str(cli_python_executable(py)), str(script), str(req)],
        cwd=str(repo_root()),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=True,
    )
    waited = 0
    while proc_h.poll() is None and waited < timeout:
        if run_ctx is not None:
            try:
                touch_job_progress(
                    run_ctx,
                    f"MusicGen generating ({role or 'theme'})… {waited}s",
                    phase="musicgen",
                )
            except Exception:
                pass
        try:
            proc_h.wait(timeout=30)
        except subprocess.TimeoutExpired:
            waited += 30
            continue
    if proc_h.poll() is None:
        proc_h.kill()
        try:
            proc_h.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        return subprocess.CompletedProcess(proc_h.args, -9, "", f"timeout after {timeout}s")
    stdout, stderr = proc_h.communicate()
    return subprocess.CompletedProcess(proc_h.args, proc_h.returncode, stdout or "", stderr or "")


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
    use_melody = bool(musicgen_cfg().get("use_melody_conditioning", False))
    ph = prompt_hash(prompt, negative=negative_prompt, model_id=model_id)
    run_ctx = _run_ctx_for_out_wav(out_wav)
    device = effective_musicgen_device(run_ctx=run_ctx)
    meta: dict[str, Any] = {
        "duration_sec": dur,
        "role": role,
        "model_id": model_id,
        "melody_model_id": melody_model_id if melody_wav else None,
        "prompt": prompt[:240],
        "prompt_hash": ph,
        "seed": seed,
        "negative_prompt": (negative_prompt or "")[:200],
        "device": device,
    }
    if py and script.is_file():
        timeout = int(musicgen_cfg().get("request_timeout_sec") or 3600)
        lock_cm = None
        try:
            from filelock import FileLock

            lock_path = repo_root() / "ASSETS" / "local_musicgen" / "generate.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_cm = FileLock(str(lock_path), timeout=timeout + 1260)
        except Exception:
            lock_cm = None

        def _hub_has(mid: str) -> bool:
            slug = "models--" + str(mid).replace("/", "--")
            return (musicgen_hf_home() / "hub" / slug).is_dir()

        def _attempt(
            *,
            dev: str,
            mid: str,
            seconds: float,
            text: str,
            melody: bool,
            step: str,
            step_timeout: int,
        ) -> bool:
            payload = {
                "prompt": text,
                "negative_prompt": negative_prompt,
                "duration_sec": seconds,
                "out_wav": str(out_wav),
                "model_id": mid,
                "melody_model_id": melody_model_id,
                "seed": seed,
                "melody_wav": str(melody_wav)
                if melody and melody_wav and Path(melody_wav).is_file()
                else None,
                "use_melody_conditioning": bool(melody and use_melody),
                "device": dev,
            }
            req = out_wav.with_suffix(".request.json")
            req.write_text(json.dumps(payload), encoding="utf-8")
            extra = {}
            if mps_banned(run_ctx=run_ctx) or dev != "mps":
                extra[_BAN_MPS_ENV] = "1"
            proc = _spawn_musicgen(
                py=py,
                script=script,
                req=req,
                timeout=int(step_timeout),
                role=role,
                run_ctx=run_ctx,
                extra_env=extra,
            )
            meta["musicgen_returncode"] = proc.returncode
            meta["fidelity_step"] = step
            meta["model_id"] = mid
            meta["duration_sec"] = seconds
            if proc.returncode == 0 and out_wav.is_file() and out_wav.stat().st_size > 1000:
                meta["backend"] = "musicgen"
                meta["device"] = dev
                meta["stdout_tail"] = (proc.stdout or "")[-400:]
                return True
            meta["musicgen_stderr"] = (proc.stderr or "")[-800:]
            if proc.returncode == -9 and "timeout" in (proc.stderr or ""):
                meta["musicgen_error"] = proc.stderr
            if is_abort_returncode(proc.returncode) and bool(
                musicgen_cfg().get("ban_mps_on_abort", True)
            ):
                ban_mps(run_ctx=run_ctx, reason=f"returncode={proc.returncode}")
                meta["musicgen_abort"] = True
            return False

        bare = "Sparse acoustic guitar and piano instrumental, no vocals, podcast bed"
        min_sec = float(musicgen_cfg().get("min_duration_sec") or 4.0)
        steps: list[dict[str, Any]] = [
            {
                "dev": device,
                "mid": model_id,
                "seconds": dur,
                "text": prompt,
                "melody": True,
                "step": "full",
                "step_timeout": timeout,
            },
            {
                "dev": "cpu",
                "mid": model_id,
                "seconds": min(dur, min_sec),
                "text": bare,
                "melody": False,
                "step": "short_bare_cpu",
                "step_timeout": min(900, timeout),
            },
        ]
        for lighter in ("facebook/musicgen-medium", "facebook/musicgen-small"):
            if lighter != model_id and _hub_has(lighter):
                steps.append(
                    {
                        "dev": "cpu",
                        "mid": lighter,
                        "seconds": min_sec,
                        "text": bare,
                        "melody": False,
                        "step": f"cached_{lighter.split('/')[-1]}",
                        "step_timeout": min(300, timeout),
                    }
                )
                break

        try:
            if lock_cm is not None:
                lock_cm.acquire()
            ok = False
            for spec in steps:
                ok = _attempt(**spec)
                if ok:
                    break
                if meta.get("musicgen_abort") and spec.get("dev") != "cpu":
                    retry = dict(spec)
                    retry["dev"] = "cpu"
                    retry["step"] = str(spec.get("step") or "") + "_cpu"
                    ok = _attempt(**retry)
                    if ok:
                        break
            if ok:
                _write_generation_meta(out_wav, meta)
                return meta
        except Exception as exc:
            meta["musicgen_error"] = str(exc)[:400]
        finally:
            if lock_cm is not None:
                try:
                    lock_cm.release()
                except Exception:
                    pass

    # Always emit listenable notes if MusicGen timed out or failed — never silent mix.
    _write_musical_stub_wav(out_wav, duration_sec=dur, seed=int(seed or 0))
    meta["backend"] = "musical_stub"
    meta["warning"] = "MusicGen unavailable; wrote deterministic musical-note stub"
    _write_generation_meta(out_wav, meta)
    return meta
