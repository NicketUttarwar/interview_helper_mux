# BLOCKER-006 — api-poll-failed

- **Status:** fixed
- **Detected at:** 2026-06-18T23:31:43.636785+00:00
- **run_id:** exec_841_be82f1154a05_20260618T232807Z
- **stage:** audio_preclean
- **job_status:** api_unreachable
- **Screenshot:** /Users/nicketuttarwar/IDEProjects/interview_helper_mux/CURSOR_EXECUTE/flow1-gui-e2e/logs/session_20260618T232716_36481/screenshots/api-poll-failed.png

## Symptom

GET /api/runs/exec_841_be82f1154a05_20260618T232807Z or /job failed 3 times in a row: timed out

## gui_log tail

- `2026-06-18T23:28:07.233014+00:00` Execution exec_841_be82f1154a05_20260618T232807Z initialized with input ASSETS/input/notebooklm_original_interview_2024.wav
- `2026-06-18T23:28:07.240940+00:00` Output intent set: flow1
- `2026-06-18T23:30:08.555839+00:00` Quality offer shown: background noise removal (before_ingest).
- `2026-06-18T23:30:08.561980+00:00` Opened execution exec_841_be82f1154a05_20260618T232807Z

## Root cause

With job status `idle` at the audio pre-clean quality offer, the E2E driver called `GET /api/runs/{id}` on every poll. That endpoint builds a full journey snapshot whose `_blocking()` loop scanned **every** pending stage (16 stages) for reuse candidates. Each scan iterated ~582 same-hash executions and read run meta per candidate (~1 s/stage), totaling ~18–40 s per request — above the driver's 30 s timeout. `/job` stayed fast (no journey build), but the poll path still hit the heavy run fetch when idle.

## Fix

- `journey_orchestrator.py`: `_blocking()` checks reuse only for the **first** pending pipeline stage (the next runnable step), not all pending stages.
- `gui_driver.py`: skip heavy `GET /api/runs/{id}` when job is `idle` (same lightweight stub as `running` / `awaiting_write_approval`) so gate handlers can click `preclean-dismiss-before_ingest` without waiting on journey enrichment.

## Fix comment

Verified locally: `build_journey_snapshot` for exec_841 drops from ~25 s to <1 s; simulated `get_run` path ~1 s. Targeted pytest (`test_journey_orchestrator.py`, `test_driver_utils.py`) passes after `pip install -e .`. Re-run `./CURSOR_EXECUTE/flow1-gui-e2e/run.sh --resume` — driver should dismiss pre-clean and continue ingest.

## Resume
./CURSOR_EXECUTE/flow1-gui-e2e/run.sh --resume
