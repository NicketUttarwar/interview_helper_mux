# BLOCKER-005 — session-not-ready

- **Status:** fixed
- **Detected at:** 2026-06-18T22:52:47.355510+00:00
- **run_id:** unknown
- **stage:** unknown
- **job_status:** unknown
- **Screenshot:** /Users/nicketuttarwar/IDEProjects/interview_helper_mux/CURSOR_EXECUTE/flow1-gui-e2e/logs/session_20260618T225011_3651/screenshots/session-not-ready.png

## Symptom

Start tab never became ready within 120s (expected start-tab-ready[data-ready=true] or enabled start-execution-notebooklm_original_interview_2024.wav)

## gui_log tail


## Root cause

App boot awaited `refreshHome()`, which always called `/api/runs?enrich=1&enrich_limit=50`. With many prior executions on disk, that enrich pass can take minutes. `sessionReady` stayed false until boot finished, so `start-tab-ready` remained `data-ready="false"` and Start buttons stayed disabled while the Source audio panel showed a stuck "Refreshing…" state.

## Fix

- `AppContext.tsx`: boot uses a fast `refreshHome({ enrichRuns: false })` (assets + lightweight runs list), sets `sessionReady` immediately after, then enriches runs and restores any active session in the background.
- Rebuilt GUI bundle (`./scripts/build_gui.sh`).

## Fix comment

Targeted pytest (`CURSOR_EXECUTE/flow1-gui-e2e/tests/test_driver_utils.py`) passes. Re-run `./CURSOR_EXECUTE/flow1-gui-e2e/run.sh --resume` — Start tab should reach `data-ready="true"` within seconds even when enrich is slow.

## Resume
./CURSOR_EXECUTE/flow1-gui-e2e/run.sh --resume
