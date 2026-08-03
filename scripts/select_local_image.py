#!/usr/bin/env python3
"""
Select best-fit MLX text-to-image model for this Apple Silicon Mac.

Writes ASSETS/local_image/selection.json including prompt_max_tokens.
Mirrors select_local_llm.py (hardware-fit catalog; llmfit is LLM-only).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Ranked catalog: prefer first that fits estimated unified memory (GB).
IMAGE_CATALOG: list[dict] = [
    {
        "model_id": "argmaxinc/mlx-FLUX.1-schnell-4bit-quantized",
        "backend": "mflux",
        "prompt_max_tokens": 256,
        "prompt_encoder": "t5",
        "native_size": 1024,
        "recommended_steps": 4,
        "min_unified_gb": 18,
        "approx_gb": 12,
    },
    {
        "model_id": "mlx-community/FLUX.1-schnell-4bit",
        "backend": "mflux",
        "prompt_max_tokens": 256,
        "prompt_encoder": "t5",
        "native_size": 1024,
        "recommended_steps": 4,
        "min_unified_gb": 16,
        "approx_gb": 10,
    },
    {
        "model_id": "mlx-community/stable-diffusion-2-1-4bit",
        "backend": "mlx_sd",
        "prompt_max_tokens": 77,
        "prompt_encoder": "clip",
        "native_size": 768,
        "recommended_steps": 20,
        "min_unified_gb": 8,
        "approx_gb": 4,
    },
]

DEFAULT_FALLBACK = IMAGE_CATALOG[-1]


def _unified_memory_gb() -> float:
    if sys.platform != "darwin":
        return 0.0
    try:
        out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
        return int(out) / (1024**3)
    except Exception:
        return 16.0


def select_model(mem_gb: float) -> dict:
    for row in IMAGE_CATALOG:
        if mem_gb >= float(row["min_unified_gb"]):
            return dict(row)
    return dict(DEFAULT_FALLBACK)


def write_selection(row: dict, *, mem_gb: float) -> Path:
    out_dir = ROOT / "ASSETS" / "local_image"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "selection.json"
    payload = {
        **row,
        "selected_at": datetime.now(timezone.utc).isoformat(),
        "selected_reason": f"fits ~{mem_gb:.1f} GB unified memory (needs ≥{row['min_unified_gb']} GB)",
        "host_unified_gb": round(mem_gb, 2),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Also download weights")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    if sys.platform != "darwin" or os.uname().machine != "arm64":
        print("SKIP: Apple Silicon only")
        return 0

    mem = _unified_memory_gb()
    row = select_model(mem)
    path = write_selection(row, mem_gb=mem)
    print(f"Selected {row['model_id']} → {path}")
    print(f"  prompt_max_tokens={row['prompt_max_tokens']} encoder={row['prompt_encoder']}")

    if args.download or args.verify:
        from pathlib import Path as _P

        script = ROOT / "scripts" / "download_local_image.py"
        cmd = [sys.executable, str(script)]
        if args.download:
            cmd.append("--download")
        if args.verify:
            cmd.append("--verify")
        return subprocess.call(cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
