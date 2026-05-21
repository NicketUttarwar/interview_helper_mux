#!/usr/bin/env bash
# Optional: download a short public-domain speech sample for pytest.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="${DIR}/speech_short.wav"

if [[ -f "$OUT" ]]; then
  echo "Already exists: $OUT"
  exit 0
fi

echo "Fetching sample speech (LibriVox-style archive.org clip)..."
# Small CC0 / public domain sample; replace URL if link rots.
URL="https://archive.org/download/jfk_speech_sample/jfk_speech_sample_64kb_mp3.mp3"
TMP="$(mktemp).mp3"
curl -fsSL -o "$TMP" "$URL" || {
  echo "Download failed. Record tests/fixtures/speech_short.wav manually (see README)."
  rm -f "$TMP"
  exit 1
}
ffmpeg -y -i "$TMP" -ar 48000 -ac 1 "$OUT"
rm -f "$TMP"
echo "Wrote $OUT"
