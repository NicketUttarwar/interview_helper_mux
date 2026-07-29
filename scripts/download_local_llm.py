#!/usr/bin/env python3
"""
Download MLX-compatible LLM weights into ASSETS/local_llm/.

Weights:  ASSETS/local_llm/models/<sanitized_repo_id>/
HF cache: ASSETS/local_llm/hf_cache/

Override: LOCAL_LLM_MODELS_DIR environment variable.

Requires (install once into the same venv):
  pip install mlx-lm huggingface_hub

Example:
  source .venv/bin/activate
  python scripts/download_local_llm.py --model mlx-community/Llama-3.2-3B-Instruct-4bit
  python scripts/download_local_llm.py --verify
  python scripts/select_local_llm.py --download --verify
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MLX_VENV = ROOT / "ASSETS" / "local_llm" / "venv"
VENV = MLX_VENV if MLX_VENV.is_dir() else ROOT / ".venv"
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from interview_mux.local_llm_config import (  # noqa: E402
    DEFAULT_MODEL_ID,
    default_hf_cache_dir,
    default_models_dir,
    repo_slug,
    resolve_model_id,
)

DEFAULT_MODEL = DEFAULT_MODEL_ID
ALT_MODELS = (
    "mlx-community/Mistral-7B-Instruct-v0.3-4bit",
    "mlx-community/Qwen2.5-7B-Instruct-4bit",
)


def _models_dir() -> Path:
    override = os.environ.get("LOCAL_LLM_MODELS_DIR", "").strip()
    if override:
        return Path(override)
    return default_models_dir()


def _hf_cache_dir() -> Path:
    return default_hf_cache_dir()


def _model_dir(repo_id: str) -> Path:
    return _models_dir() / repo_slug(repo_id)


def _ensure_venv() -> Path:
    py = VENV / "bin" / "python"
    if not py.is_file():
        print(
            "Missing MLX venv — run ./scripts/bootstrap_venv.sh first.",
            file=sys.stderr,
        )
        sys.exit(1)
    return py


def _missing_deps() -> list[str]:
    missing: list[str] = []
    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        missing.append("huggingface_hub")
    try:
        import mlx_lm  # noqa: F401
    except ImportError:
        missing.append("mlx-lm")
    return missing


def _install_deps(python: Path) -> None:
    import subprocess

    print("Installing mlx-lm and huggingface_hub into .venv ...")
    subprocess.check_call(
        [str(python), "-m", "pip", "install", "mlx-lm", "huggingface_hub"],
    )


def _download(repo_id: str, *, revision: str | None) -> Path:
    from huggingface_hub import snapshot_download

    dest = _model_dir(repo_id)
    hf_cache = _hf_cache_dir()
    dest.mkdir(parents=True, exist_ok=True)
    hf_cache.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("HF_HOME", str(hf_cache))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hf_cache))
    try:
        from interview_mux.config import huggingface_hub_token

        token = huggingface_hub_token()
        if token:
            os.environ.setdefault("HF_TOKEN", token)
            os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", token)
    except Exception:
        pass

    print(f"Downloading {repo_id} → {dest}")
    snapshot_download(
        repo_id=repo_id,
        revision=revision,
        local_dir=str(dest),
        local_dir_use_symlinks=False,
    )
    manifest = {
        "repo_id": repo_id,
        "revision": revision,
        "local_dir": str(dest),
        "hf_cache": str(hf_cache),
    }
    (dest / ".interview_mux_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Done. Manifest: {dest / '.interview_mux_manifest.json'}")
    return dest


def _verify(repo_id: str | None) -> None:
    from mlx_lm import generate, load

    models_dir = _models_dir()
    if repo_id:
        candidates = [_model_dir(repo_id)]
        if not candidates[0].is_dir():
            candidates = [Path(repo_id)]
    else:
        resolved = resolve_model_id()
        candidates = [_model_dir(resolved)]
        if not candidates[0].is_dir():
            candidates = sorted(models_dir.glob("*")) if models_dir.is_dir() else []

    if not candidates:
        print("No local models found. Run with --model <hf_repo_id> first.", file=sys.stderr)
        sys.exit(1)

    path = candidates[-1]
    manifest_path = path / ".interview_mux_manifest.json"
    load_id = repo_id or (
        json.loads(manifest_path.read_text(encoding="utf-8")).get("repo_id")
        if manifest_path.is_file()
        else str(path)
    )

    print(f"Loading {load_id} (smoke generate) ...")
    model, tokenizer = load(str(path if path.is_dir() else load_id))
    messages = [{"role": "user", "content": "Reply with exactly: ok"}]
    prompt = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
    )
    text = generate(model, tokenizer, prompt=prompt, max_tokens=16, verbose=False)
    print(f"Model response: {text!r}")
    print("Verify OK.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default=None,
        help=f"Hugging Face repo id (default: resolved from selection.json or {DEFAULT_MODEL})",
    )
    parser.add_argument("--revision", default=None, help="Optional git revision / tag")
    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="pip install mlx-lm and huggingface_hub into .venv before download",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Load model and run a one-line generation smoke test",
    )
    parser.add_argument(
        "--list-recommended",
        action="store_true",
        help="Print recommended MLX models and exit",
    )
    args = parser.parse_args()

    if args.list_recommended:
        print("Recommended MLX 4-bit models:")
        print(f"  default: {DEFAULT_MODEL}")
        for m in ALT_MODELS:
            print(f"  alt:     {m}")
        print("  auto:    python scripts/select_local_llm.py --download")
        return

    _ensure_venv()

    if args.install_deps:
        _install_deps(VENV / "bin" / "python")

    missing = _missing_deps()
    if missing:
        print(
            f"Missing packages: {', '.join(missing)}. "
            "Re-run with --install-deps or: pip install mlx-lm huggingface_hub",
            file=sys.stderr,
        )
        sys.exit(1)

    model = args.model or resolve_model_id()

    if args.verify:
        _verify(model if args.model else None)
        return

    _download(model, revision=args.revision)
    print()
    print("Next: python scripts/download_local_llm.py --verify")
    print("Active model_id:", repr(model))


if __name__ == "__main__":
    main()
