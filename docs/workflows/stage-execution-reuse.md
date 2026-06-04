# Stage execution reuse

Before each **automated pipeline stage** runs, the app can offer to copy outputs from an earlier execution that used the **same source audio** (`run_meta.input_audio_path`).

## When an offer appears

- Another `exec_*` folder under `ASSETS/executions/` shares the same `input_audio_path`.
- That run has `.stage_done/<stage>` and all requisite output files for the stage (see `src/interview_mux/stage_execution_reuse.py`).
- The current run has not decided yet (`run_meta.stage_reuse[stage_id]` unset).
- `journey_ui.enable_stage_reuse_offers` is `true` (default).

**Not offered:** operator gates (`transcript_review`, G1, G2, profile) — only stages in `pipeline.py` orders plus `vo_ingest`.

## Operator flow (GUI)

1. Run or resume an execution with the same input WAV as a prior run.
2. When the next stage would run, the checkpoint modal shows **Reuse previous execution?**
3. **Reuse from this run** — copies artifacts, marks the stage done, then the GUI continues to the next step automatically.
4. **Run fresh** — records decline and runs the stage normally.

When `enable_stage_reuse_offers` is `false` in config, the GUI skips offers (same as CLI `--no-reuse-offers`).

Decisions are stored in `run_meta.stage_reuse` and cleared when you **Redo from stage** (invalidate downstream).

## API

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/runs/{run_id}/stages/{stage_id}/reuse-offers` | List eligible prior runs |
| `POST` | `/api/runs/{run_id}/stages/{stage_id}/reuse` | `{action: "accept", source_run_id}` or `{action: "decline"}` |

Background jobs set `gui_job.needs_stage_reuse` when the pipeline pauses for a decision.

## CLI

```bash
python -m interview_mux analysis --run-id exec_002_… --reuse-from exec_001_…
python -m interview_mux flow --flow flow1 --run-id exec_002_… --no-reuse-offers
```

- `--reuse-from <exec_id>` — auto-accept reuse from that run when eligible (no prompts).
- `--no-reuse-offers` — never pause for offers (default when stdin is not a TTY).

## Config

`config/app.defaults.json` → `journey_ui.enable_stage_reuse_offers` (default `true`).

See [config-keys.md](../cross-cutting/config-keys.md), [idempotent-runs.md](./idempotent-runs.md), [api-reference.md](./api-reference.md).
