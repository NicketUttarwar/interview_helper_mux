#!/usr/bin/env bash
# Shared helpers for Terraform wrappers. Source after SCRIPT_DIR is set to this script's parent (scripts/).
#
# Logging: tf_log / tf_warn to stderr. TF_QUIET=1 silences tf_log. TF_TRACE=1 enables set -x.
#
# Session state (rolling backup of local backend state):
#   Live:   terraform/state/terraform.tfstate
#   Latest: terraform/state/session/latest.tfstate (only one file kept; updated after each successful terraform run)
#   USE_LATEST_SESSION=1 or --use-session on wrappers: restore live state from latest before terraform runs.
# shellcheck shell=bash

: "${SCRIPT_DIR:?terraform-common: SCRIPT_DIR must be set}"

REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform"
# Variable values: prefer config/terraform.tfvars (see README). Override with TF_VAR_FILE.
# Legacy path terraform/terraform.tfvars is still used if the config file does not exist.
TF_STATE_LIVE="${TF_DIR}/state/terraform.tfstate"
TF_STATE_SESSION_DIR="${TF_DIR}/state/session"
TF_STATE_SESSION_LATEST="${TF_STATE_SESSION_DIR}/latest.tfstate"

# Script name for log lines (caller that sourced this file)
if [[ -z "${TF_SCRIPT_NAME:-}" ]]; then
  if [[ -n "${BASH_SOURCE[1]:-}" ]]; then
    TF_SCRIPT_NAME="$(basename "${BASH_SOURCE[1]}")"
  else
    TF_SCRIPT_NAME="terraform"
  fi
fi

# Set TF_QUIET=1 to hide informational [script] lines. TF_TRACE=1 enables set -x.
tf_log() {
  [[ "${TF_QUIET:-}" == "1" ]] && return 0
  echo "[$TF_SCRIPT_NAME] $*" >&2
}

tf_warn() {
  echo "[$TF_SCRIPT_NAME] WARNING: $*" >&2
}

tf_log_cmd() {
  tf_log "Running: $*"
}

if [[ "${TF_TRACE:-}" == "1" ]]; then
  set -x
fi

# --- Session state: filter --use-session from terraform args ----------------

# Populates _TF_FILTERED_ARGS and sets _TF_USE_SESSION_FLAG=1 if restore requested.
terraform_common_filter_session_args() {
  _TF_FILTERED_ARGS=()
  _TF_USE_SESSION_FLAG=0
  if [[ "${USE_LATEST_SESSION:-}" == "1" ]]; then
    _TF_USE_SESSION_FLAG=1
  fi
  local arg
  for arg in "$@"; do
    case "$arg" in
      --use-session)
        _TF_USE_SESSION_FLAG=1
        tf_log "Option --use-session: will restore live state from latest session backup (if present)"
        ;;
      *)
        _TF_FILTERED_ARGS+=("$arg")
        ;;
    esac
  done
}

terraform_common_wants_session_restore() {
  [[ "${_TF_USE_SESSION_FLAG:-}" == "1" ]]
}

# Replace dest with a full copy of src using a temp file in the same directory as dest, then mv.
# Same-filesystem rename makes the switch atomic: readers never see a partially written state file.
terraform_common_atomic_replace_file() {
  local src=$1
  local dest=$2
  local dest_dir tmp
  dest_dir="$(dirname "$dest")"
  mkdir -p "$dest_dir" || return 1
  tmp="$(mktemp "${dest_dir}/.tfstate-atomic.XXXXXX")" || return 1
  if ! cp -f "$src" "$tmp"; then
    rm -f "$tmp"
    return 1
  fi
  if ! mv -f "$tmp" "$dest"; then
    rm -f "$tmp"
    return 1
  fi
  return 0
}

terraform_common_maybe_restore_session() {
  terraform_common_wants_session_restore || return 0
  [[ "${_TF_SESSION_RESTORED:-}" == "1" ]] && return 0
  if [[ ! -f "$TF_STATE_SESSION_LATEST" ]]; then
    tf_warn "Session restore requested but no backup at $TF_STATE_SESSION_LATEST — using current live state"
    _TF_SESSION_RESTORED=1
    return 0
  fi
  mkdir -p "$TF_STATE_SESSION_DIR"
  tf_log "Restoring live state from session backup: $TF_STATE_SESSION_LATEST → $TF_STATE_LIVE"
  if ! terraform_common_atomic_replace_file "$TF_STATE_SESSION_LATEST" "$TF_STATE_LIVE"; then
    tf_warn "Failed to restore live state atomically (cp/mv)"
    return 1
  fi
  _TF_SESSION_RESTORED=1
}

