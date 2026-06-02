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
| `web.api_consent_persist` | `POST /api/session/api-consent`, GUI | When `true` (default), grants written to `ASSETS/.gui/api_consent.json` for convenience across `./scripts/run.sh` relaunches |
| `journey_ui.enabled` | GUI phase sidebar, Story Board, journey snapshot | When `false`, flat stage list (legacy UI); meta still written |
| `journey_ui.intent_at_start` | Start tab flow cards, `POST /api/runs` `flow_intent` | Early planning before G2 |
| `journey_ui.require_preview_listen` | Polish CTA gating after `assembly_preview` | When `true`, requires `preview_listened_at` milestone |
| `g1_5_require_prompt_approval` | `g15_prompt_review`, `sfx_elevenlabs`, GUI `/elevenlabs-prompts` | When `true`, blocks ElevenLabs SFX until operator approves crafted prompts |
| `narrative_qc.strict` | `gates.check_narrative_qc`, `selection_flow1`, `assembly_flow1` | When `true`, blocks `full_master_ranking` / `edl_flow1` on topic/chapter failures (production default `true`) |
| `show_description_qc.strict` | `publishing_flow3`, `gates.check_show_description_qc` | When `true`, blocks persisting invalid show description; default `false` (warn only) |
| `value_analysis.enabled` | `tools/run_value_spike.py`, `tools/extract_value_features.py`, gap volleys | Master switch for deterministic value features + investigation triggers (production default `true`) |
| `value_analysis.spike_scoring` | `run_value_spike.py` | Spike scorecard aggregation when master enabled |
| `value_analysis.transcript_features` | `extract_value_features.py --profile transcript` | Transcript-derived metrics artifact |
| `value_analysis.audio_features` | `extract_value_features.py --profile audio` | Audio-derived metrics (normalized.wav) |
| `value_analysis.auto_extract_after_content_context` | `understanding.run_content_context` | When master + this flag on, writes `understanding/value_features.json` after successful `content_context` (default off) |
| `models.<stage_key>` | `get_model()` → OpenAI calls | Wrong model: cost/quality drift; unknown name → API errors |

**Secrets override (not in JSON):** `INPUT_AUDIO_PATH` in `secrets.env` replaces `input_audio_path` for **CLI/automation only**. Not required for GUI: operators pick WAVs under `ASSETS/` — see [assets-and-executions.md](./assets-and-executions.md).

**Optional secrets (fallback):** `OPENAI_MODEL` used when a stage key is missing from tier resolution.

---

## `models` — runtime (BUILD-073)

Resolved by `get_model(stage_key)` in `src/interview_mux/config.py`:

1. If `models.<stage_key>` is a **string** → use that API ID directly (per-stage override).
2. Else `model_registry.resolve_model(stage_key, task_kind)` using `models.tiers` + `models.stages`.
3. Fallback: `OPENAI_MODEL` secret, then `gpt-4o-mini`.

Flat string overrides in `app.defaults.json` remain the escape hatch when you need an explicit API ID for one stage.

