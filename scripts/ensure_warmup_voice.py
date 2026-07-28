#!/usr/bin/env python3
"""Create ASSETS/local_speech/warmup_voice/neutral.wav for probe warm-up TTS."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.warmup_voice import ensure_neutral_warmup_voice  # noqa: E402


def main() -> int:
    path = ensure_neutral_warmup_voice()
    print(path)
    return 0 if path.is_file() else 1


if __name__ == "__main__":
    raise SystemExit(main())
