---
name: sync-env
description: Check this machine's tool, pip and model versions against the reference Mac and align them. Use when setup fails, a new bug appears that the reference Mac does not have, or after pulling a new config/env-lock/.
---

# sync-env

The reference environment is committed in `config/env-lock/` (written by `python3 tools/env_sync.py snapshot` on the reference Mac).

1. Run `python3 tools/env_sync.py` from the repo root and show the user the full output.
2. If it reports `DIFF` lines, explain each in plain words, then run `python3 tools/env_sync.py --fix` (it asks before every action). Do not add `--yes` unless the user says so, and do not add `--prune` unless the user asks to remove extra packages.
3. If a venv is reported missing, run `./scripts/bootstrap_venv.sh` first, then repeat from step 1.
4. Re-run the check. Report what still differs.

Things this cannot fix, and must be reported rather than worked around: macOS version, chip, RAM, and an exact Python or ffmpeg patch version that Homebrew no longer serves. `WARN` lines are informational. A model download can be many GB, so tell the user before accepting it.

Never edit `config/env-lock/` while fixing. Only the reference Mac regenerates it.