Tier guidance: [llm-stage-model-matrix.md](./llm-stage-model-matrix.md). API ID registry: [model-routing.md](./model-routing.md#model-tier-registry).

| Key | Purpose |
|-----|---------|
| `models.tiers.<economy\|standard\|flagship>` | Maps tier alias → API ID |
| `models.stages.<stage_key>.tier` | Default tier for `task_kind=primary` |
| `models.stages.<stage_key>.severity` | `low` \| `medium` \| `high` — drives collate floor (when set) |
| `models.<stage_key>` (string) | **Override:** explicit API ID wins over tier lookup |

**Optional secrets (tier overrides):**

| Key | Effect |
|-----|--------|
| `OPENAI_TIER_ECONOMY` | Override economy tier API ID |
| `OPENAI_TIER_STANDARD` | Override standard tier API ID |
| `OPENAI_TIER_FLAGSHIP` | Override flagship tier API ID |
| `OPENAI_MODEL` | Fallback when stage missing (unchanged) |

`task_kind` (`primary`, `arbiter`, `shard`, `collate`) is **not** a config key — resolved in code per [llm-orchestration.md](./llm-orchestration.md).

---

## `local_llm`

On-device MLX framing before OpenAI — [local-llm-tier.md](./local-llm-tier.md). Shipped in `config/app.defaults.json` (`enabled: true` by default on macOS).

| Key | Default | If wrong |
|-----|---------|----------|
| `local_llm.enabled` | `true` | No local pass when `false`; OpenAI-only volleys |
| `local_llm.model_id` | `mlx-community/Llama-3.2-3B-Instruct-4bit` | Fallback when no `selection.json`; override via secrets |
| `local_llm.models_dir` | `ASSETS/local_llm/models` | Download script and runner disagree on path |
| `local_llm.max_volley_turns` | `2` | OpenAI volley bloat; higher API cost |
| `local_llm.max_tokens` | `768` | Truncated framer JSON → forced escalation |
| `local_llm.escalate_on_parse_error` | `true` | `false` risks skipping OpenAI on bad local output |

**Secrets (optional):**

| Key | Effect |
|-----|--------|
| `LOCAL_LLM_MODEL_ID` | Highest-priority HF repo id for local tier |
| `LOCAL_LLM_REFRESH` | Set to `1` during bootstrap to force llmfit re-selection |

**llmfit selection:** `ASSETS/local_llm/selection.json` (written by `scripts/select_local_llm.py`). Picks largest context among `mlx-community/*` models with fit `perfect`/`good` and quality ≥ 45 (`MIN_QUALITY_SCORE` in `local_llm_selection.py`).

Setup: `python scripts/select_local_llm.py --download` (see [SETUP.md](../../SETUP.md)).

---

## Legacy note — flat-only config

Older docs described only a flat `models.<stage_key>` map. That still works, but **`models.tiers` + `models.stages` are the preferred shape** in `config/app.defaults.json`.

---

## `analysis.llm_call_records`

Every OpenAI call via `run_prompt_envelope` (when `ctx` is set). Spec: [llm-call-record-framework.md](./llm-call-record-framework.md).

| Key | Default | If wrong |
|-----|---------|----------|
| `enabled` | `true` | No per-call files; only `stage_runs` attempt summaries |
| `write_markdown_sidecar` | `true` | No `.md` copy-paste files next to JSON records |

Export: `python tools/export_llm_calls.py --run-id <exec_*>`.

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

## `analysis.specialists.enabled`

When `true`, runs economy-tier specialist passes after `missing_framing`, `segment_classification`, and `topic_coverage_audit`; enqueues investigations when thresholds are met. Default `false`.

---

## `analysis.prompt_examples.enabled`

When `true` (default), appends compact good/bad examples from `docs/prompts/_shared/examples/` into system prompts for `missing_framing`, `segment_classification`, and `topic_coverage_audit`.

---

## Stage enrichment inputs (`stage_enrichment.py`)

Optional compact keys in shaped `stage_input` (when artifacts exist):

| Key | Stages | Source |
|-----|--------|--------|
| `pause_ladder_hints` | `boundary_detection` | Transcript word gaps |
| `emphasis_regions` | `topic_coverage_audit`, `narrative_arc_plan` | `source_acoustic_profile` + segments |
| `quotability_signals` | `highlight_selection` | RMS peaks + text heuristics |
| `value_features_summary` | Flow + boundary stages | `understanding/value_features.json` (opt-in extract) |
| `comprehension_risks` | `missing_framing` | Specialist pass output (when enabled) |

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

## `mix` — crossfade and preclean gate (gap-closure)

| Key | Used by | If wrong |
|-----|---------|----------|
| `mix.crossfade_ms_flow1` / `mix.crossfade_ms_flow2` | `sound_design.py` speech/overlay concat | Harsh or overly long crossfades |
| `mix.crossfade_ms_assembly_preview` | `assembly_flow1.run_preview` | Preview clip seams audible or mushy |
| `mix.require_preclean_acknowledgment` | `web/runner.py`, GUI preclean offers | When `true`, single-stage runs block until checkpoint acknowledged in `run_meta.audio_preclean.offered_at` |

---

## `nle_edits`

| Key | Used by | If wrong |
|-----|---------|----------|
| `nle_edits.strict` | `nle_state.save_nle`, GUI NLE PUT | When `true`, invalid `segments/nle_edits.json` raises HTTP 400 instead of warn-only |

---

## `elevenlabs`

| Key | Used by | If wrong |
|-----|---------|----------|
| `elevenlabs.music_model_id` | `elevenlabs_rest.generate_music` | Wrong model (use `music_v2` for current sound-design path) |
| `elevenlabs.force_instrumental` | `elevenlabs_rest.generate_music` | `false` may yield vocals in beds/stingers |
| `elevenlabs.request_timeout_sec` | `elevenlabs_rest.py` REST calls | Hung or premature timeout on isolation/Music compose |
| `elevenlabs.max_retries` | `elevenlabs_rest.py` | Too few retries → flaky generation; too many → slow failures |
| `elevenlabs.max_upload_bytes` | `elevenlabs_rest.py`, `audio_preclean.py` chunk policy | Oversized WAV rejected or chunked before POST |

---

## Related

- [model-routing.md](./model-routing.md) — tier registry and v1 mapping
- [llm-orchestration.md](./llm-orchestration.md) — arbiter, shard/collate (spec)
- [llm-stage-model-matrix.md](./llm-stage-model-matrix.md) — per-stage tiers
- [prompts/README.md](../prompts/README.md) — prompt conventions
- `src/interview_mux/config.py` — merge rules
- `config/templates/secrets.env.example` — secret key names
- [../config/README.md](../config/README.md) — resolution order
