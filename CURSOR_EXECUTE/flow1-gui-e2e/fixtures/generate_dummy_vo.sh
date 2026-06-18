#!/usr/bin/env bash
# Generate 3s mono 440Hz tone WAV for G1 VO pickup E2E uploads.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="${SCRIPT_DIR}/dummy_vo.wav"
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg required" >&2
  exit 1
fi
ffmpeg -y -f lavfi -i "sine=frequency=440:duration=3" -ac 1 -ar 44100 -sample_fmt s16 "${OUT}" 2>/dev/null
echo "Wrote ${OUT}"
