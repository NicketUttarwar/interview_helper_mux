#!/usr/bin/env bash
# Bootstrap DeepFilterNet and MMAudio isolated venvs under ASSETS/ (v2 — no MLX).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${PYTHON:-/opt/homebrew/bin/python3.12}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3.12 || command -v python3)"
fi

CORE_PY="$ROOT/.venv/bin/python"
if [[ -x "$CORE_PY" ]]; then
  PY_DETECT="$CORE_PY"
else
  PY_DETECT="$PY"
fi

TORCH_DEVICE="$("$PY_DETECT" -c 'from interview_mux.hardware_detect import detect_torch_device; print(detect_torch_device())')"
TORCH_INDEX="$("$PY_DETECT" -c 'from interview_mux.hardware_detect import torch_index_url; print(torch_index_url())')"

echo "Torch device: $TORCH_DEVICE (index: $TORCH_INDEX)"

if ! command -v rustc >/dev/null 2>&1; then
  echo "WARN: rustc not on PATH — DeepFilterNet native build will be skipped."
  echo "  Install Rust before preclean: brew install rust"
fi

bash "$ROOT/scripts/clone_local_audio_repos.sh"

bootstrap_venv() {
  local runtime_id="$1"
  local venv_dir="$2"
  local req_file="$3"
  echo "=== Bootstrap $runtime_id venv: $venv_dir ==="
  rm -rf "$venv_dir"
  "$PY" -m venv "$venv_dir"
  # shellcheck source=/dev/null
  source "$venv_dir/bin/activate"
  pip install -U pip setuptools wheel
  if [[ -f "$req_file" ]]; then
    pip install -r "$req_file"
  fi
  deactivate
}

install_torch() {
  local venv_dir="$1"
  local pin="${2:-}"
  # shellcheck source=/dev/null
  source "$venv_dir/bin/activate"
  if [[ -n "$pin" ]]; then
    pip install "torch==${pin}" "torchaudio==${pin}" --index-url "$TORCH_INDEX"
  else
    pip install torch torchaudio --index-url "$TORCH_INDEX"
  fi
  deactivate
}

DF_VENV="$ROOT/ASSETS/local_deepfilter/venv"
MM_VENV="$ROOT/ASSETS/local_mmaudio/venv"
DF_REPO="$ROOT/ASSETS/local_deepfilter/DeepFilterNet"
MM_REPO="$ROOT/ASSETS/local_mmaudio/MMAudio"

DF_PY_PKG="$DF_REPO/DeepFilterNet"
DF_TORCH_PIN="2.5.1"

bootstrap_venv deepfilter "$DF_VENV" "$ROOT/requirements-local-deepfilter.txt"
install_torch "$DF_VENV" "$DF_TORCH_PIN"
# shellcheck source=/dev/null
source "$DF_VENV/bin/activate"
if [[ -d "$DF_REPO/pyDF" ]]; then
  if command -v rustc >/dev/null 2>&1; then
    maturin develop --release -m "$DF_REPO/pyDF/Cargo.toml"
    pip install -e "$DF_PY_PKG"
  else
    echo "SKIP DeepFilterNet maturin build (Rust not installed)." >&2
  fi
fi
deactivate

bootstrap_venv mmaudio "$MM_VENV" "$ROOT/requirements-local-mmaudio.txt"
install_torch "$MM_VENV"
# shellcheck source=/dev/null
source "$MM_VENV/bin/activate"
pip install -e "$MM_REPO"
deactivate

VERIFY_FAILED=0
DF_VERIFIED=False
MM_VERIFIED=False
if [[ -x "$DF_VENV/bin/python" ]]; then
  if "$DF_VENV/bin/python" "$ROOT/tools/deepfilter_enhance.py" --verify; then
    DF_VERIFIED=True
  else
    VERIFY_FAILED=1
    echo "WARN: DeepFilterNet verify failed — preclean unavailable until Rust is installed." >&2
  fi
fi
if [[ -x "$MM_VENV/bin/python" ]]; then
  if "$MM_VENV/bin/python" "$ROOT/tools/mmaudio_generate.py" --verify --repo "$MM_REPO"; then
    MM_VERIFIED=True
  else
    VERIFY_FAILED=1
  fi
else
  VERIFY_FAILED=1
fi

if [[ -x "$CORE_PY" ]]; then
  "$CORE_PY" -c "
from pathlib import Path
from interview_mux.local_runtime import write_install_manifest
root = Path('$ROOT')
write_install_manifest(
    root / 'ASSETS/local_deepfilter',
    runtime_id='deepfilter',
    repo_url='https://github.com/rikorose/deepfilternet.git',
    repo_dir=root / 'ASSETS/local_deepfilter/DeepFilterNet',
    venv_dir=root / 'ASSETS/local_deepfilter/venv',
    verified=$DF_VERIFIED,
)
write_install_manifest(
    root / 'ASSETS/local_mmaudio',
    runtime_id='mmaudio',
    repo_url='https://github.com/hkchengrex/MMAudio.git',
    repo_dir=root / 'ASSETS/local_mmaudio/MMAudio',
    venv_dir=root / 'ASSETS/local_mmaudio/venv',
    verified=$MM_VERIFIED,
)
"
fi

if [[ "$MM_VERIFIED" != "True" ]]; then
  echo "ERROR: MMAudio runtime verify failed (required for SFX stages)." >&2
  echo "  Run: ./scripts/verify_local_models.sh" >&2
  exit 1
fi

if [[ "$DF_VERIFIED" != "True" ]]; then
  echo "WARN: DeepFilterNet not verified — install Rust and re-run bootstrap for preclean."
fi

echo "Local runtimes bootstrapped (MMAudio required OK)."
