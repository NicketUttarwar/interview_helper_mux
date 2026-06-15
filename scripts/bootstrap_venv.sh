#!/usr/bin/env bash
# =============================================================================
# SINGLE SETUP ENTRY — interview_helper_mux
#
# Creates/refreshes ALL Python environments for this repo:
#
#   1. Core .venv          — interview_mux package + FastAPI GUI (requirements.lock)
#   2. ASSETS/local_llm/venv       — MLX volley framing (requirements-local-mlx.txt)
#   3. ASSETS/local_deepfilter/venv — DeepFilterNet preclean (requirements-local-deepfilter.txt)
#   4. ASSETS/local_mmaudio/venv    — MMAudio SFX generation (requirements-local-mmaudio.txt)
#
# Also:
#   - git clone/pull upstream repos into ASSETS/local_* (see clone_local_audio_repos.sh)
#   - verify each local runtime (--verify gate; non-zero exit on failure)
#   - write ASSETS/local_*/install.json manifests
#   - optional faster-whisper weights for disfluency_extract
#
# If you delete any venv or clone tree, re-run THIS script — do not use separate
# bootstrap scripts. Internal helper: scripts/lib/bootstrap_local_runtimes.sh
#
# After bootstrap:
#   source .venv/bin/activate
#   ./tools/check_prerequisites.sh
#   CHECK_LOCAL_RUNTIMES=1 ./tools/check_prerequisites.sh   # strict local stack check
#
# Docs: SETUP.md · docs/cross-cutting/local-audio-stack.md
# =============================================================================
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-/opt/homebrew/bin/python3.12}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3.12 || command -v python3)"
fi
echo "Using Python: $PY"
echo "=== Core application venv (.venv) ==="
"$PY" -m venv "$ROOT/.venv"
# shellcheck source=/dev/null
source "$ROOT/.venv/bin/activate"
pip install -U pip setuptools wheel
if [[ -f "$ROOT/requirements.lock" ]]; then
  echo "Installing from requirements.lock (anchor lock)…"
  pip install -r "$ROOT/requirements.lock"
else
  echo "requirements.lock missing — falling back to requirements.txt"
  pip install -r "$ROOT/requirements.txt"
fi
pip install -e "$ROOT"

echo "=== Local audio repos + isolated ASSETS venvs ==="
bash "$ROOT/scripts/lib/bootstrap_local_runtimes.sh"

echo "Local STT (optional): prefetch faster-whisper weights for disfluency_extract…"
python "$ROOT/scripts/download_local_stt.py" --model base \
  || echo "WARN: local STT download skipped — disfluency_extract will use transcript lexicon only."

echo "Done. Run: ./scripts/run.sh   (or: source .venv/bin/activate)"
