#!/usr/bin/env bash
# One-time setup (or after deleting .venv / local audio venvs):
#   ./scripts/bootstrap_venv.sh
# Then every launch:
#   ./scripts/run.sh
#
# Optional:
#   BOOTSTRAP_SKIP_GUI=1      Skip npm build (run.sh will fail until you build once)
#   BOOTSTRAP_SKIP_VERIFY=1   Skip MMAudio/DeepFilterNet verify
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== 1/5 Core .venv ==="
bash "$ROOT/scripts/lib/install_core_venv.sh"

echo "=== 2/5 GUI bundle ==="
if [[ "${BOOTSTRAP_SKIP_GUI:-0}" != "1" ]]; then
  bash "$ROOT/scripts/lib/install_frontend.sh"
else
  echo "Skipped (BOOTSTRAP_SKIP_GUI=1)"
fi

echo "=== 3/5 Local audio (DeepFilterNet + MMAudio + MusicGen) ==="
bash "$ROOT/scripts/lib/bootstrap_local_runtimes.sh"
bash "$ROOT/scripts/bootstrap_musicgen.sh" || echo "WARN: MusicGen bootstrap failed — theme stubs will be used until fixed."

echo "=== 4/5 Local speech (MLX STT + diarization + S2S) ==="
bash "$ROOT/scripts/lib/bootstrap_local_speech.sh"

# Chatterbox gap VO clone (fail-open to mlx-audio when missing)
bash "$ROOT/scripts/lib/bootstrap_local_chatterbox.sh" || true

echo "=== 5/5 Local LLM (MLX volley framer, Apple Silicon) ==="
bash "$ROOT/scripts/lib/bootstrap_local_llm.sh"

if [[ "${BOOTSTRAP_SKIP_VERIFY:-0}" != "1" ]]; then
  bash "$ROOT/scripts/verify_local_models.sh" \
    || echo "WARN: verify failed — fix before STT/SFX stages."
fi

echo ""
echo "Setup complete. Start the app:"
echo "  ./scripts/run.sh"
