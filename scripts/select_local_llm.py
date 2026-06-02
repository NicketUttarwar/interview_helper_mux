#!/usr/bin/env python3
"""
Select and optionally download the best-fit MLX local LLM using llmfit.

Writes ASSETS/local_llm/selection.json and downloads weights via download_local_llm.

Requires llmfit on PATH: brew install AlexsJones/llmfit/llmfit

Example:
  source .venv/bin/activate
  python scripts/select_local_llm.py --download --verify
  python scripts/select_local_llm.py --refresh --select-only
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from shutil import which

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from interview_mux.local_llm_config import DEFAULT_MODEL_ID  # noqa: E402
from interview_mux.local_llm_selection import (  # noqa: E402
    LLMFIT_RECOMMEND_CMD,
    build_fallback_manifest,
    build_manifest,
    fetch_llmfit_recommendations,
    llmfit_version,
    select_from_llmfit_json,
    selection_cache_valid,
    write_selection_manifest,
)

VENV_PY = ROOT / ".venv" / "bin" / "python"


def _ensure_llmfit() -> None:
    if which("llmfit") is None:
        print(
            "llmfit is not on PATH.\n"
            "Install (macOS):\n"
            "  brew install AlexsJones/llmfit/llmfit\n"
            "  # or: curl -fsSL https://llmfit.axjns.dev/install.sh | sh -s -- --local\n"
            "See SETUP.md § Local LLM.",
            file=sys.stderr,
        )
        sys.exit(1)


def _download(model_id: str, *, install_deps: bool) -> None:
    download_script = ROOT / "scripts" / "download_local_llm.py"
    cmd = [str(VENV_PY if VENV_PY.is_file() else sys.executable), str(download_script), "--model", model_id]
    if install_deps:
        cmd.append("--install-deps")
    subprocess.check_call(cmd)


def _verify(model_id: str | None) -> None:
    download_script = ROOT / "scripts" / "download_local_llm.py"
    cmd = [str(VENV_PY if VENV_PY.is_file() else sys.executable), str(download_script), "--verify"]
    if model_id:
        cmd.extend(["--model", model_id])
    subprocess.check_call(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--select-only",
        action="store_true",
        help="Write selection.json only; do not download weights",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download selected model weights after selection",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run mlx-lm smoke test after download",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore cached selection.json and re-run llmfit",
    )
    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="pip install mlx-lm and huggingface_hub before download",
    )
    parser.add_argument(
        "--fallback-model",
        default=DEFAULT_MODEL_ID,
        help=f"Model if llmfit has no eligible mlx-community candidates (default: {DEFAULT_MODEL_ID})",
    )
    parser.add_argument(
        "--min-quality",
        type=float,
        default=None,
        help="Override minimum quality score (default from local_llm_selection.MIN_QUALITY_SCORE)",
    )
    args = parser.parse_args()

    if not args.select_only and not args.download and not args.verify:
        # Default: select + download when invoked without flags (bootstrap-friendly)
        args.download = True

    if selection_cache_valid(refresh=args.refresh) and not args.refresh:
        from interview_mux.local_llm_selection import load_selection_manifest

        manifest = load_selection_manifest()
        model_id = str((manifest or {}).get("model_id") or DEFAULT_MODEL_ID)
        print(f"Using cached selection: {model_id}")
        if args.download:
            _download(model_id, install_deps=args.install_deps)
        if args.verify:
            _verify(model_id)
        return

    _ensure_llmfit()
    print(f"Running: {LLMFIT_RECOMMEND_CMD}")
    data, command = fetch_llmfit_recommendations()

    min_q = args.min_quality
    from interview_mux.local_llm_selection import MIN_QUALITY_SCORE

    best, all_candidates = select_from_llmfit_json(
        data,
        min_quality=min_q if min_q is not None else MIN_QUALITY_SCORE,
        fallback_model_id=args.fallback_model,
    )

    if best is None:
        print(
            f"No mlx-community models with fit perfect/good and quality >= "
            f"{min_q if min_q is not None else MIN_QUALITY_SCORE} "
            f"(parsed {len(all_candidates)} mlx-community rows). Using fallback.",
            file=sys.stderr,
        )
        manifest = build_fallback_manifest(args.fallback_model)
        model_id = args.fallback_model
    else:
        manifest = build_manifest(best, command=command)
        model_id = best.model_id
        print(
            f"Selected: {model_id} "
            f"(ctx={best.context_length}, fit={best.fit}, quality={best.quality:.1f}, "
            f"score={best.score:.1f})"
        )

    path = write_selection_manifest(manifest)
    print(f"Wrote {path}")
    print(f"llmfit: {llmfit_version()}")

    if args.select_only:
        return

    if args.download:
        _download(model_id, install_deps=args.install_deps)

    if args.verify:
        _verify(model_id)


if __name__ == "__main__":
    main()