# After a successful terraform run, keep a single rolling copy (remove any other files in session dir).
terraform_common_maybe_save_session_backup() {
  local ec=$1
  [[ "$ec" -eq 0 ]] || return 0
  if [[ ! -f "$TF_STATE_LIVE" ]]; then
    tf_log "No live state file at $TF_STATE_LIVE — skipping session backup"
    return 0
  fi
  mkdir -p "$TF_STATE_SESSION_DIR"
  if ! terraform_common_atomic_replace_file "$TF_STATE_LIVE" "$TF_STATE_SESSION_LATEST"; then
    tf_warn "Failed to save session backup atomically (cp/mv)"
    return 0
  fi
  find "$TF_STATE_SESSION_DIR" -maxdepth 1 -type f \
    ! -name '.gitkeep' ! -name 'latest.tfstate' -delete 2>/dev/null || true
  tf_log "Saved rolling session backup (latest only): $TF_STATE_SESSION_LATEST"
}

# --- Preconditions ---------------------------------------------------------

terraform_common_require() {
  [[ "${_TF_COMMON_REQUIRE_OK:-}" == "1" ]] && return 0
  tf_log "Checking prerequisites (terraform binary, ${TF_DIR})..."
  if ! command -v terraform >/dev/null 2>&1; then
    tf_warn "terraform is not installed or not in PATH"
    exit 127
  fi
  if [[ ! -d "$TF_DIR" ]]; then
    tf_warn "Terraform directory not found: $TF_DIR"
    exit 1
  fi
  if [[ ! -f "$TF_DIR/versions.tf" ]]; then
    tf_warn "Terraform directory appears invalid (missing versions.tf): $TF_DIR"
    exit 1
  fi
  tf_log "Prerequisites OK (terraform: $(command -v terraform))"
  _TF_COMMON_REQUIRE_OK=1
}

# On Apple Silicon, tfenv can leave an x86_64 Terraform if the version was installed under Rosetta.
# That forces darwin_amd64 providers and often causes plugin startup timeouts.
terraform_common_warn_if_terraform_cli_not_native_arm64() {
  [[ "$(uname -m)" == "arm64" ]] || return 0
  local tfenv_root="${TFENV_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/tfenv}"
  local ver tf_bin ft
  [[ -f "$tfenv_root/version" ]] || return 0
  ver="$(cat "$tfenv_root/version" 2>/dev/null || true)"
  [[ -n "$ver" ]] || return 0
  tf_bin="$tfenv_root/versions/$ver/terraform"
  [[ -f "$tf_bin" ]] || return 0
  ft="$(file -b "$tf_bin" 2>/dev/null || true)"
  if [[ "$ft" == *x86_64* ]]; then
    tf_warn "Terraform at $tf_bin is x86_64 on an arm64 Mac — reinstall for arm64: rm -rf \"$tfenv_root/versions/$ver\" && tfenv install $ver"
  fi
}

