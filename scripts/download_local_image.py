#!/usr/bin/env python3
"""Download / verify local MLX image model from ASSETS/local_image/selection.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "ASSETS" / "local_image" / "selection.json"
MODELS = ROOT / "ASSETS" / "local_image" / "models"


def _selection() -> dict:
    if not SELECTION.is_file():
        print("No selection.json — run scripts/select_local_image.py first", file=sys.stderr)
        sys.exit(1)
    return json.loads(SELECTION.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    sel = _selection()
    model_id = str(sel.get("model_id") or "")
    MODELS.mkdir(parents=True, exist_ok=True)

    if args.download:
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            print("huggingface_hub missing in this interpreter", file=sys.stderr)
            return 1
        print(f"Downloading {model_id}…")
        snapshot_download(repo_id=model_id, local_dir=str(MODELS / model_id.replace("/", "__")))
        print("Download complete.")

    if args.verify:
        # Soft verify: selection present + venv python importable later
        if not model_id:
            print("VERIFY FAIL: empty model_id", file=sys.stderr)
            return 1
        print(f"VERIFY OK: selection model_id={model_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
