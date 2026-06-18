# BLOCKER-001 — first-run harness validation

- **Status:** fixed
- **Detected at:** 2026-06-18T19:22:00Z
- **run_id:** (varies per start click)
- **stage:** setup / start
- **job_status:** n/a
- **Screenshot:** logs/session_*/screenshots/

## Symptom

First automated runs hit: wrong Python for driver (system vs venv), `networkidle` goto timeout, ambiguous `Start` button, stale `run_id` from page HTML, API timeout on poll.

## Root cause

Driver bootstrap and start-tab flow needed hardening for SPA polling UI and session API as source of truth.

## Fix

- `run.sh` uses `CURSOR_EXECUTE/.venv/bin/python` for driver
- `start_run()` waits for `start-asset-*` / `start-execution-*` testids; `domcontentloaded` not `networkidle`
- `resolve_run_id_after_start()` prefers `/api/session` active run, then `/api/runs` by input path
- API poll retries on timeout; `_get` timeout 60s

## Fix comment

Harness verified: dry-run passes, server health OK, Playwright clicks flow-intent + start-execution on notebooklm WAV. Full Flow 1 to `master.wav` is a multi-hour operator run — use `./CURSOR_EXECUTE/flow1-gui-e2e/run.sh` (Ctrl+C safe; `--resume` continues).

## Resume

```bash
./CURSOR_EXECUTE/flow1-gui-e2e/run.sh --resume
```
