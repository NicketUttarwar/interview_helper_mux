#!/usr/bin/env python3
"""
Prefetch faster-whisper model weights into ASSETS/local_stt/models/.

Example:
  source .venv/bin/activate
  python scripts/download_local_stt.py --model base
  python scripts/download_local_stt.py --verify
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

DEFAULT_MODEL = "base"


def _weights_dir() -> Path:
    from interview_mux.config import merged_config, repo_root

    cfg = merged_config()
    block = cfg.get("disfluency_extract") or {}
    rel = block.get("weights_dir") or "ASSETS/local_stt/models"
    p = Path(str(rel))
    if not p.is_absolute():
        p = repo_root() / p
    return p


def download(model: str) -> Path:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        print("Missing faster-whisper — pip install faster-whisper", file=sys.stderr)
        raise SystemExit(1) from exc

    dest = _weights_dir()
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Whisper '{model}' into {dest} …")
    WhisperModel(model, device="cpu", compute_type="int8", download_root=str(dest))
    print(f"Done — weights cached under {dest}")
    return dest


def verify(model: str) -> bool:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster-whisper not installed")
        return False
    dest = _weights_dir()
    try:
        WhisperModel(model, device="cpu", compute_type="int8", download_root=str(dest))
        print(f"OK — model '{model}' loadable from {dest}")
        return True
    except Exception as exc:
        print(f"Verify failed: {exc}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Download local faster-whisper weights")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Whisper model size/name")
    parser.add_argument("--verify", action="store_true", help="Verify model loads")
    args = parser.parse_args()
    if args.verify:
        raise SystemExit(0 if verify(args.model) else 1)
    download(args.model)


if __name__ == "__main__":
    main()
