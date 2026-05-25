#!/usr/bin/env bash
set -euo pipefail
echo "Checking prerequisites..."
command -v ffmpeg >/dev/null || { echo "Missing ffmpeg"; exit 1; }
command -v ffprobe >/dev/null || { echo "Missing ffprobe"; exit 1; }
command -v aws >/dev/null || { echo "Missing aws CLI"; exit 1; }
PY="${PYTHON:-/opt/homebrew/bin/python3.12}"
command -v "$PY" >/dev/null || PY=python3
"$PY" --version
if [[ -d .venv ]]; then
  # shellcheck source=/dev/null
  source .venv/bin/activate
  python -c "import interview_mux; print('interview_mux', interview_mux.__version__)"
fi
echo "Prerequisites OK."
