#!/usr/bin/env bash
# Clone or update upstream MMAudio and DeepFilterNet into separate ASSETS trees.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MMAUDIO_URL="https://github.com/hkchengrex/MMAudio.git"
DF_URL="https://github.com/rikorose/deepfilternet.git"
MMAUDIO_DIR="$ROOT/ASSETS/local_mmaudio/MMAudio"
DF_DIR="$ROOT/ASSETS/local_deepfilter/DeepFilterNet"

mkdir -p "$ROOT/ASSETS/local_mmaudio" "$ROOT/ASSETS/local_deepfilter"

clone_or_pull() {
  local url="$1"
  local dest="$2"
  if [[ -d "$dest/.git" ]]; then
    echo "Updating $(basename "$dest")…"
    git -C "$dest" pull --ff-only
  elif [[ -d "$dest" ]]; then
    echo "ERROR: $dest exists but is not a git clone. Remove it and re-run." >&2
    exit 1
  else
    echo "Cloning $url → $dest"
    git clone "$url" "$dest"
  fi
}

clone_or_pull "$MMAUDIO_URL" "$MMAUDIO_DIR"
clone_or_pull "$DF_URL" "$DF_DIR"
echo "Local audio repos ready:"
echo "  MMAudio:       $MMAUDIO_DIR"
echo "  DeepFilterNet: $DF_DIR"
