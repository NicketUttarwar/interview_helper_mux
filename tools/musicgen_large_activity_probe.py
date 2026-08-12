#!/usr/bin/env python3
"""Fresh instrumented probe: does facebook/musicgen-large finish on this Mac?

Samples CPU / RSS / threads every --sample-sec while generating a short stinger.
Classifies activity so we can tell "slow but working" vs "dead hang" vs "swap thrash".

Example:
  INTERVIEW_MUX_GPU_COOLDOWN_SEC=5 \\
    .venv/bin/python -u tools/musicgen_large_activity_probe.py --timeout 1800 --duration 6
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path


def _sample(pid: int) -> dict:
    try:
        out = subprocess.check_output(
            ["ps", "-o", "pid=,pcpu=,pmem=,rss=,vsz=,time=,state=", "-p", str(pid)],
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return {"alive": False}
    if not out:
        return {"alive": False}
    parts = out.split()
    # pid pcpu pmem rss vsz TIME STATE — TIME may be like 0:12.34 or 1:02:03
    if len(parts) < 7:
        return {"alive": False, "raw": out}
    return {
        "alive": True,
        "pid": int(parts[0]),
        "pcpu": float(parts[1]),
        "pmem": float(parts[2]),
        "rss_mb": round(int(parts[3]) / 1024.0, 1),
        "vsz_mb": round(int(parts[4]) / 1024.0, 1),
        "cpu_time": parts[5],
        "state": parts[6],
    }


def _vm_pressure() -> dict:
    """Best-effort macOS memory snapshot."""
    try:
        raw = subprocess.check_output(["vm_stat"], text=True)
    except (OSError, subprocess.CalledProcessError):
        return {}
    page = 16384
    vals: dict[str, int] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        digits = "".join(ch for ch in v if ch.isdigit())
        if digits:
            vals[k.strip()] = int(digits)
    free = vals.get("Pages free", 0) * page / (1024**3)
    speculative = vals.get("Pages speculative", 0) * page / (1024**3)
    compressed = vals.get("Pages stored in compressor", 0) * page / (1024**3)
    swapouts = vals.get("Swapouts", 0)
    return {
        "free_gb": round(free + speculative, 2),
        "compressor_gb": round(compressed, 2),
        "swapouts": swapouts,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--timeout", type=int, default=1800, help="Wall budget seconds (default 30m)")
    ap.add_argument("--duration", type=float, default=6.0, help="Audio seconds to generate")
    ap.add_argument("--sample-sec", type=float, default=15.0)
    ap.add_argument("--device", default="mps", help="Device for request (default mps)")
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output wav under ASSETS/local_musicgen/probe/",
    )
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    os.environ.setdefault("INTERVIEW_MUX_GPU_COOLDOWN_SEC", "5")
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    from interview_mux.music_motif import compile_musicgen_prompt, default_motif_family
    from interview_mux.musicgen_runner import (
        cli_python_executable,
        effective_musicgen_device,
        musicgen_hf_home,
        musicgen_venv_python,
    )
    from interview_mux.gpu_exclusive import gpu_exclusive

    brief = {
        "show_identity": {
            "genre_hint": "acoustic conversational documentary instrumental",
            "mood": "determined",
            "instrumentation_prefs": [
                "acoustic guitar",
                "punchy piano",
                "warm electric bass",
                "soft strings",
            ],
            "key_center": "G",
            "scale_or_mode": "major_bright",
        },
        "motif_seeds": {"keywords": ["conviction", "gratitude"]},
        "narrative_spine": {"acts": []},
    }
    prompt, neg = compile_musicgen_prompt(
        brief=brief,
        motif=default_motif_family(brief),
        role="theme_emphasis",
        palette_kind="stinger",
        wpm=140,
    )

    out = args.out or (
        root / "ASSETS" / "local_musicgen" / "probe" / "fresh_large_activity_30min.wav"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    for stale in out.parent.glob("fresh_large_activity_30min*"):
        if stale != out:
            try:
                stale.unlink()
            except OSError:
                pass

    device = str(args.device).strip().lower()
    if device == "auto":
        device = effective_musicgen_device()
    py = musicgen_venv_python()
    script = root / "tools" / "musicgen_generate.py"
    if py is None or not py.is_file():
        print("FAIL: musicgen venv missing", file=sys.stderr)
        return 1

    payload = {
        "prompt": prompt,
        "negative_prompt": neg,
        "duration_sec": float(args.duration),
        "out_wav": str(out),
        "model_id": "facebook/musicgen-large",
        "melody_model_id": None,
        "seed": 20260812,
        "melody_wav": None,
        "use_melody_conditioning": False,
        "device": device,
    }
    req = out.with_suffix(".request.json")
    req.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    env = os.environ.copy()
    cache = musicgen_hf_home()
    cache.mkdir(parents=True, exist_ok=True)
    env.setdefault("HF_HOME", str(cache))
    env.setdefault("TRANSFORMERS_CACHE", str(cache))
    env.setdefault("HUGGINGFACE_HUB_CACHE", str(cache / "hub"))
    env.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    print(f"model=facebook/musicgen-large device={device} duration={args.duration}s")
    print(f"timeout={args.timeout}s sample_every={args.sample_sec}s")
    print(f"request={req}")
    print(f"out={out}")
    sys.stdout.flush()

    samples: list[dict] = []
    t0 = time.monotonic()
    classification = "unknown"

    with gpu_exclusive("musicgen"):
        cmd = [str(cli_python_executable(py)), str(script), str(req)]
        proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,
        )
        print(f"spawned pid={proc.pid}")
        sys.stdout.flush()

        last_sample = 0.0
        while True:
            elapsed = time.monotonic() - t0
            if proc.poll() is not None:
                break
            if elapsed >= float(args.timeout):
                proc.kill()
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
                classification = "killed_timeout"
                break
            if elapsed - last_sample >= float(args.sample_sec) or last_sample == 0.0:
                row = _sample(proc.pid)
                row["elapsed_sec"] = round(elapsed, 1)
                row["vm"] = _vm_pressure()
                samples.append(row)
                print(
                    f"t={row['elapsed_sec']:6.1f}s "
                    f"cpu={row.get('pcpu', 0):5.1f}% "
                    f"rss={row.get('rss_mb', 0):7.1f}MB "
                    f"state={row.get('state')} "
                    f"cputime={row.get('cpu_time')} "
                    f"free_gb={row.get('vm', {}).get('free_gb')} "
                    f"compressor_gb={row.get('vm', {}).get('compressor_gb')}"
                )
                sys.stdout.flush()
                last_sample = elapsed
            time.sleep(min(2.0, float(args.sample_sec) / 3.0))

        stdout, stderr = proc.communicate() if proc.poll() is not None else ("", "")
        # If we killed, communicate may already be done.
        if proc.stdout and not stdout:
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except Exception:
                pass

    elapsed = time.monotonic() - t0
    ok = (
        proc.returncode == 0
        and out.is_file()
        and out.stat().st_size > 1000
        and classification != "killed_timeout"
    )

    # Activity classification from samples (ignore final dead sample).
    live = [s for s in samples if s.get("alive")]
    max_cpu = max((float(s.get("pcpu") or 0) for s in live), default=0.0)
    mean_cpu = (
        sum(float(s.get("pcpu") or 0) for s in live) / len(live) if live else 0.0
    )
    max_rss = max((float(s.get("rss_mb") or 0) for s in live), default=0.0)
    # CPU time string growth is a strong "still working" signal.
    cpu_times = [str(s.get("cpu_time") or "") for s in live]
    cpu_time_grew = len(set(cpu_times)) > 1

    if ok:
        classification = "completed"
    elif classification != "killed_timeout":
        classification = "failed_exit"

    if not ok:
        if mean_cpu < 2.0 and not cpu_time_grew and elapsed > 60:
            activity = "likely_hung_idle"
        elif max_rss > 6000 and mean_cpu < 15 and float(live[-1].get("vm", {}).get("compressor_gb") or 0) > 4:
            activity = "likely_memory_thrash"
        elif cpu_time_grew or mean_cpu >= 10:
            activity = "actively_working_but_incomplete"
        else:
            activity = "unclear"
    else:
        activity = "actively_working_completed"

    report = {
        "case": "fresh_large_activity_probe",
        "model_id": "facebook/musicgen-large",
        "device": device,
        "duration_sec": float(args.duration),
        "timeout_budget_sec": int(args.timeout),
        "elapsed_sec": round(elapsed, 1),
        "returncode": proc.returncode,
        "ok": ok,
        "bytes": out.stat().st_size if out.is_file() else 0,
        "classification": classification,
        "activity": activity,
        "metrics": {
            "samples": len(samples),
            "max_pcpu": round(max_cpu, 1),
            "mean_pcpu": round(mean_cpu, 1),
            "max_rss_mb": round(max_rss, 1),
            "cpu_time_grew": cpu_time_grew,
            "ru_maxrss_mb": round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024.0, 1),
        },
        "samples": samples,
        "stdout_tail": (stdout or "")[-400:],
        "stderr_tail": (stderr or "")[-800:],
        "out_wav": str(out),
        "interpretation": {
            "actively_working_whole_time": bool(cpu_time_grew or mean_cpu >= 10),
            "would_30min_likely_help": bool(
                (not ok)
                and (cpu_time_grew or mean_cpu >= 10)
                and classification == "killed_timeout"
                and activity == "actively_working_but_incomplete"
            ),
        },
    }
    report_path = out.with_suffix(".activity_report.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, indent=2))
    print(f"wrote {report_path}")
    if ok:
        print(
            f"ANSWER: YES — large finished in {elapsed:.0f}s on {device} "
            f"(activity={activity})"
        )
        return 0
    print(
        f"ANSWER: NO — large did not finish "
        f"(classification={classification} activity={activity} elapsed={elapsed:.0f}s)"
    )
    if report["interpretation"]["would_30min_likely_help"]:
        print(
            "NOTE: samples show active CPU progress when killed — "
            "a longer budget might help, but ship path should stay on medium."
        )
    elif activity == "likely_memory_thrash":
        print(
            "NOTE: high RSS / compressor with weak CPU — thrashing, not steady progress; "
            "more wall time alone is unlikely to fix large on 16GB."
        )
    elif activity == "likely_hung_idle":
        print("NOTE: process was idle — hung, not merely slow.")
    return 2 if classification == "killed_timeout" else 1


if __name__ == "__main__":
    raise SystemExit(main())
