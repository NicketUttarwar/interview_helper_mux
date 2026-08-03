#!/usr/bin/env bash
# Self-test for scripts/lib/secrets_env.sh
set -euo pipefail

LIB_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "${LIB_DIR}/secrets_env.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "${TMP}/config/secrets"
cat > "${TMP}/config/app.defaults.json" <<'JSON'
{}
JSON
touch "${TMP}/pyproject.toml"
cat > "${TMP}/config/secrets/secrets.env" <<'ENV'
# comment
CURSOR_API_KEY=cursor_test_key_123
OPENAI_API_KEY=sk-test
EMPTY_KEY=
ENV

unset CURSOR_API_KEY OPENAI_API_KEY EMPTY_KEY EXPORTED_KEY

val="$(secrets_env_get CURSOR_API_KEY "$TMP")"
[[ "$val" == "cursor_test_key_123" ]] || { echo "FAIL secrets_env_get"; exit 1; }

load_secrets_env "$TMP"
[[ "${CURSOR_API_KEY:-}" == "cursor_test_key_123" ]] || { echo "FAIL load_secrets_env CURSOR_API_KEY"; exit 1; }
[[ "${OPENAI_API_KEY:-}" == "sk-test" ]] || { echo "FAIL load_secrets_env OPENAI_API_KEY"; exit 1; }
[[ -z "${EMPTY_KEY:-}" ]] || { echo "FAIL empty key exported"; exit 1; }

export EXPORTED_KEY=from_env
load_secrets_env "$TMP"
[[ "${EXPORTED_KEY:-}" == "from_env" ]] || { echo "FAIL env override"; exit 1; }

unset CURSOR_API_KEY
load_secrets_env_key CURSOR_API_KEY "$TMP"
[[ "${CURSOR_API_KEY:-}" == "cursor_test_key_123" ]] || { echo "FAIL load_secrets_env_key"; exit 1; }

unset CURSOR_API_KEY
has_secrets_env_key CURSOR_API_KEY "$TMP" || { echo "FAIL has_secrets_env_key"; exit 1; }

unset CURSOR_API_KEY
require_secrets_env_key CURSOR_API_KEY "$TMP"
[[ "${CURSOR_API_KEY:-}" == "cursor_test_key_123" ]] || { echo "FAIL require_secrets_env_key"; exit 1; }

echo "PASS scripts/lib/secrets_env.sh"
