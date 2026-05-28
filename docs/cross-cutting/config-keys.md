# Config keys — `app.defaults.json` and overrides

**Runtime versions:** Python packages and CLI tools — [anchored-toolchain.md](./anchored-toolchain.md). OpenAI model IDs — [model-routing.md](./model-routing.md).

Authoritative defaults live in **`config/app.defaults.json`**. At runtime, `interview_mux.config.merged_config()` merges **`config/secrets/secrets.env`** (never commit secrets). This doc lists **meaningful keys**, what uses them, and **what breaks if wrong**.

---

## Top-level

| Key | Used by | If wrong |
|-----|---------|----------|
| `assets_root` | `RunContext`, GUI assets list (`GET /api/assets`) | Wrong folder for audio discovery |
| `input_audio_path` | CLI / tools **default** when no run exists yet | Headless analysis points at missing file; **GUI operators use asset picker instead** — [assets-and-executions.md](./assets-and-executions.md) |
| `data_root` | Legacy runs `data/run_NNN` | Legacy paths broken |
| `executions_root` | New runs under `ASSETS/executions/...` | Runs created outside expected tree; resume breaks |
| `sample_rate` | Ingest / mastering expectation | Wrong SR → Transcribe or mux issues |
| `flow1_target_lufs` / `flow2_target_lufs` | Mastering targets (when enforced) | Wrong loudness “sound” |
| `web_port` | `serve` / `run.sh` | GUI on wrong port / collision |
| `g1_5_require_prompt_approval` | `g15_prompt_review`, `sfx_elevenlabs`, GUI `/elevenlabs-prompts` | When `true`, blocks ElevenLabs SFX until operator approves crafted prompts |
| `value_analysis.enabled` | `tools/run_value_spike.py`, `tools/extract_value_features.py` | Master switch for optional R&D tooling (default off) |
| `value_analysis.spike_scoring` | `run_value_spike.py` | Spike scorecard aggregation when master enabled |
| `value_analysis.transcript_features` | `extract_value_features.py --profile transcript` | Transcript-derived metrics artifact |
| `value_analysis.audio_features` | `extract_value_features.py --profile audio` | Audio-derived metrics (normalized.wav) |
| `models.<stage_key>` | `get_model()` → OpenAI calls (**v1**) | Wrong model: cost/quality drift; unknown name → API errors |

**Secrets override (not in JSON):** `INPUT_AUDIO_PATH` in `secrets.env` replaces `input_audio_path` for **CLI/automation only**. Not required for GUI: operators pick WAVs under `ASSETS/` — see [assets-and-executions.md](./assets-and-executions.md).

**Optional secrets (fallback, v1):** `OPENAI_MODEL` used when a stage key is missing from `models` map.

---

## `models` — v1 (current runtime)

Flat map: each `models.<stage_key>` is a **string** OpenAI API model ID. Resolved by `get_model(stage_key)` in `src/interview_mux/config.py` with fallback to `OPENAI_MODEL` then `gpt-4o-mini`.

