# Analysis orchestration loop

Shared analysis (`tools/run_analysis.py`) uses an orchestrator on top of the linear stage list.

## Flow

1. **Init** — create `analysis_state.json`, `investigation_queue.json`, `context_index.json` before first LLM stage.
2. **Run stage** — up to `analysis.max_iterations_per_stage` (default 3) inner retries until `status: complete` and no blocking `needs`.
3. **Merge memory** — apply `memory_updates` and enqueue `follow_up_investigations`.
4. **Drain queue** — after each LLM stage, run up to `max_queue_drains_per_stage` suggested reruns (e.g. re-classify after a theme investigation).
5. **Finalize** — update `completion.analysis_ready` and write `analysis_complete.json`.

## Context volley

Each LLM call uses selective user/assistant turns (see [context-padding.md](../cross-cutting/context-padding.md)), not a full memory JSON blob.

## Response envelope

Every LLM stage returns the [analysis envelope](../cross-cutting/json-schemas/analysis_envelope.schema.json). Stage-specific JSON lives under `artifacts`.

| status | Meaning |
|--------|---------|
| `complete` | Proceed |
| `partial` | Artifacts usable; may retry or queue investigation |
| `needs_input` | Rerun or operator action in `needs` |
| `blocked` | Stop inner loop; surface blocking `needs` |

## needs types

| type | Action |
|------|--------|
| `rerun_stage` | Orchestrator may re-invoke named stage |
| `operator` | Log + GUI; operator edits profile or artifacts |
| `transcript_excerpt` | Future: fetch time range into `stage_input` |

## Re-run from stage

Unchanged from [idempotent-runs.md](./idempotent-runs.md):

```bash
python tools/run_analysis.py --run-id exec_001_... --from-stage content_context
```

Invalidates that stage and downstream markers. Memory files persist unless you delete them manually.

## Config

```json
"analysis": {
  "max_iterations_per_stage": 3,
  "max_queue_drains_per_stage": 5,
  "max_user_json_chars": 48000
}
```
