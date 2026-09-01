"""Local MusicGen runner for music-only theme stems."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import time
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


def _env_truthy(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes"}


def fail_closed_on_stub_roles() -> set[str]:
    raw = musicgen_cfg().get("fail_closed_on_stub_roles")
    if isinstance(raw, list) and raw:
        return {str(x).strip() for x in raw if str(x).strip()}
    return {"theme_cold_open", "theme_outro"}


def keep_prior_stem_on_fail() -> bool:
    return bool(musicgen_cfg().get("keep_prior_stem_on_fail", True))


def backup_prior_stem(out_wav: Path) -> bool:
    """Copy good on-disk stem to ``<wav>.prior.bak`` before regen."""
    if not keep_prior_stem_on_fail():
        return False
    out_wav = Path(out_wav)
    if not out_wav.is_file() or out_wav.stat().st_size < 1000:
        return False
    gen_path = out_wav.with_suffix(".gen.json")
    backend = ""
    if gen_path.is_file():
        try:
            gmeta = json.loads(gen_path.read_text(encoding="utf-8"))
            backend = str((gmeta or {}).get("backend") or "").strip().lower()
        except (OSError, json.JSONDecodeError):
            backend = ""
    if backend and backend not in {"musicgen", "mmaudio_backup"}:
        return False
    bak = Path(str(out_wav) + ".prior.bak")
    try:
        shutil.copy2(out_wav, bak)
        if gen_path.is_file():
            shutil.copy2(gen_path, Path(str(gen_path) + ".prior.bak"))
        return True
    except OSError:
        return False


def restore_prior_stem(out_wav: Path) -> dict[str, Any] | None:
    """Restore ``<wav>.prior.bak`` after failed regen; return meta patch or None."""
    out_wav = Path(out_wav)
    bak = Path(str(out_wav) + ".prior.bak")
    if not bak.is_file():
        return None
    try:
        shutil.copy2(bak, out_wav)
        gen_bak = Path(str(out_wav.with_suffix(".gen.json")) + ".prior.bak")
        gen_path = out_wav.with_suffix(".gen.json")
        if gen_bak.is_file():
            shutil.copy2(gen_bak, gen_path)
            try:
                gmeta = json.loads(gen_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                gmeta = {}
        else:
            gmeta = {}
        gmeta = dict(gmeta)
        gmeta["fallback"] = "kept_prior_stem"
        gmeta["prior_stem_kept"] = True
        _write_generation_meta(out_wav, gmeta)
        return gmeta
    except OSError:
        return None


def stub_allowed_for_role(role: str | None) -> bool:
    role_s = str(role or "").strip()
    if role_s in fail_closed_on_stub_roles():
        return False
    allowed = musicgen_cfg().get("stub_allowed_roles")
    if isinstance(allowed, list) and allowed:
        return role_s in {str(x).strip() for x in allowed}
    return True


def fail_closed_on_stub() -> bool:
    # E2E soft-escape after MusicGen OOM / quit loops (set by Full-auto driver).
    if _env_truthy("MUX_E2E_MUSICGEN_ALLOW_STUB"):
        return False
    return bool(musicgen_cfg().get("fail_closed_on_stub", True))


def e2e_musicgen_timeout_sec(default: int) -> int:
    """Optional override for MusicGen request timeout (seconds).

    MusicGen always runs the real model ladder first; this only caps hang safety.
    """
    raw = str(os.environ.get("MUX_E2E_MUSICGEN_TIMEOUT_SEC") or "").strip()
    if not raw:
        return int(default)
    try:
        return max(30, int(float(raw)))
    except ValueError:
        return int(default)


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
    """Delegate to heavy_task_policy (SIGABRT + SIGTERM + SIGKILL)."""
    from interview_mux.heavy_task_policy import is_heavy_kill_returncode

    return is_heavy_kill_returncode(code)


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


def _mps_available_for_musicgen() -> bool:
    """True when Apple Silicon MPS can be used by the MusicGen worker venv."""
    import platform

    if platform.system() != "Darwin":
        return False
    if platform.machine().lower() not in {"arm64", "aarch64"}:
        return False
    try:
        import torch

        return bool(torch.backends.mps.is_available() and torch.backends.mps.is_built())
    except Exception:
        # App .venv may lack torch; MusicGen venv on Apple Silicon still has MPS.
        return True


def effective_musicgen_device(*, requested: str | None = None, run_ctx: Any | None = None) -> str:
    """Resolve device. ``auto`` prefers GPU (MPS/CUDA) when available; falls back to CPU.

    MPS remains crash-guarded via ``ban_mps_on_abort`` / ``mps_banned``.
    """
    pref = str(
        requested if requested is not None else (musicgen_cfg().get("device") or "auto")
    ).strip().lower()
    if pref in {"", "auto"}:
        if not mps_banned(run_ctx=run_ctx) and _mps_available_for_musicgen():
            pref = "mps"
        else:
            try:
                import torch

                if torch.cuda.is_available():
                    pref = "cuda"
                else:
                    pref = "cpu"
            except Exception:
                pref = "cpu"
    if pref == "mps" and mps_banned(run_ctx=run_ctx):
        return "cpu"
    if pref == "mps" and not _mps_available_for_musicgen():
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
    """Soft duration guidance — floor only; no hard global max_duration_sec ceiling.

    Role bands from ``mmaudio.duration_bands_by_role`` raise short clips to the
    band floor. Longer full beds / bookends may exceed the soft band hi.
    """
    cfg = musicgen_cfg()
    lo = float(cfg.get("min_duration_sec") or 4.0)
    bands = (merged_config().get("mmaudio") or {}).get("duration_bands_by_role") or {}
    role_s = str(role or "").strip()
    if role_s and isinstance(bands.get(role_s), (list, tuple)) and len(bands[role_s]) >= 2:
        band_lo = float(bands[role_s][0])
        lo = max(lo, band_lo)
    # Soft advisory only — do not clamp downward to max_duration_sec.
    return max(lo, float(seconds))


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
    # Soft ops fallback when an op is missing on Metal (does not override device=cpu).
    env.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    if extra_env:
        env.update(extra_env)
    from interview_mux.gpu_exclusive import gpu_exclusive

    # One MusicGen subprocess at a time across the machine; cooldown after exit
    # so unified memory can settle before Chatterbox/MMAudio/MLX/next stem.
    with gpu_exclusive("musicgen", ctx=run_ctx, stage="musicgen"):
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
        result = subprocess.CompletedProcess(
            proc_h.args, proc_h.returncode, stdout or "", stderr or ""
        )
        from interview_mux.heavy_task_policy import record_heavy_abort

        record_heavy_abort(
            "musicgen",
            result.returncode,
            ctx=run_ctx,
            stage="musicgen",
        )
        return result


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
    backup_prior_stem(out_wav)
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
        cfg_block = musicgen_cfg()
        base_timeout = int(cfg_block.get("request_timeout_sec") or 900)
        # musicgen-large on CPU thrash is slow; use a tighter CPU budget and step down.
        # On MPS, keep the full request_timeout_sec (large ~3–15 min for short stems).
        if str(device).lower() == "cpu":
            base_timeout = int(
                cfg_block.get("cpu_request_timeout_sec")
                or min(base_timeout, 300)
            )
        timeout = e2e_musicgen_timeout_sec(base_timeout)
        step_down_timeout = int(
            cfg_block.get("step_down_timeout_sec") or min(480, timeout)
        )
        step_ratio = float(cfg_block.get("step_down_duration_ratio") or 0.85)
        pause_between = float(cfg_block.get("pause_between_ladder_steps_sec") or 0)
        # Ladder: configured primary (default large) → medium → small.
        # prefer_medium_on_cpu can skip large→medium when primary is still large on CPU.
        if (
            str(device).lower() == "cpu"
            and bool(cfg_block.get("prefer_medium_on_cpu", False))
            and model_id.endswith("-large")
        ):
            medium = "facebook/musicgen-medium"
            slug = "models--" + medium.replace("/", "--")
            if (musicgen_hf_home() / "hub" / slug).is_dir():
                model_id = medium
                meta["model_id"] = model_id
                meta["prefer_medium_on_cpu"] = True
        def _hub_has(mid: str) -> bool:
            slug = "models--" + mid.replace("/", "--")
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
            meta["ladder_step"] = step
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
                meta["musicgen_timeout"] = True
            if is_abort_returncode(proc.returncode) and bool(
                musicgen_cfg().get("ban_mps_on_abort", True)
            ):
                ban_mps(run_ctx=run_ctx, reason=f"returncode={proc.returncode}")
                meta["musicgen_abort"] = True
            return False

        # Model ladder: configured primary → medium → small; same prompt + planned duration.
        primary = str(model_id or "facebook/musicgen-large")
        ladder_models: list[str] = [primary]
        for lighter in ("facebook/musicgen-medium", "facebook/musicgen-small"):
            if lighter != primary and lighter not in ladder_models:
                ladder_models.append(lighter)

        steps: list[dict[str, Any]] = []
        for i, mid in enumerate(ladder_models):
            # Prefer hub-cached models for step-downs; always try primary.
            if i > 0 and not _hub_has(mid):
                continue
            step_name = "large" if "large" in mid else ("medium" if "medium" in mid else "small")
            step_seconds = dur if i == 0 else max(
                float(musicgen_cfg().get("min_duration_sec") or 4.0),
                dur * (step_ratio ** i),
            )
            # Keep step-downs on the same accelerator (MPS/CUDA). Forcing CPU here
            # recreated the exec_1765 thrash path on 16GB Apple Silicon after a
            # primary timeout. CPU is only used when device resolved to cpu, or via
            # the MPS-abort retry below.
            steps.append(
                {
                    "dev": device,
                    "mid": mid,
                    "seconds": step_seconds,
                    "text": prompt,
                    "melody": i == 0,
                    "step": f"ladder_{step_name}",
                    "step_timeout": timeout if i == 0 else step_down_timeout,
                    "attempt": i + 1,
                }
            )
        meta["model_ladder"] = [s["mid"] for s in steps]

        from interview_mux.heavy_task_policy import is_heavy_kill_returncode, wait_abort_backoff

        try:
            ok = False
            for idx, spec in enumerate(steps):
                meta["attempt"] = spec.get("attempt")
                ok = _attempt(**{k: v for k, v in spec.items() if k != "attempt"})
                if ok:
                    break
                if meta.get("musicgen_abort") and spec.get("dev") != "cpu":
                    retry = dict(spec)
                    retry["dev"] = "cpu"
                    retry["step"] = str(spec.get("step") or "") + "_cpu"
                    ok = _attempt(**{k: v for k, v in retry.items() if k != "attempt"})
                    if ok:
                        break
                rc = meta.get("musicgen_returncode")
                if is_heavy_kill_returncode(rc) and idx + 1 < len(steps):
                    wait_abort_backoff(run_ctx, "musicgen")
                elif pause_between > 0 and idx + 1 < len(steps):
                    time.sleep(pause_between)
            if ok:
                _write_generation_meta(out_wav, meta)
                return meta
        except Exception as exc:
            meta["musicgen_error"] = str(exc)[:400]

    if not stub_allowed_for_role(role):
        prior = restore_prior_stem(out_wav)
        if prior:
            meta.update(prior)
            return meta
        meta["backend"] = "musicgen_failed"
        meta["warning"] = "MusicGen failed; musical_stub blocked for role"
        meta["mmaudio_backup_suggested"] = bool(musicgen_cfg().get("mmaudio_backup_on_stub", True))
        _write_generation_meta(out_wav, meta)
        return meta

    # Always emit listenable notes if MusicGen timed out or failed — never silent mix.
    # Callers (sfx_mmaudio) may still try MMAudio when backend=musical_stub.
    _write_musical_stub_wav(out_wav, duration_sec=dur, seed=int(seed or 0))
    meta["backend"] = "musical_stub"
    meta["warning"] = "MusicGen unavailable; wrote deterministic musical-note stub"
    meta["mmaudio_backup_suggested"] = bool(musicgen_cfg().get("mmaudio_backup_on_stub", True))
    _write_generation_meta(out_wav, meta)
    return meta