# Warn when the host is Apple Silicon but only the darwin_amd64 AWS provider is installed (Rosetta).
# That mismatch often causes "timeout while waiting for plugin to start" during validate/plan.
terraform_common_warn_if_aws_provider_arch_mismatch() {
  [[ "$(uname -m)" == "arm64" ]] || return 0
  local base="${TF_DIR}/.terraform/providers/registry.terraform.io/hashicorp/aws"
  [[ -d "$base" ]] || return 0
  local verdir
  for verdir in "$base"/*; do
    [[ -d "$verdir" ]] || continue
    if [[ -d "$verdir/darwin_amd64" && ! -d "$verdir/darwin_arm64" ]]; then
      tf_warn "This Mac is arm64 but the AWS provider under .terraform is darwin_amd64 only (Rosetta). Plugin startup can time out. Fix: rm -rf \"${TF_DIR}/.terraform/providers\" && ./scripts/tf-init.sh (use a native arm64 terraform binary so init installs darwin_arm64)."
      return 0
    fi
  done
}

terraform_common_source_aws_env() {
  [[ "${_TF_COMMON_AWS_ENV_SOURCED:-}" == "1" ]] && return 0
  local env="${REPO_ROOT}/config/secrets/secrets.env"
  if [[ -f "$env" ]]; then
    tf_log "Loading AWS environment from: $env"
    set -a
    # shellcheck source=/dev/null
    source "$env"
    set +a
    if [[ -n "${AWS_DEFAULT_REGION:-}" ]]; then
      tf_log "AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}"
    fi
  else
    tf_log "No config/secrets/secrets.env — using existing shell environment / instance role / SSO (if any)"
  fi
  _TF_COMMON_AWS_ENV_SOURCED=1
}

# Prints the path to the tfvars file wrappers should load, or returns non-zero if none.
# Precedence: TF_VAR_FILE (if file exists), then config/terraform.tfvars, then terraform/terraform.tfvars.
terraform_common_effective_var_file_path() {
  if [[ -n "${TF_VAR_FILE:-}" ]]; then
    if [[ -f "${TF_VAR_FILE}" ]]; then
      printf '%s' "${TF_VAR_FILE}"
      return 0
    fi
    tf_warn "TF_VAR_FILE is set but file not found: ${TF_VAR_FILE}"
    return 1
  fi
  if [[ -f "${REPO_ROOT}/config/terraform.tfvars" ]]; then
    printf '%s' "${REPO_ROOT}/config/terraform.tfvars"
    return 0
  fi
  if [[ -f "${TF_DIR}/terraform.tfvars" ]]; then
    printf '%s' "${TF_DIR}/terraform.tfvars"
    return 0
  fi
  return 1
}

terraform_common_subcommand_needs_var_file() {
  case "${1:-}" in
    plan | apply | destroy | refresh | console | import | graph | test)
      return 0
      ;;
    *)
      # validate does not accept -var-file in Terraform 1.14+; tf-fmt-validate.sh handles it.
      return 1
      ;;
  esac
}

terraform_common_user_has_var_file() {
  local arg prev=""
  for arg in "$@"; do
    if [[ "$arg" == -var-file=* ]]; then
      return 0
    fi
    if [[ "$prev" == -var-file ]]; then
      return 0
    fi
    prev="$arg"
  done
  return 1
}

terraform_common_maybe_warn_legacy_tfvars() {
  local vf=$1
  [[ "${_TF_LEGACY_TFVARS_WARNED:-}" == "1" ]] && return 0
  if [[ "$vf" == "${TF_DIR}/terraform.tfvars" ]]; then
    tf_warn "Using legacy terraform/terraform.tfvars — move to config/terraform.tfvars (see README)"
    _TF_LEGACY_TFVARS_WARNED=1
  fi
}

# Sets _TF_FINAL_ARGS from _TF_FILTERED_ARGS (appends -var-file after the subcommand when appropriate).
# Terraform requires -var-file after the subcommand (e.g. validate -var-file=...), not before it.
terraform_common_finalize_args() {
  _TF_FINAL_ARGS=()
  local subcmd vf
  subcmd="${_TF_FILTERED_ARGS[0]:-}"
  vf=$(terraform_common_effective_var_file_path) || vf=""
  _TF_FINAL_ARGS+=("${_TF_FILTERED_ARGS[@]}")
  if [[ -n "$vf" ]] && terraform_common_subcommand_needs_var_file "$subcmd" &&
    ! terraform_common_user_has_var_file "${_TF_FILTERED_ARGS[@]}"; then
    terraform_common_maybe_warn_legacy_tfvars "$vf"
    tf_log "Using -var-file=$vf"
    _TF_FINAL_ARGS+=(-var-file="$vf")
  fi
}

# Run terraform with optional AWS env (credentials for provider/remote backends).
terraform_common_exec() {
  terraform_common_filter_session_args "$@"
  terraform_common_require
  terraform_common_source_aws_env
  terraform_common_maybe_restore_session || return
  terraform_common_finalize_args
  if [[ "${_TF_EXEC_CTX_LOGGED:-}" != "1" ]]; then
    tf_log "Repository root: $REPO_ROOT"
    tf_log "Working directory for -chdir: $TF_DIR"
    _TF_EXEC_CTX_LOGGED=1
  fi
  tf_log_cmd "terraform -chdir=\"$TF_DIR\" ${_TF_FINAL_ARGS[*]}"
  (cd "$REPO_ROOT" && terraform -chdir="$TF_DIR" "${_TF_FINAL_ARGS[@]}")
  local ec=$?
  if [[ $ec -eq 0 ]]; then
    tf_log "terraform finished successfully (exit 0)."
  else
    tf_warn "terraform exited with status $ec"
  fi
  terraform_common_maybe_save_session_backup "$ec"
  return "$ec"
}

# Run terraform without sourcing config/secrets/secrets.env (fmt, validate, local state output).
terraform_common_exec_local() {
  terraform_common_filter_session_args "$@"
  terraform_common_require
  terraform_common_maybe_restore_session || return
  terraform_common_finalize_args
  if [[ "${_TF_LOCAL_CTX_LOGGED:-}" != "1" ]]; then
    tf_log "Skipping config/secrets/secrets.env (not required for this command)"
    tf_log "Repository root: $REPO_ROOT"
    tf_log "Working directory for -chdir: $TF_DIR"
    _TF_LOCAL_CTX_LOGGED=1
  fi
  tf_log_cmd "terraform -chdir=\"$TF_DIR\" ${_TF_FINAL_ARGS[*]}"
  (cd "$REPO_ROOT" && terraform -chdir="$TF_DIR" "${_TF_FINAL_ARGS[@]}")
  local ec=$?
  if [[ $ec -eq 0 ]]; then
    tf_log "terraform finished successfully (exit 0)."
  else
    tf_warn "terraform exited with status $ec"
  fi
  terraform_common_maybe_save_session_backup "$ec"
  return "$ec"
}
