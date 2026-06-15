# Legacy and compatibility

Operator golden path: [operator-journey.md](./operator-journey.md). This page is for CLI, old runs, and single-stage reruns.

## Run directories

| Path | Status |
|------|--------|
| `ASSETS/executions/exec_*` | **Current** — new work |
| `data/run_NNN/` | Legacy — still readable |

## Input audio

| Method | Use |
|--------|-----|
| GUI **Input audio** under `ASSETS/` | Default |
| `INPUT_AUDIO_PATH` in secrets / defaults | CLI / automation only |

## Legacy pipeline stage ids

Still runnable via `POST …/execute` with `mode: stage`:

| Legacy id | Replacement |
|-----------|-------------|
| `mux_flow1` / `mux_flow2` | `mix_flow1` / `mix_flow2` |
| `podcast_sfx_brief` / `sfx_brief` | SDP + `sfx_prompt_craft` |

Not in default `FLOW1_ORDER` / `FLOW2_ORDER`.

## LLM call records

Legacy `run_prompt` without `RunContext` does not write labeled `llm_calls/` — see [llm-call-record-framework.md](../cross-cutting/llm-call-record-framework.md).
