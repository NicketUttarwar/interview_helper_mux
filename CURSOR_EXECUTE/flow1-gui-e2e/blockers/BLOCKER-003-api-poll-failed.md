# BLOCKER-003 — api-poll-failed

- **Status:** fixed
- **Detected at:** 2026-06-18T20:53:53.416922+00:00
- **run_id:** exec_580_be82f1154a05_20260612T221635Z
- **stage:** ingest
- **job_status:** api_unreachable
- **Screenshot:** /Users/nicketuttarwar/IDEProjects/interview_helper_mux/CURSOR_EXECUTE/flow1-gui-e2e/logs/session_20260618T205154_75708/screenshots/api-poll-failed.png

## Symptom

GET /api/runs/exec_580_be82f1154a05_20260612T221635Z or /job failed 3 times in a row: timed out

## gui_log tail

- `2026-06-13T22:10:28.425376+00:00` Ingest complete — normalized audio at ingest/normalized.wav (48000 Hz mono).
- `2026-06-13T22:10:28.428896+00:00` Stage 'ingest' outputs await review before saving (2 file(s)).

## Root cause

`GET /api/runs/{id}` builds a full journey snapshot on every poll. `_blocking()` scanned stage-reuse candidates for every pending stage by calling `find_reuse_candidates()`, which (a) re-read and SHA-256'd the 150 MB source WAV on every candidate run via `source_audio_hash(recompute=True)` and (b) iterated all ~800 execution folders without hash prefilter. With the run stuck at `awaiting_write_approval` for ingest, each E2E poll exceeded the 30 s client timeout. `/api/runs/{id}/job` stayed fast because it reads only `gui_job.json`.

## Fix

- `stage_execution_reuse.py`: reuse matching uses stored `run_meta` hashes (no WAV recompute on poll); prefilter candidate runs by the 12-char hash embedded in `exec_*` folder names before file checks.
- `journey_orchestrator.py`: treat `awaiting_write_approval` as blocking immediately so journey snapshot skips reuse scans when write approval is pending.
- `gui_driver.py`: poll `/job` first; skip heavy `/api/runs/{id}` fetch while job is `running` or `awaiting_write_approval`.

## Fix comment

Verified locally: `build_journey_snapshot` for exec_580 drops from multi-minute hang to ~80 ms; targeted pytest (`test_stage_execution_reuse.py`, `test_journey_orchestrator.py`) passes after `pip install -e .`. Re-run `./CURSOR_EXECUTE/flow1-gui-e2e/run.sh --resume` — driver should click **Save & continue** on ingest write approval and continue.

## Resume
./CURSOR_EXECUTE/flow1-gui-e2e/run.sh --resume