Tier guidance (target defaults): [llm-stage-model-matrix.md](./llm-stage-model-matrix.md). API ID registry: [model-routing.md](./model-routing.md#model-tier-registry).

---

## `models` — proposed (not yet implemented)

**Status: spec only.** Smart routing per [llm-orchestration.md](./llm-orchestration.md).

```json
"models": {
  "tiers": {
    "economy": "<api-id>",
    "standard": "<api-id>",
    "flagship": "<api-id>"
  },
  "stages": {
    "missing_framing": { "tier": "flagship", "severity": "high" },
    "segment_classification": { "tier": "standard", "severity": "medium" }
  },
  "missing_framing": "gpt-4o"
}
```

| Key | Purpose |
|-----|---------|
| `models.tiers.<economy\|standard\|flagship>` | Maps tier alias → API ID |
| `models.stages.<stage_key>.tier` | Default tier for `task_kind=primary` |
| `models.stages.<stage_key>.severity` | `low` \| `medium` \| `high` — drives collate floor |
| `models.<stage_key>` (string) | **Override:** explicit API ID wins over tier lookup |

**Optional secrets (BUILD-073):**

| Key | Effect |
|-----|--------|
| `OPENAI_TIER_ECONOMY` | Override economy tier API ID |
| `OPENAI_TIER_STANDARD` | Override standard tier API ID |
| `OPENAI_TIER_FLAGSHIP` | Override flagship tier API ID |
| `OPENAI_MODEL` | Fallback when stage missing (unchanged) |

`task_kind` (`primary`, `arbiter`, `shard`, `collate`) is **not** a config key — resolved in code per [llm-orchestration.md](./llm-orchestration.md).

---

## `analysis.max_iterations_per_stage`

Orchestrator inner loop per LLM stage. **Too low:** exits before fixing validation errors. **Too high:** extra cost on stuck stages.

---

## `analysis.max_queue_drains_per_stage`

Drains `investigation_queue` suggestions per stage. **Too low:** unresolved investigations pile up. **Too high:** thrash / cost.

---

## `analysis.context.*`

Consumed by `context_volley` shaping. See [long-interview-chunking.md](../workflows/long-interview-chunking.md).

| Key | If wrong |
|-----|----------|
| `transcript_excerpt_chars` | Truncated evidence in mid-pipeline stages |
| `transcript_full_chars` | Early understanding/segmentation blind past cutoff |
| `segment_text_max_chars` | Gap text unreadable / over-truncated |
| `max_segments_in_context` | Tail segments invisible to ranking-like stages |
| `max_segments_in_gap_pass` | Gap pass misses part of timeline |
| `max_gap_evaluations` | Some segments never evaluated in one pass |
| `max_stage_data_chars` | Huge payloads rejected or truncated by model host |
| `interviewer_sample_lines` | Transitions stage lacks tone reference |

---

## `analysis.prompt_thresholds.*`

Injected into prompts / STT prep; changing them changes **editorial behavior**, not just formatting.

| Key | If wrong |
|-----|----------|
| `pause_split_ms` | Too small → fragment boundaries; too large → merges distinct ideas |
| `short_question_max_words` | Mis-splits Q+A pairs in boundary prompt |
| `interviewer_question_max_words` / `interviewer_setup_max_words` | VO lines too long for product spec |
| `highlight_setup_max_sec` | Flow 2 clip + VO timing invalid vs schema |
| `max_chapters` | Narrative plan violates cap → validation / model confusion |
| `max_highlight_clips` | Selection over cap (should match product ≤5) |
| `show_description_min_words` / `show_description_max_words` | Flow 3 JSON schema band (150–250) | Blurb too short/long for hosts |
| `show_description_target_words` | Editorial target (~200) in `app.defaults.json` | Copy drifts from product spec |
| `models.podcast_show_description` | OpenAI model for Flow 3 blurb (flagship tier) | Weak or generic show copy |

---

## `_comment`

Documentation only — not read by code.

---

## `secrets.env` keys (merged, not in `app.defaults.json`)

Loaded by `load_secrets()` / `merged_config()`. **Never commit** real values.

| Key | Effect if wrong / missing |
|-----|---------------------------|
| `INPUT_AUDIO_PATH` | Overrides `input_audio_path` for CLI default — optional when using GUI + `exec_*` run ids |
| `OPENAI_API_KEY` | LLM stages fail at runtime |
| `OPENAI_MODEL` | Fallback when `models.<stage>` missing |
| `OPENAI_SPEECH_MODEL` | Reserved for future OpenAI audio adapters |
| `AWS_DEFAULT_REGION` / `AWS_REGION` | Transcribe / S3 wrong region |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_PROFILE` | Auth failures — see troubleshooting |
| `AWS_S3_BUCKET` / `AWS_S3_INPUT_KEY` / `AWS_S3_URI` | Transcribe cannot read media |
| `ELEVENLABS_API_KEY` | SFX + isolation fail — see [elevenlabs-integration-guide.md](./elevenlabs-integration-guide.md) |

Optional placeholders in `config/templates/secrets.env.example` (AssemblyAI, Deepgram, etc.) are **not wired** until an adapter exists — document when adding code.

---

## Related

- [model-routing.md](./model-routing.md) — tier registry and v1 mapping
- [llm-orchestration.md](./llm-orchestration.md) — arbiter, shard/collate (spec)
- [llm-stage-model-matrix.md](./llm-stage-model-matrix.md) — per-stage tiers
- [prompts/README.md](../prompts/README.md) — prompt conventions
- `src/interview_mux/config.py` — merge rules
- `config/templates/secrets.env.example` — secret key names
- [../config/README.md](../config/README.md) — resolution order
