#!/usr/bin/env bash
# Activate core .venv or exit with install instructions.
set -euo pipefail

require_core_venv() {
  local root="${1:?root required}"
  local venv="$root/.venv"

  if [[ ! -x "$venv/bin/python" ]]; then
    echo "" >&2
    echo "ERROR: No .venv — run setup first:" >&2
    echo "  ./scripts/bootstrap_venv.sh" >&2
    echo "" >&2
    return 1
  fi

  # shellcheck source=/dev/null
  source "$venv/bin/activate"

  if ! python -c "import interview_mux" 2>/dev/null; then
    echo "ERROR: broken .venv — re-run: ./scripts/bootstrap_venv.sh" >&2
    return 1
  fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  require_core_venv "$ROOT"
fi
