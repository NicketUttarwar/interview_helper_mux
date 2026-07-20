#!/usr/bin/env python3
"""Select local speech models (STT + S2S) for this machine."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from interview_mux.hardware_detect import is_apple_silicon  # noqa: E402
from interview_mux.local_model_selection import (  # noqa: E402
    build_speech_selection,
    speech_selection_path,
    write_json_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--select-only", action="store_true")
    args = parser.parse_args()

    if not is_apple_silicon():
        print("SKIP: local speech selection requires Apple Silicon.")
        return

    payload = build_speech_selection(source="tier_fallback")
    path = write_json_manifest(speech_selection_path(), payload)
    print(f"Wrote {path}")
    print(f"  stt_model_id={payload['stt_model_id']}")
    print(f"  s2s_model_id={payload['s2s_model_id']}")
    print(f"  ram_gb={payload['ram_gb']}")


if __name__ == "__main__":
    main()
