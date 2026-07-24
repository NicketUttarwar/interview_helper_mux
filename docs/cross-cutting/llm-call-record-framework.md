# LLM call record framework

**Status: shipped (runtime)** — every OpenAI Chat Completions call made through `run_prompt_envelope` is stored with a **stable label**, full request/response, and **LLM volley** (message-packet) fields for copy-paste and reconstruction. See [volley-glossary.md](./volley-glossary.md) — this is not speaker volley (podcast conversation).

**Related:** [artifact-layout.md](./artifact-layout.md) · [context-padding.md](./context-padding.md) · [llm-orchestration.md](./llm-orchestration.md) · [local-llm-tier.md](./local-llm-tier.md) (future `provider: local_mlx`)

---

## Why

Operators reviewing past executions need to:

1. **Find** every API call (primary, arbiter, shard, collate, specialist) by label.
2. **Copy-paste** prompts and responses from files without re-running.
3. **Reconstruct** user/assistant volleys for edits, reruns, or external tools.
4. **Link** calls to stage attempt envelopes in `understanding/stage_runs/`.

---

## Storage layout

```
understanding/llm_calls/
  index.jsonl                          # one line per call (grep-friendly)
  <stage_key>/
    attempt_001/
      01_primary.json
      01_primary.md                    # optional markdown sidecar (copy-paste)
      02_arbiter.json
      02_arbiter.md
      03_shard.json
      04_collate.json
    attempt_002/
      ...
```

| Path | Purpose |
|------|---------|
| `index.jsonl` | Fast listing: `call_id`, `label`, `stage_key`, `task_kind`, `importance`, `path` |
| `*.json` | Canonical record ([llm_call_record.schema.json](./json-schemas/llm_call_record.schema.json)) |
| `*.md` | Human-readable transcript (when `analysis.llm_call_records.write_markdown_sidecar` is true) |

**GUI:** Pipeline workspace → sub-tab **LLM calls** — browse, expand/collapse, edit LLM volley turns, save back to disk.

**CLI export:** `tools/export_llm_calls.py` for markdown/jsonl bundles.

---

## Label system

### `label` (human)

```text
<phase>:<stage_key>:a<attempt>:<sequence>:<task_kind>
```

| Part | Values |
|------|--------|
| `phase` | `analysis`, `flow1`, `flow2`, `flow3`, `system` |
| `stage_key` | Pipeline stage id (e.g. `missing_framing`) |
| `attempt` | Inner-loop attempt `a001`, `a002`, … |
| `sequence` | Order of API calls within that attempt `01`, `02`, … |
| `task_kind` | `primary`, `arbiter`, `shard`, `collate`, `specialist`, … |

**Examples:**

- `analysis:speaker_roles:a001:01:primary`
- `analysis:missing_framing:a002:02:arbiter`
- `analysis:missing_framing:a002:03:shard`
- `flow1:full_master_ranking:a001:01:primary`

### `call_id` (machine, globally unique per run)

```text
<run_id>/<stage_key>/a<attempt>/<sequence>_<task_kind>
```

Example: `exec_001_a1b2c3d4e5f6_20260601T120000Z/missing_framing/a002/02_arbiter`

### `importance`

| Value | `task_kind` |
|-------|-------------|
| **high** | `primary`, `collate`, `arbiter` |
| **medium** | `shard`, `specialist` |
| **low** | reserved (e.g. future local digest) |

---

## Record document (JSON)

Each file contains:

| Section | Use |
|---------|-----|
| `request.messages` | Exact Chat Completions payload (system + user/assistant) |
| `response.raw_content` | Model text before parsing |
| `response.parsed_envelope` | Normalized analysis envelope when applicable |
| `volley.system_prompt` | System text split out for LLM-volley-only rebuild |
| `volley.turns` | `user` / `assistant` only — inject into `build_message_volley` |
| `links.attempt_artifact` | Related `understanding/stage_runs/.../attempt_*.json` |
| `links.relative_path` | Path from run root |
| `links.volley_entry_ids` | (optional) Related `context_index.json` `volley_entries[].entry_id` when written on same accept |

When a primary call is accepted, matching `volley_entries` may reference this record via `source.llm_call_path` and `source.call_id`. GUI: Pipeline → **Volley** → **Open LLM call** deep-links to **Debug** tab.

## LLM volley reconstruction

### From one record

```python
from pathlib import Path
from interview_mux.llm_call_record import load_call_record, messages_to_volley_only, messages_to_openai_format

rec = load_call_record(Path("ASSETS/executions/exec_001.../understanding/llm_calls/speaker_roles/attempt_001/01_primary.json"))
volley_only = messages_to_volley_only(rec)       # user/assistant for context_volley
full_messages = messages_to_openai_format(rec) # includes system
```

### From multiple records (same stage attempt)

```python
from interview_mux.llm_call_record import list_calls_for_run, reconstruct_volley_from_calls, load_call_record

run_dir = Path("ASSETS/executions/exec_001...")
rows = [r for r in list_calls_for_run(run_dir) if r["stage_key"] == "missing_framing" and r["attempt"] == 2]
records = [load_call_record(run_dir / r["path"]) for r in rows]
merged = reconstruct_volley_from_calls(records)
```

### Copy-paste

Open the `.md` sidecar next to any `.json` record, or run:

```bash
python tools/export_llm_calls.py --run-id exec_001_... --stage missing_framing --format markdown -o /tmp/calls.md
```

---

## Config

`config/app.defaults.json` → `analysis.llm_call_records`:

| Key | Default | Effect |
|-----|---------|--------|
| `enabled` | `true` | Write records from `run_prompt_envelope` when `ctx` is set |
| `write_markdown_sidecar` | `true` | Also write `.md` next to each `.json` |

See [config-keys.md](./config-keys.md).

---

## What is recorded

| Call site | Recorded |
|-----------|----------|
| `run_prompt_envelope` (all `task_kind`) | Yes, when `ctx` present |
| Primary retries (LLM volley extend) | Each retry = new sequence number |
| Arbiter | Yes (`record_stage_key` = parent stage) |
| Shard / collate | Yes |
| Specialists | Yes |
| Legacy `run_prompt` without ctx | No |
| Future local MLX | Use `provider: local_mlx` (plan) |

---

## Relationship to `stage_runs/attempt_*.json`

| Artifact | Granularity | Best for |
|----------|-------------|----------|
| `stage_runs/.../attempt_NNN.json` | One stage **attempt** outcome | Envelope, arbiter verdict, merge decision |
| `llm_calls/.../NN_task.json` | One **API round-trip** | Full prompts, every retry, copy-paste |

Cross-link via `links.attempt_artifact` on each call record.

---

## CLI export

```bash
source .venv/bin/activate
python tools/export_llm_calls.py --run-id exec_001_a1b2c3d4e5f6_20260601T120000Z
python tools/export_llm_calls.py --run-id exec_001_... --stage missing_framing --importance high
python tools/export_llm_calls.py --run-id exec_001_... --label-contains arbiter --format jsonl -o calls.jsonl
```

---

## Future: local LLM

When [local-llm-tier.md](./local-llm-tier.md) ships, local calls use the same schema with `provider: local_mlx` and `importance: low|medium` so OpenAI and on-device calls share one index.
