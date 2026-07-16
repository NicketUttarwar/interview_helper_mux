# Stage execution reuse

At **every pipeline stage**, the GUI can offer to copy outputs from a **recent prior execution** when that run used the **same canonical pipeline WAV** (`run_meta.source_audio_hash`, derived from the post-conversion `.wav` file — never from raw m4a/mp4 containers).

The scanner walks the **last N prior executions** (`journey_ui.stage_reuse_lookback_executions`, default **5**), ordered by `execution_number` from newest to oldest. The **first** run in that window with a hash match and complete stage outputs becomes the reuse candidate. Runs outside the lookback window are not offered even when the hash matches.

Fresh executions are the default. Reuse is **opt-in per stage** and only appears when strict eligibility checks pass.

## When an offer appears

All of the following must be true:

1. **Hash match** — the current run and a prior `exec_*` under `ASSETS/executions/` share the same `source_audio_hash`. Hash is **recomputed from disk** when building the offer list; a mismatch vs stored `run_meta.source_audio_hash` logs a warning. Runs without a stored or computable hash are not eligible, and path-only matching is not offered.
2. **Stage complete** — the prior run has `.stage_done/<stage>` **and** all requisite output files for that stage (non-empty, on disk). See `src/interview_mux/stage_execution_reuse.py` (`prior_run_has_reusable_stage`).
3. **No decision yet** — the current run has not decided (`run_meta.stage_reuse[stage_id]` unset).

If either the hash or completeness check fails, **no reuse offer** is shown for that stage.

Offers render in **Stage detail** (`StageReuseSection`) and the **operator action modal** whenever candidates exist. `journey_ui.enable_stage_reuse_offers` (default `true`) controls whether execute is **blocked** until you choose reuse or run fresh.

## Hash-match visual

New runs allocate ids like `exec_003_a1b2c3d4e5f6_20260609T143022Z` — the 12-character segment is `source_audio_hash_short`.

When a candidate qualifies, the GUI shows:

> **Same source audio hash — outputs verified complete**

The **Executions** tab and status header also surface hash chips; runs with matching hashes get a **Same audio** pill.

## Operator flow (GUI)

1. Run or resume an execution with the same input WAV as a prior run (hash computed at `POST /api/runs` from the canonical pipeline WAV).
2. On each pending stage, review **Previous execution reuse** (if candidates exist) or click **Run step N**.
3. **Reuse outputs** — copies artifacts to the working directory. **Transcript stages** (`transcribe`, `transcript_review_build`, `transcript_review`) copy directly to final paths (no write-approval staging). When operator-corrected snapshots exist (`operator/transcript_corrected.*`), they are **overlaid onto `transcript/full.json`** so the working transcript is the latest corrected text. **Only `transcribe` reuse** opens the **one-time** edit window (`transcript_reuse_pending_edit`) with the **synced transcript dock** (fuzzy similar-word replace, undo, audio sync) — not the plain STT review UI. Later transcript-stage reuses (`transcript_review_build`, `transcript_review`) copy artifacts without reopening the interstitial. Edit and **Save & continue**, or **Skip** to clear the pending flag and edit later in G0. The window does not auto-appear merely because the operator is on the Transcript review stage, and it does not reappear after you have saved or skipped once. Save refreshes `transcript/full.json` + `operator/transcript_corrected.*`, so the **next** execution's reuse picks up the corrected transcript. G0 first-try auto-complete is suppressed while the interstitial is pending.
4. **Run fresh instead** — records decline and runs the stage normally (e.g. fresh AWS transcribe).

When `enable_stage_reuse_offers` is `false`, the UI still lists candidates but execute is not blocked (CLI: `--no-reuse-offers`).

Decisions are stored in `run_meta.stage_reuse` (with `applied_at` after copy) and cleared when you **Redo from stage**. Accept is idempotent — a second accept while outputs are staged or done does not re-copy files. API reuse/approve/discard calls are serialized with the background job via `JobRunner.run_guard` and a cross-process `RunDirectoryLock` on `{run_dir}/.run.lock`. Reuse copy acquires the **source** run lock for the duration of the copy. Candidates expose `match_kind: "hash"` when eligible. Reusing SDP-consuming stages (`sound_design_palettes`, `sound_design_plan_flow*`, `sound_design_vo_finalize`) is blocked when an existing `understanding/sound_design_plan.json` came from a different `source_run_id`. A mirror log is written to `operator/stage_reuse_decisions.json`.

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

`--reuse-from` auto-accepts only when the source run shares the same `source_audio_hash` and has complete stage outputs.

## Config

- `journey_ui.enable_stage_reuse_offers` (default `true`) — block execute until reuse decision.
- `journey_ui.require_write_approval_per_stage` (default `true`) — stage outputs (including reused copies) await review in **WriteApprovalPanel** before final save.

See [config-keys.md](../cross-cutting/config-keys.md), [idempotent-runs.md](./idempotent-runs.md), [api-reference.md](./api-reference.md), [gui-surface-map.md](./gui-surface-map.md).
