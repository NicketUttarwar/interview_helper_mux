#!/usr/bin/env bash
# Shared config/secrets/secrets.env loader for bash entry points.
# Environment variables already set take precedence (matches interview_mux.config).

_secrets_env_unquote() {
  local val="$1"
  val="${val%\"}"
  val="${val#\"}"
  val="${val%\'}"
  val="${val#\'}"
  printf '%s' "$val"
}

# Resolve repository root from optional start directory (default: pwd).
secrets_env_repo_root() {
  local start="${1:-$(pwd)}"
  if [[ -n "${INTERVIEW_MUX_ROOT:-}" ]]; then
    if [[ -f "${INTERVIEW_MUX_ROOT}/config/secrets/secrets.env" ]] \
      || [[ -f "${INTERVIEW_MUX_ROOT}/config/app.defaults.json" ]]; then
      printf '%s\n' "$(cd "${INTERVIEW_MUX_ROOT}" && pwd)"
      return 0
    fi
  fi
  local root
  root="$(git -C "$start" rev-parse --show-toplevel 2>/dev/null || true)"
  if [[ -n "$root" ]] && [[ -f "${root}/config/app.defaults.json" ]]; then
    printf '%s\n' "$root"
    return 0
  fi
  local dir="$start"
  while [[ "$dir" != "/" ]]; do
    if [[ -f "${dir}/pyproject.toml" && -f "${dir}/config/app.defaults.json" ]]; then
      printf '%s\n' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

secrets_env_file() {
  local root
  root="$(secrets_env_repo_root "${1:-}")" || return 1
  printf '%s\n' "${root}/config/secrets/secrets.env"
}

# Read one key from secrets.env without exporting. Prints value or empty string.
secrets_env_get() {
  local key="$1"
  local start="${2:-$(pwd)}"
  local file
  file="$(secrets_env_file "$start")" || return 1
  [[ -f "$file" ]] || return 0
  local line k val
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$line" || "$line" != *=* ]] && continue
    k="${line%%=*}"
    k="${k%"${k##*[![:space:]]}"}"
    [[ "$k" == "$key" ]] || continue
    val="${line#*=}"
    val="${val#"${val%%[![:space:]]*}"}"
    _secrets_env_unquote "$val"
    return 0
  done < "$file"
  return 0
}

# Export all keys from secrets.env; skip keys already present in the environment.
load_secrets_env() {
  local start="${1:-$(pwd)}"
  local file
  file="$(secrets_env_file "$start")" || return 1
  [[ -f "$file" ]] || return 0
  local line k val existing
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$line" || "$line" != *=* ]] && continue
    k="${line%%=*}"
    k="${k%"${k##*[![:space:]]}"}"
    val="${line#*=}"
    val="${val#"${val%%[![:space:]]*}"}"
    val="$(_secrets_env_unquote "$val")"
    [[ -n "$val" ]] || continue
    existing="${!k-__unset__}"
    if [[ "$existing" == "__unset__" || -z "$existing" ]]; then
      export "$k=$val"
    fi
  done < "$file"
}

# Export one key from secrets.env when not already set in the environment.
load_secrets_env_key() {
  local key="$1"
  local start="${2:-$(pwd)}"
  if [[ -n "${!key:-}" ]]; then
    return 0
  fi
  local val
  val="$(secrets_env_get "$key" "$start")"
  [[ -n "$val" ]] || return 1
  export "$key=$val"
}

has_secrets_env_key() {
  local key="$1"
  local start="${2:-$(pwd)}"
  [[ -n "${!key:-}" ]] && return 0
  local val
  val="$(secrets_env_get "$key" "$start")"
  [[ -n "$val" ]]
}

require_secrets_env_key() {
  local key="$1"
  local start="${2:-$(pwd)}"
  load_secrets_env_key "$key" "$start" || true
  if [[ -z "${!key:-}" ]]; then
    local file
    file="$(secrets_env_file "$start" 2>/dev/null || echo "config/secrets/secrets.env")"
    printf '%s is not set. Export it or add it to %s\n' "$key" "$file" >&2
    return 1
  fi
}
