#!/usr/bin/env python3
"""Verify / smoke-test local speech stack (mlx-audio)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEECH_PY = ROOT / "ASSETS" / "local_speech" / "venv" / "bin" / "python"
PY = SPEECH_PY if SPEECH_PY.is_file() else ROOT / ".venv" / "bin" / "python"


def _run_tool(script: str, flag: str) -> bool:
    import subprocess

    cmd = [str(PY), str(ROOT / "tools" / script), flag]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        print((proc.stderr or proc.stdout or "verify failed")[:500], file=sys.stderr)
        return False
    return True


def _verify_diarization() -> bool:
    import subprocess

    code = (
        "from mlx_audio.vad import load\n"
        "load('mlx-community/diar_sortformer_4spk-v1-fp32')\n"
        "print('ok diarization')"
    )
    proc = subprocess.run(
        [str(PY), "-c", code],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    )
    if proc.returncode != 0:
        print((proc.stderr or proc.stdout or "diarization verify failed")[:800], file=sys.stderr)
        return False
    print((proc.stdout or "").strip() or "ok diarization")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-stt", action="store_true")
    parser.add_argument("--verify-s2s", action="store_true")
    parser.add_argument(
        "--verify-diarization",
        action="store_true",
        help="Import mlx_audio.vad and load Sortformer (identity classify).",
    )
    parser.add_argument("--verify", action="store_true", help="Verify STT + S2S")
    args = parser.parse_args()
    if args.verify:
        args.verify_stt = True
        args.verify_s2s = True

    ok = True
    if args.verify_stt:
        ok = _run_tool("stt_transcribe.py", "--verify") and ok
    if args.verify_s2s:
        ok = _run_tool("s2s_generate.py", "--verify") and ok
    if args.verify_diarization:
        ok = _verify_diarization() and ok
    if not args.verify_stt and not args.verify_s2s and not args.verify_diarization:
        parser.print_help()
        sys.exit(2)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
