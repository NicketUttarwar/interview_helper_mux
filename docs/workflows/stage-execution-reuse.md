# Stage execution reuse

At **every pipeline stage**, the GUI can offer to copy outputs from an earlier execution that used the **same canonical pipeline WAV** (`run_meta.source_audio_hash`, derived from the post-conversion `.wav` file — never from raw m4a/mp4 containers).

## When an offer appears

- Another `exec_*` folder under `ASSETS/executions/` shares the same `source_audio_hash` (fallback: same `input_audio_path` on legacy runs without a stored hash).
- That run has `.stage_done/<stage>` and all requisite output files for the stage (see `src/interview_mux/stage_execution_reuse.py`).
- The current run has not decided yet (`run_meta.stage_reuse[stage_id]` unset).

Offers render in **Stage detail** (`StageReuseSection`) and the **operator action modal** whenever candidates exist. `journey_ui.enable_stage_reuse_offers` (default `true`) controls whether execute is **blocked** until you choose reuse or run fresh.

## Hash-match visual

New runs allocate ids like `exec_003_a1b2c3d4e5f6_20260609T143022Z` — the 12-character segment is `source_audio_hash_short`.

When a candidate's hash matches the current run, the GUI shows:

> **Same source audio as this run**

The **Executions** tab and status header also surface hash chips; runs with matching hashes get a **Same audio** pill.

## Operator flow (GUI)

1. Run or resume an execution with the same input WAV as a prior run (hash computed at `POST /api/runs` from the canonical pipeline WAV).
2. On each pending stage, review **Previous execution reuse** (if candidates exist) or click **Run step N**.
3. **Reuse outputs** — copies artifacts (through write staging when approval is enabled), then opens write review if configured.
4. **Run fresh instead** — records decline and runs the stage normally.

When `enable_stage_reuse_offers` is `false`, the UI still lists candidates but execute is not blocked (CLI: `--no-reuse-offers`).

Decisions are stored in `run_meta.stage_reuse` (with `applied_at` after copy) and cleared when you **Redo from stage**. Accept is idempotent — a second accept while outputs are staged or done does not re-copy files. API reuse/approve/discard calls are serialized with the background job via `JobRunner.run_guard`. A mirror log is written to `operator/stage_reuse_decisions.json`.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/runs/{run_id}/stages/{stage_id}/reuse-offers` | `eligible`, `blocking`, `candidates[]`, `pending_decision`, `current_source_audio_hash_short` |
| `POST` | `/api/runs/{run_id}/stages/{stage_id}/reuse` | `{action: "accept", source_run_id}` or `{action: "decline"}` |

Each candidate includes `same_source_audio`, `source_audio_hash`, `source_audio_hash_short`, `hash_in_run_id`, `paths[]`, `execution_number`, and `updated_at`.

Background jobs set `gui_job.needs_stage_reuse` and `gui_job.reuse_candidates` when the pipeline pauses for a decision.

## CLI

```bash
python -m interview_mux analysis --run-id exec_002_a1b2c3d4e5f6_… --reuse-from exec_001_a1b2c3d4e5f6_…
python -m interview_mux flow --flow flow1 --run-id exec_002_… --no-reuse-offers
```

## Config

- `journey_ui.enable_stage_reuse_offers` (default `true`) — block execute until reuse decision.
- `journey_ui.require_write_approval_per_stage` (default `true`) — stage outputs (including reused copies) await review in **WriteApprovalPanel** before final save.

See [config-keys.md](../cross-cutting/config-keys.md), [idempotent-runs.md](./idempotent-runs.md), [api-reference.md](./api-reference.md), [gui-surface-map.md](./gui-surface-map.md).
