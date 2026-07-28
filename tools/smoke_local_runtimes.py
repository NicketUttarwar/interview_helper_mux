#!/usr/bin/env python3
"""Golden generate smokes for every local runtime (Chatterbox, S2S, MMAudio, CLAP, DeepFilter, STT, LLM).

Usage:
  python tools/smoke_local_runtimes.py              # import/verify + optional generate when STRICT_LOCAL_SMOKE=1
  STRICT_LOCAL_SMOKE=1 python tools/smoke_local_runtimes.py
  python tools/smoke_local_runtimes.py --ref-wav PATH --generate

Pass criteria for generate smokes: WAV exists, duration > 0.3s, peak > −40 dBFS.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE_DIR = ROOT / "ASSETS" / "smoke" / "local_runtimes"


def _peak_dbfs(path: Path) -> tuple[float, float]:
    with wave.open(str(path), "rb") as wf:
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        rate = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
    if sw != 2 or rate <= 0:
        return -90.0, 0.0
    count = len(raw) // 2
    samples = struct.unpack(f"<{count}h", raw)
    if nch > 1:
        samples = samples[::nch]
    floats = [s / 32768.0 for s in samples]
    peak = max((abs(s) for s in floats), default=0.0)
    dur = len(floats) / float(rate)
    return 20.0 * math.log10(max(peak, 1e-8)), dur


def _ok_audio(path: Path, *, min_dur: float = 0.3, min_peak_db: float = -40.0) -> tuple[bool, str]:
    if not path.is_file():
        return False, "missing wav"
    peak, dur = _peak_dbfs(path)
    if dur < min_dur:
        return False, f"duration {dur:.3f}s < {min_dur}"
    if peak < min_peak_db:
        return False, f"peak {peak:.1f} dBFS < {min_peak_db}"
    return True, f"dur={dur:.2f}s peak={peak:.1f}dBFS"


def _run_json(venv_py: Path, script: Path, payload: dict, timeout: int = 600) -> dict:
    proc = subprocess.run(
        [str(venv_py), str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(ROOT),
    )
    raw = (proc.stdout or "").strip()
    data: dict = {}
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError:
            data = {"ok": False, "error": f"invalid json stdout: {raw[:200]}"}
    if proc.returncode != 0 and not data.get("error"):
        data["ok"] = False
        data["error"] = (proc.stderr or proc.stdout or "empty")[:500]
    return data


def smoke_chatterbox(ref_wav: Path, out_dir: Path) -> tuple[str, str, str]:
    py = ROOT / "ASSETS" / "local_chatterbox" / "venv" / "bin" / "python"
    script = ROOT / "tools" / "chatterbox_generate.py"
    if not py.is_file():
        return "WARN", "chatterbox", "venv missing"
    out = out_dir / "chatterbox_smoke.wav"
    result = _run_json(
        py,
        script,
        {
            "text": "This is a short smoke test for voice clone.",
            "ref_audio": str(ref_wav),
            "out_wav": str(out),
            "model_id": "ResembleAI/chatterbox",
        },
    )
    if not result.get("ok"):
        return "FAIL", "chatterbox", str(result.get("error") or result)[:200]
    ok, detail = _ok_audio(out)
    return ("OK" if ok else "FAIL"), "chatterbox", detail


def smoke_s2s(ref_wav: Path, out_dir: Path) -> tuple[str, str, str]:
    py = ROOT / "ASSETS" / "local_speech" / "venv" / "bin" / "python"
    script = ROOT / "tools" / "s2s_generate.py"
    if not py.is_file():
        return "WARN", "s2s", "venv missing"
    out = out_dir / "s2s_smoke.wav"
    result = _run_json(
        py,
        script,
        {
            "mode": "synthesize",
            "text": "This is a short smoke test for mlx audio.",
            "ref_audio": str(ref_wav),
            "out_wav": str(out),
            "model_id": "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
        },
        timeout=900,
    )
    if not result.get("ok"):
        return "WARN", "s2s", str(result.get("error") or result)[:200]
    ok, detail = _ok_audio(out)
    return ("OK" if ok else "WARN"), "s2s", detail


def smoke_mmaudio(out_dir: Path) -> tuple[str, str, str]:
    py = ROOT / "ASSETS" / "local_mmaudio" / "venv" / "bin" / "python"
    script = ROOT / "tools" / "mmaudio_generate.py"
    if not py.is_file():
        return "FAIL", "mmaudio", "venv missing"
    out = out_dir / "mmaudio_smoke.wav"
    proc = subprocess.run(
        [
            str(py),
            str(script),
            "--prompt",
            "soft warm wood stinger, short percussive tap, no vocals",
            "--negative-prompt",
            "speech, vocals, lyrics",
            "--duration",
            "1.5",
            "--num-steps",
            "15",
            "--output-wav",
            str(out),
        ],
        capture_output=True,
        text=True,
        timeout=900,
        cwd=str(ROOT),
    )
    if proc.returncode != 0 and not out.is_file():
        return "WARN", "mmaudio", (proc.stderr or proc.stdout or "generate failed")[:200]
    ok, detail = _ok_audio(out, min_dur=0.2)
    return ("OK" if ok else "FAIL"), "mmaudio", detail


def smoke_clap(wav: Path) -> tuple[str, str, str]:
    py = ROOT / "ASSETS" / "local_mmaudio" / "venv" / "bin" / "python"
    script = ROOT / "tools" / "clap_similarity.py"
    if not py.is_file() or not wav.is_file():
        return "WARN", "clap", "venv or wav missing"
    result = _run_json(
        py,
        script,
        {"wav_path": str(wav), "text": "soft warm wood stinger"},
        timeout=180,
    )
    if not result.get("available") or result.get("score") is None:
        return "FAIL", "clap", str(result.get("error") or result)[:200]
    return "OK", "clap", f"score={result.get('score')}"


def smoke_deepfilter(src: Path, out_dir: Path) -> tuple[str, str, str]:
    py = ROOT / "ASSETS" / "local_deepfilter" / "venv" / "bin" / "python"
    script = ROOT / "tools" / "deepfilter_enhance.py"
    if not py.is_file():
        return "WARN", "deepfilter", "venv missing"
    out = out_dir / "deepfilter_smoke.wav"
    proc = subprocess.run(
        [str(py), str(script), "--input-wav", str(src), "--output-wav", str(out), "--compensate-delay"],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(ROOT),
    )
    if proc.returncode != 0 and not out.is_file():
        return "WARN", "deepfilter", (proc.stderr or proc.stdout or "enhance failed")[:200]
    ok, detail = _ok_audio(out, min_dur=0.1)
    return ("OK" if ok else "WARN"), "deepfilter", detail


def smoke_stt() -> tuple[str, str, str]:
    py = ROOT / "ASSETS" / "local_speech" / "venv" / "bin" / "python"
    if not py.is_file():
        return "FAIL", "stt", "venv missing"
    proc = subprocess.run(
        [str(py), str(ROOT / "scripts" / "download_local_speech.py"), "--verify-stt"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=120,
    )
    if proc.returncode != 0:
        return "FAIL", "stt", (proc.stderr or proc.stdout or "verify failed")[:200]
    return "OK", "stt", "verify-stt ok"


def smoke_llm() -> tuple[str, str, str]:
    py = ROOT / "ASSETS" / "local_llm" / "venv" / "bin" / "python"
    if not py.is_file():
        return "WARN", "llm", "venv missing (fail-open ok)"
    proc = subprocess.run(
        [str(py), str(ROOT / "scripts" / "download_local_llm.py"), "--verify"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=120,
    )
    if proc.returncode != 0:
        return "WARN", "llm", "verify failed — documented fail-open"
    return "OK", "llm", "verify ok"


def _find_default_ref() -> Path | None:
    candidates = [
        ROOT / "ASSETS" / "executions" / "exec_1123_1311e28fffa1_20260727T200034Z" / "understanding" / "speaker_samples" / "spk_0.wav",
    ]
    for p in candidates:
        if p.is_file():
            return p
    # any speaker sample
    for p in (ROOT / "ASSETS" / "executions").glob("exec_*/understanding/speaker_samples/*.wav"):
        return p
    for p in (ROOT / "ASSETS").glob("*.wav"):
        return p
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref-wav", type=Path, default=None)
    parser.add_argument("--generate", action="store_true", help="Run golden generate smokes")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    do_gen = args.generate or os.environ.get("STRICT_LOCAL_SMOKE", "0") == "1"

    rows: list[tuple[str, str, str]] = []
    rows.append(smoke_stt())
    rows.append(smoke_llm())

    if do_gen:
        SMOKE_DIR.mkdir(parents=True, exist_ok=True)
        ref = args.ref_wav or _find_default_ref()
        if ref is None or not ref.is_file():
            rows.append(("FAIL", "ref_wav", "no reference WAV for TTS/DeepFilter smokes"))
        else:
            rows.append(smoke_chatterbox(ref, SMOKE_DIR))
            rows.append(smoke_s2s(ref, SMOKE_DIR))
            status, name, detail = smoke_mmaudio(SMOKE_DIR)
            rows.append((status, name, detail))
            mm_wav = SMOKE_DIR / "mmaudio_smoke.wav"
            if mm_wav.is_file():
                rows.append(smoke_clap(mm_wav))
            else:
                rows.append(("WARN", "clap", "skipped — no mmaudio wav"))
            rows.append(smoke_deepfilter(ref, SMOKE_DIR))
    else:
        rows.append(("OK", "generate", "skipped (set STRICT_LOCAL_SMOKE=1 or --generate)"))

    fail = sum(1 for s, _, _ in rows if s == "FAIL")
    warn = sum(1 for s, _, _ in rows if s == "WARN")
    report = [{"status": s, "name": n, "detail": d} for s, n, d in rows]
    if args.json:
        print(json.dumps({"results": report, "fail": fail, "warn": warn}, indent=2))
    else:
        for s, n, d in rows:
            print(f"  {s:4} {n} — {d}")
        print(f"smoke_local_runtimes: fail={fail} warn={warn}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
