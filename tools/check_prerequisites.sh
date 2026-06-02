#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

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

LOCK="$ROOT/requirements.lock"
if [[ ! -f "$LOCK" ]]; then
  echo "Missing requirements.lock — run ./scripts/bootstrap_venv.sh after generating the lock"
  exit 1
fi

if [[ -d .venv ]]; then
  echo "Running pip-audit against requirements.lock..."
  python - "$LOCK" <<'PY'
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

LOCK = sys.argv[1]
FAIL_LEVEL = os.environ.get("PIP_AUDIT_FAIL_LEVEL", "HIGH").upper()
IGNORE = {
    x.strip()
    for x in os.environ.get("PIP_AUDIT_IGNORE_VULNS", "").split(",")
    if x.strip()
}
RANK = {"LOW": 0, "MEDIUM": 1, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}
THRESHOLD = RANK.get(FAIL_LEVEL, RANK["HIGH"])


def osv_severity(vuln: dict) -> str:
    for key in (vuln.get("id"), *vuln.get("aliases", [])):
        if not key:
            continue
        url = f"https://api.osv.dev/v1/vulns/{key}"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.load(resp)
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
            continue
        sev = (data.get("database_specific") or {}).get("severity")
        if sev:
            return str(sev).upper()
        for entry in data.get("severity") or []:
            score = entry.get("score", "")
            if "CVSS:3" in score or "CVSS:4" in score:
                # Conservative default when only vector is present
                return "MEDIUM"
    return "UNKNOWN"


proc = subprocess.run(
    [sys.executable, "-m", "pip_audit", "-r", LOCK, "--format", "json", "--desc", "on"],
    capture_output=True,
    text=True,
)
if proc.returncode not in (0, 1):
    print(proc.stderr or proc.stdout, file=sys.stderr)
    sys.exit(proc.returncode)

try:
    payload = json.loads(proc.stdout)
except json.JSONDecodeError as exc:
    print(f"pip-audit JSON parse error: {exc}", file=sys.stderr)
    print(proc.stdout, file=sys.stderr)
    sys.exit(1)

blocking = []
for dep in payload.get("dependencies", []):
    name = dep.get("name", "?")
    version = dep.get("version", "?")
    for vuln in dep.get("vulns", []):
        vid = vuln.get("id", "")
        if vid in IGNORE:
            continue
        severity = osv_severity(vuln)
        rank = RANK.get(severity, RANK["HIGH"] if severity == "UNKNOWN" else 0)
        if rank >= THRESHOLD:
            fixes = ", ".join(vuln.get("fix_versions") or []) or "none listed"
            blocking.append((severity, vid, name, version, fixes, vuln.get("description", "")))

if blocking:
    print(
        f"pip-audit: {len(blocking)} unaccepted finding(s) at or above {FAIL_LEVEL} "
        f"(set PIP_AUDIT_IGNORE_VULNS or document in anchored-toolchain.md):",
        file=sys.stderr,
    )
    for severity, vid, name, version, fixes, desc in blocking:
        print(f"  [{severity}] {vid} — {name}=={version} (fix: {fixes})", file=sys.stderr)
        if desc:
            print(f"    {desc}", file=sys.stderr)
    sys.exit(1)

print("pip-audit: no unaccepted HIGH/CRITICAL findings")
PY
fi

if [[ "$(uname -s)" == "Darwin" ]] && [[ -d .venv ]]; then
  if ! python -c "import mlx_lm" 2>/dev/null; then
    echo "WARN: local_llm is on by default but mlx-lm is not installed — re-run ./scripts/bootstrap_venv.sh"
  else
    if ! command -v llmfit >/dev/null 2>&1; then
      echo "WARN: llmfit not on PATH — install: brew install AlexsJones/llmfit/llmfit (or see SETUP.md § Local LLM)"
    fi
    if [[ ! -d ASSETS/local_llm/models ]] || [[ -z "$(ls -A ASSETS/local_llm/models 2>/dev/null)" ]]; then
      echo "WARN: local LLM weights not found under ASSETS/local_llm/models — run: python scripts/select_local_llm.py --download"
    fi
  fi
fi

echo "Prerequisites OK."
