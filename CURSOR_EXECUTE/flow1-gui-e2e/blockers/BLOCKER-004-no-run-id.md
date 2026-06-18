# BLOCKER-004 — no-run-id

- **Status:** fixed
- **Detected at:** 2026-06-18T22:31:41.614743+00:00
- **run_id:** unknown
- **stage:** unknown
- **job_status:** unknown
- **Screenshot:** /Users/nicketuttarwar/IDEProjects/interview_helper_mux/CURSOR_EXECUTE/flow1-gui-e2e/logs/session_20260618T222846_81889/screenshots/no-run-id.png

## Symptom

Could not capture run_id after Start

## gui_log tail


## Root cause

The per-asset **Start** button was not disabled while `sessionReady` was false. Playwright clicked it ~4s after page load; `startRun()` returned early with a toast and never POSTed `/api/runs`. The driver treated `is_enabled()` as boot-complete, but the button had no `disabled` attribute. A stale server on port 8765 also caused the E2E harness health check to pass while `MUX_FRESH_SESSION=1` never bound.

## Fix

- `StartTab.tsx`: disable Start until `sessionReady` / `openRunLoading`; expose `data-testid="start-tab-ready"` with `data-ready`.
- `gate_handlers.py` / `gui_driver.py`: wait for `start-tab-ready` before clicking Start.
- `run.sh`: free port 8765 before launch; fail fast if the spawned server exits or logs bind errors.

## Fix comment

Rebuilt GUI (`./scripts/build_gui.sh`). Targeted pytest for driver utils passes. Re-run `./CURSOR_EXECUTE/flow1-gui-e2e/run.sh --resume` — driver should wait for boot, POST create_run, and capture `run_id`.

## Resume
./CURSOR_EXECUTE/flow1-gui-e2e/run.sh --resume
