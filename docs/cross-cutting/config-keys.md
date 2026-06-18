# Config keys — `app.defaults.json` and overrides

**Runtime versions:** Python packages and CLI tools — [anchored-toolchain.md](./anchored-toolchain.md). OpenAI model IDs — [model-routing.md](./model-routing.md).

Authoritative defaults live in **`config/app.defaults.json`**. At runtime, `interview_mux.config.merged_config()` merges **`config/secrets/secrets.env`** (never commit secrets). This doc lists **meaningful keys**, what uses them, and **what breaks if wrong**.

---

## Launcher environment (not in `app.defaults.json`)

| Variable | Default | Used by | If wrong |
|----------|---------|---------|----------|
| `MUX_FRESH_SESSION` | `0` | `./scripts/run.sh` | `1` clears `ASSETS/.gui/active_execution.json` on every launch (no auto-restore); `0` keeps session pointer for refresh and restart |
| `MUX_MIRROR_OPERATOR_ERRORS` | `1` | `run.sh`, pipeline stderr mirror | `0` hides terminal mirror of operator errors |

---

## GUI session persistence (`ASSETS/.gui/active_execution.json`)

Written by `PUT /api/session/active`. Restored on `GET /api/session` → browser refresh and `./scripts/run.sh` restart (when `MUX_FRESH_SESSION=0`).

| Field | Values | Purpose |
|-------|--------|---------|
| `run_id` | execution id | Active run pointer |
| `selected_stage_id` | stage id | Pipeline sidebar focus |
| `active_tab` | `start` \| `executions` \| `pipeline` \| `logs` | Main tab |
| `pipeline_sub_tab` | `stage` \| `story` \| `timeline` \| … | Pipeline tool row |
| `activity_log_tab` | `live` \| `step` \| `all` | Inline activity panel tab |
| `activity_log_collapsed` | bool | Collapse Pipeline activity column |
| `source_locked` | bool | Session source lock (default true when run active) |

No new `journey_ui.*` keys were added for the activity panel — tab/collapse state uses session fields above.

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
| `show_description_min_words` / `show_description_max_words` / `show_description_target_words` | Flow 3 schema band + editorial target (defaults **150** / **250** / **200**) | Blurb fails validation or drifts from product spec |
| `web_port` | `serve` / `run.sh` | GUI on wrong port / collision |
| `web.api_consent_persist` | `POST /api/session/api-consent`, GUI | When `true` (default), grants written to `ASSETS/.gui/api_consent.json` for convenience across `./scripts/run.sh` relaunches |
| `journey_ui.enabled` | GUI phase sidebar, Story Board, journey snapshot | When `false`, flat stage list (legacy UI); meta still written |
| `journey_ui.intent_at_start` | Start tab flow cards, `POST /api/runs` `flow_intent` | Early planning before G2 |
| `journey_ui.phase_sidebar` | `PipelineStepList` phase grouping | When `false`, flat numbered step list |
| `journey_ui.story_board` | `StoryBoardPanel` tab | When `false`, hides story-board tool tab |
| `journey_ui.unified_preclean_drawer` | `AudioQualityDrawer` + journey preclean hints | When `false`, drawer hidden (inline `PrecleanOfferCard` still works) |
| `journey_ui.express_flow1` | Express Flow 1 CTAs in journey kernel | When `false`, hides express shortcuts |
| `journey_ui.journey_log_filter` | Logs tab journey-scoped filter | When `false`, standard log filters only |
| `journey_ui.require_preview_listen` | Polish CTA gating after `assembly_preview` | When `true`, requires `POST …/milestones/preview-listened` before polish execute |
| `journey_ui.require_handoff_between_stages` | `custom_run_handoff`, pipeline batch runs, GUI execute | When `true` (default), pauses after each stage that writes custom-run descriptive JSON until `handoff-ack`; set `false` for unattended multi-stage runs |
| `journey_ui.enable_stage_reuse_offers` | `stage_execution_reuse`, pipeline, GUI | When `true` (default), blocks execute until reuse decision when candidates exist; when `false`, UI still lists offers but does not block (CLI: `--no-reuse-offers`) — [stage-execution-reuse.md](../workflows/stage-execution-reuse.md) |
| `journey_ui.require_write_approval_per_stage` | `write_staging`, pipeline, GUI | When `true` (default), stage outputs land in `.pending_writes/<stage_id>/` until operator approves in WriteApprovalPanel (`POST …/pending-writes/{stage}/approve`); when `false`, writes go directly to final paths. Reuse copies respect the same staging when enabled. |
| `g1_5_require_prompt_approval` | `sfx_prompt_review`, `sfx_mmaudio`, GUI `/sfx-prompts` | When `true` (shipped default), blocks MMAudio SFX until operator approves crafted prompts |
| `narrative_qc.strict` | `gates.check_narrative_qc`, `selection_flow1`, `assembly_flow1` | When `true`, blocks `full_master_ranking` / `edl_flow1` on topic/chapter failures (production default `true`) |
| `edl_qc.strict` | `gates.check_edl_qc`, `assembly_flow1`, `tools/validate_edl.py` | When `true`, blocks invalid EDL timeline mechanics before mix/export |
| `edl_narrative_qc.strict` | `gates.check_edl_narrative_qc`, `assembly_flow1`, `tools/validate_narrative.py --include-edl` | When `true`, blocks `edl_flow1` when final EDL breaks coverage, chapter continuity, ordering constraints, transitions, gap placements, or flagship audit findings |
| `show_description_qc.strict` | `publishing_flow3`, `gates.check_show_description_qc` | When `true` (shipped default), blocks persisting invalid show description; when `false`, warn only |
| `value_analysis.enabled` | `tools/run_value_spike.py`, `tools/extract_value_features.py`, gap volleys | Master switch for deterministic value features + investigation triggers (production default `true`) |
| `value_analysis.spike_scoring` | `run_value_spike.py` | Spike scorecard aggregation when master enabled |
| `value_analysis.transcript_features` | `extract_value_features.py --profile transcript` | Transcript-derived metrics artifact |
| `value_analysis.audio_features` | `extract_value_features.py --profile audio` | Audio-derived metrics (normalized.wav) |
| `value_analysis.auto_extract_after_content_context` | `understanding.run_content_context` | When master + this flag on, writes `understanding/value_features.json` after successful `content_context` (default **on** in shipped `app.defaults.json`) |
| `interview_spine.enabled` | `interview_spine_stage.run_interview_spine_build` | Master switch for time-aligned comprehension spine (default **on**) |
| `interview_spine.clap_enabled` | `interview_spine/clap_index.py` | Build CLAP sidecar `understanding/interview_spine/embeddings.npz`; fail-open when MMAudio venv missing |
| `interview_spine.prosody_enabled` | `interview_spine/features.py`, SAP `prosody_summary` | Per-window F0 via librosa pyin when available |
| `interview_spine.window_sec_default` | `interview_spine/windows.py` | Default window length (seconds) for conversational pace |
| `interview_spine.window_sec_dense` | `interview_spine/windows.py` | Window length when SAP `pace_class` is `dense` |
| `interview_spine.window_sec_calm` | `interview_spine/windows.py` | Window length when SAP `pace_class` is `calm` |
| `interview_spine.hop_sec` | `interview_spine/windows.py` | Hop for subdividing long spans |
| `interview_spine.boundary_fusion_min_sources` | `interview_spine/boundaries.py` | Minimum fused sources to keep boundary events (default `1`) |
| `interview_spine.clap_model_id` | `tools/clap_embed_window.py` | CLAP model id for retrieval embeddings |
| `interview_spine.clap_timeout_sec` | `interview_spine/clap_index.py` | Subprocess timeout per window embed |
| `interview_spine.ssl_enabled` | — | **Opt-in only** — Wav2Vec/SSL merge path; default **false** (H-ING-01 gate preserved) |
| `interview_spine.flow2_quotability_enabled` | `stage_enrichment.quotability_signals` | Fuse spine boundary events into Flow 2 quotability proxy |
| `value_analysis.orc03_enabled` | `coherence/config.py` | Master sub-flag for H-ORC-03 long-run coherence (requires `value_analysis.enabled`) |
| `coherence.enabled` | `coherence/analyze.py` | Master switch for coherence report + investigations |
| `coherence.min_duration_ms` | `coherence/duration_gate.py` | Activation threshold (default **1800000** = 30 minutes) |
| `coherence.max_investigations_per_run` | `coherence/investigations.py` | Cap enqueue per run |
| `coherence.max_risks_in_memory` | `coherence/memory_sync.py` | Cap `analysis_state.coherence_risks[]` |
| `coherence.topic_drift_threshold` | `coherence/analyze.py` | Minimum `drift_score` for topic_drift risk |
| `coherence.claim_contradiction_threshold` | `coherence/claim_contradiction.py` | Minimum confidence for contradiction risk |
| `coherence.missing_callback_threshold` | `coherence/missing_callback.py` | Minimum confidence for missing callback risk |
| `coherence.require_acoustic_novelty` | `coherence/analyze.py` | Require novelty gate for topic_drift |
| `coherence.novelty_min_delta` | `coherence/novelty.py`, `analyze.py` | Adjacent-window novelty minimum |
| `coherence.theme_alignment_min` | `coherence/theme_alignment.py` | Token overlap floor for theme match |
| `coherence.blocking_claim_contradiction` | `coherence/claim_contradiction.py` | High-confidence contradictions block `analysis_ready` |
| `coherence.replace_stub_topic_shift_hints` | `interview_spine/boundaries.py`, `value_analysis/extract.py` | Disable speaker-turn-only stub when full coherence on |
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

Tier guidance: [llm-stage-model-matrix.md](./llm-stage-model-matrix.md). API ID registry: [model-routing.md](./model-routing.md#model-tier-registry). Committed defaults use **flagship** for all `STAGE_ARTIFACT_SCHEMAS` stages — [artifact-generation-and-validation.md](./artifact-generation-and-validation.md).

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
| `local_llm.min_confidence` | `0.6` | Local framing below threshold → escalate to OpenAI |
| `local_llm.skip_openai_primary_when_local_satisfied` | `false` | When `true`, may skip OpenAI primary on high-confidence local output (P0–P2 stages always escalate) |
| `local_llm.apply_to_specialists` | `true` | Local volley before economy specialist passes |
| `local_llm.apply_to_shards` | `true` | Local volley before shard calls |
| `local_llm.apply_to_collate` | `true` | Local volley before collate calls |

**Secrets (optional):**

| Key | Effect |
|-----|--------|
| `LOCAL_LLM_MODEL_ID` | Highest-priority HF repo id for local tier |
| `LOCAL_LLM_REFRESH` | Set to `1` during bootstrap to force llmfit re-selection |

**llmfit selection:** `ASSETS/local_llm/selection.json` (written by `scripts/select_local_llm.py`). Picks largest context among `mlx-community/*` models with fit `perfect`/`good` and quality ≥ 45 (`MIN_QUALITY_SCORE` in `local_llm_selection.py`).

Setup: `python scripts/select_local_llm.py --download` (see [SETUP.md](../../SETUP.md)).

---

## `disfluency_extract` / `disfluency_restore`

Local VAD + optional faster-whisper filler detection after G0 — [disfluency-extract.md](../pipeline/transcription/disfluency-extract.md), [disfluency-restore.md](../pipeline/assembly_and_mux/disfluency-restore.md).

| Key | Default | If wrong |
|-----|---------|----------|
| `disfluency_extract.enabled` | `true` | Stage no-ops; gate auto-complete |
| `disfluency_extract.whisper_model` | `base` | Slow or inaccurate gap ASR |
| `disfluency_extract.compute_type` | `int8` | faster-whisper compute type |
| `disfluency_extract.gap_min_ms` / `gap_max_ms` | `80` / `2500` | Inter-word gap window for candidate events |
| `disfluency_extract.pad_ms` | `80` | Clip padding around gap audio |
| `disfluency_extract.min_event_ms` | `60` | Drop shorter detected events |
| `disfluency_extract.max_events` | `2000` | Cap catalog size per run |
| `disfluency_extract.vad_energy_dbfs` | `-42.0` | Energy VAD threshold for gap clips |
| `disfluency_extract.weights_dir` | `ASSETS/local_stt/models` | Whisper pass skipped if weights missing |
| `disfluency_restore.enabled` | `true` | EDL stays monolithic speech |
| `disfluency_restore.max_inter_segment_gap_ms` | `1200` | Max gap between speech slices when restoring |
| `disfluency_restore.crossfade_ms` | `30` | Crossfade when splicing filler clips in mix |
| `disfluency_restore.min_speech_slice_ms` | `200` | Minimum speech slice after split |
| `disfluency_restore.dedupe_overlap_ms` | `40` | Overlap dedupe between adjacent restore events |
| `run_meta.disfluency_restore.enabled` | — | Per-run override via `PATCH …/disfluency-restore` |

Setup: `python scripts/download_local_stt.py --model base` (optional; lexicon pass works without Whisper).

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

## `analysis.max_volley_retries`

Within-attempt volley retries when the model returns fixable validation errors (`llm_stage_routing.py`, `analysis_memory.py`). Default **2** in `app.defaults.json`. **Too low:** gives up before self-correction. **Too high:** cost thrash on stuck volleys.

---

## `analysis.max_queue_drains_per_stage`

Drains `investigation_queue` suggestions per stage. **Too low:** unresolved investigations pile up. **Too high:** thrash / cost.

---

## `analysis.context.*`

Consumed by `context_volley` shaping. Defaults in `config/app.defaults.json` (shipped: `transcript_full_chars` 72000, `max_stage_data_chars` 64000, `max_segments_in_context` 100). See [long-interview-chunking.md](../workflows/long-interview-chunking.md).

| Key | If wrong |
|-----|----------|
| `transcript_excerpt_chars` | Legacy excerpt fallback truncated in mid-pipeline stages |
| `transcript_full_chars` | Early understanding/segmentation blind past cutoff |
| `speaker_roles_sample_chars` | Speaker role inference sees too little of long interviews |
| `max_transcript_shards` | Long transcripts split into too few/many shard calls |
| `proactive_decompose_chars` | `content_context` single-pass vs shard/collate threshold |
| `segment_text_max_chars` | Gap text unreadable / over-truncated |
| `max_segments_in_context` | Tail segments invisible to ranking-like stages |
| `max_segments_in_gap_pass` | Gap pass misses part of timeline |
| `max_gap_evaluations` | Some segments never evaluated in one pass |
| `max_stage_data_chars` | Huge payloads rejected or truncated by model host |
| `interviewer_sample_lines` | Transitions stage lacks tone reference |

---

## `analysis.context_index.*`

Volley Q&A memory — [context-padding.md](./context-padding.md), `context_resolver.py`.

| Key | Default | Purpose |
|-----|---------|---------|
| `enabled` | `true` | Master switch for index read/write |
| `sync_plans_on_ensure` | `true` | Refresh `stage_plans` from code `STAGE_PLANS` on workspace ensure |
| `write_on_accept` | `true` | Append `volley_entries` on arbiter-accept merge |
| `prefer_index_over_legacy_summaries` | `false` | When `true`, `build_message_volley` uses index entries instead of legacy `_format_*` fallbacks only |

Rollout: ship with `prefer_index_over_legacy_summaries: false` (dual-write); enable after backfill smoke on real runs.

---

## `analysis.flow_hardening`

Fail-closed LLM stage progression — [LLM-ANALYSIS-ARCHITECTURE.md §18](../../LLM-ANALYSIS-ARCHITECTURE.md#18-flow-hardening). Implemented in `llm_flow_hardening.py`, `llm_preflight.py`, `artifact_cross_validate.py`.

| Key | Default | Purpose |
|-----|---------|---------|
| `enabled` | `true` | Master switch (`false` = legacy always `mark_done`) |
| `strict_critical_stages` | `true` | `SystemExit` on critical LLM stage failure |
| `preflight_enabled` | `true` | Deterministic checks before OpenAI |
| `cross_validate_enabled` | `true` | Cross-artifact checks at segmentation boundaries |
| `halt_on_schema_errors_with_accept` | `true` | Arbiter accept + schema errors → blocked |
| `investigation_dedupe` | `true` | Dedupe open investigations by kind+stage+target |
| `shard_min_success_ratio` | `0.75` | Min fraction of successful shards before collate |
| `inner_retry_require_delta` | `true` | Stop inner retries when volley/errors unchanged |
| `max_primary_attempts_per_stage` | `4` | Cap primary OpenAI calls per stage (`attempt_budget.py`) |
| `max_arbiter_rejects_per_stage` | `3` | Cap non-accept arbiter verdicts before hard stop |
| `stuck_signature_threshold` | `2` | Identical attempt signatures in a row → stage treated as stuck |
| `max_investigation_reruns_per_kind` | `2` | Cap investigation-driven reruns per investigation kind (`attempt_budget.py`) |
| `spend_block_stages` | see defaults | Stages that require complete upstream SDP/craft before API spend |
| `block_mix_without_sfx_when_enabled` | `true` | When `true`, block `mix_flow*` if SFX assets missing; set `false` for dry-mix debugging without generated WAVs |

When `enabled`, `pipeline.py` calls `maybe_require_upstream_llm_progress` before each LLM stage so upstream `.stage_done` and producer artifacts must be complete.

**Spend block:** `spend_block_stages` lists stage ids checked by `llm_flow_hardening.require_spend_prerequisites()` — default `sfx_prompt_craft`, `mmaudio_sfx_flow1`, `mmaudio_sfx_flow2`, `mix_flow1`, `mix_flow2`. If upstream `sound_design_plan.json` or craft artifacts are incomplete, the stage is blocked with no MMAudio generation. Override list only for dev; production should keep defaults.

**Loop policy:** See [LLM-ANALYSIS-ARCHITECTURE.md §20](../../LLM-ANALYSIS-ARCHITECTURE.md#20-loop-policy) and `attempt_budget.py`.

**Arbiter rubric optional fields** (per-stage JSON under `docs/prompts/_shared/arbiter-rubrics/`):

| Field | Default | Purpose |
|-------|---------|---------|
| `min_segment_coverage_ratio` | `0.85` (or `1.0` when manifest &lt;5 segments) | Threshold for generic `segment_coverage_ratio` lint on decompose-eligible stages |

---

## `analysis.specialists.enabled`

When `true` (shipped default), runs economy-tier specialist passes after `missing_framing` (pre), `segment_classification`, `topic_coverage_audit`, and `full_master_ranking` (post); enqueues investigations when thresholds are met. Omit `pilot_stages` to run all mapped stages globally.

| Key | Default | Purpose |
|-----|---------|---------|
| `comprehension_risk_threshold` | `0.7` | Minimum `risk_score` from `comprehension_risk_blind` specialist before enqueueing a `comprehension_risk` investigation |

---

## `analysis.prompt_examples`

Few-shot example injection into system prompts via `stages/llm_runner.py` → `load_compact_examples()`.

| Key | Default | Purpose |
|-----|---------|---------|
| `enabled` | `true` | Master switch; when `false`, no example packs appended |
| `mode` | `full` (shipped) | `compact` — per-stage char cap (`COMPACT_EXAMPLE_MAX_CHARS_BY_STAGE`); `full` — entire example `.md` file |
| `stages` | *(omit = built-in list)* | Optional allowlist; when set, only listed `stage_key`s receive examples |

**Built-in stages** (when `stages` omitted): all keys in `STAGE_EXAMPLE_FILES` — includes P0/P1 stages and sound-design packs when example files exist. Narrower runtime default than the full reference list in [prompts/README.md](../prompts/README.md).

**If wrong:** `compact` truncates mid-pattern → model misses bad-example guardrails; `full` on very long packs increases token cost but improves quality-first runs (shipped default). Unknown `mode` falls back to `compact`.

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
| `CURSOR_API_KEY` | Required for [CURSOR_EXECUTE](../../CURSOR_EXECUTE/README.md) agent runs — set in `config/secrets/secrets.env` or env; also used by [june182026build/run.sh](../../docs/build-out/june182026build/run.sh) |

Optional placeholders in `config/templates/secrets.env.example` (AssemblyAI, Deepgram, etc.) are **not wired** until an adapter exists — document when adding code.

---

## `sound_design`

SDP asset caps and post-generation placement QA — [sound-design.md](./sound-design.md), [post-generation-placement.md](./post-generation-placement.md).

| Key | Default | Used by | If wrong |
|-----|---------|---------|----------|
| `max_assets_flow1` | `6` | `sound_design.py` Flow 1 plan | Too many cues → API cost; too few → thin master |
| `max_assets_flow2` | `4` | `sound_design.py` Flow 2 plan | Montage under-designed or over-spent |
| `max_palettes` | `3` | `sound_design_palettes` planning bounds | Over-broad palette spread or constrained thematic coverage |
| `use_adaptive_caps` | `true` | `sound_design` planners + sonic context posture | Ignores scenario-based cap tuning when false |
| `post_listen_gate_mode` | `warn` | post-listen QA UX/reporting | Unexpected hard-block vs advisory behavior |
| `placement_qa_enabled` | `true` | `placement_qa.py` → `maybe_run_placement_qa` after `mmaudio_sfx_flow*` (and on mix refresh) | When `true`, writes `sound_design/placement_adjustments.json`; `apply_placement_adjustments` applies hints in `flow1_overlays_from_sdp` / Flow 2 overlay builder at mix |

`placement_qa` is deterministic (no OpenAI) — reads SDP cues + `source_acoustic_profile` and logs hints via `ctx.log()`. Does not auto-rewrite the plan; operator or re-run adjusts.

---

## `mix` — crossfade, slice policy, completeness (gap-closure)

| Key | Used by | If wrong |
|-----|---------|----------|
| `mix.crossfade_ms_flow1` / `mix.crossfade_ms_flow2` | `sound_design.py` speech/overlay concat | Harsh or overly long crossfades (base ms before adaptive scaling) |
| `mix.crossfade_ms_assembly_preview` | `assembly_flow1.run_preview`, `audio_preclean.py` chunk merge | Preview clip seams audible or mushy |
| `mix.adaptive_crossfade` | `audio_timeline.append_with_crossfade` via `sound_design.py` | When `true` (default), crossfade length scales 80–200 ms from tail/head energy |
| `mix.adaptive_level_from_sap` | `sound_design.py` mix level defaults from source acoustic profile | Missed speech-first level adaptation by pace/policy |
| `mix.scenario_overlay_rules` | `sound_design.py` scenario-specific overlay behavior | Overlay cadence ignores scenario posture constraints |
| `mix.word_boundary_cuts` | `sound_design.py` EDL/highlight slices | When `true`, nudge slice ends to transcript word boundaries |
| `mix.word_boundary_margin_ms` / `mix.word_boundary_max_shift_ms` | `audio_timeline.snap_cut_to_word_boundary` | Too small → mid-word cuts remain; too large → clips drift from EDL |
| `mix.normalize_vo_pickup` | `gaps.ingest_vo_pickup` | When `true`, writes loudnorm copies under `vo_pickup/normalized/` |
| `mix.completeness_gate.enabled` | `mix_completeness.enforce_mix_completeness` | When `true`, logs missing VO/SFX after mix |
| `mix.completeness_gate.mode` | `mix_completeness.enforce_mix_completeness` | `warn` (default) logs only; `block` raises before `master_flow*` |
| `mix.require_preclean_acknowledgment` | *(deprecated — unused)* | Formerly gated mix/master stages on mid-pipeline pre-clean ack; v1 offers only `before_ingest` and `g1_vo_pickup` (non-blocking) |
| `mix.intelligibility_qc.enabled` | `master_qc.maybe_check_mix_intelligibility` | Optional speech-vs-bed check after mix |

## `audio_preclean`

| Key | Default | Used by | If wrong |
|-----|---------|---------|----------|
| `audio_preclean.provider` | `deepfilternet` | `preclean/provider.json`, lineage | Wrong provider label in artifacts |
| `audio_preclean.chunk_max_bytes` | `52428800` | `audio_preclean.py` chunking before DeepFilterNet | Oversized sources chunked more/less than expected |
| `audio_preclean.local_fallback_enabled` | `true` | `stages/audio_preclean.py` | When `true` (default), DeepFilterNet failure falls back to ffmpeg `afftdn` denoise (`provider: ffmpeg_local`) |

See [local-audio-stack.md](./local-audio-stack.md) · [audio_preclean README](../pipeline/audio_preclean/README.md).

---

## `local_runtimes`

Isolated venv paths — [local-audio-stack.md](./local-audio-stack.md).

| Key | Default | If wrong |
|-----|---------|----------|
| `local_runtimes.mlx.venv_dir` | `ASSETS/local_llm/venv` | MLX subprocess fails — re-run `bootstrap_venv.sh` |
| `local_runtimes.deepfilter.venv_dir` | `ASSETS/local_deepfilter/venv` | Preclean DeepFilterNet subprocess fails |
| `local_runtimes.mmaudio.venv_dir` | `ASSETS/local_mmaudio/venv` | MMAudio SFX subprocess fails |
| `local_runtimes.*.enabled` | `true` | When `false`, `local_runtime` raises for that stack |

---

## `deepfilter`

| Key | Default | Used by | If wrong |
|-----|---------|---------|----------|
| `deepfilter.repo_dir` | `ASSETS/local_deepfilter/DeepFilterNet` | `deepfilter_runner`, bootstrap | Clone missing → enhance fails |
| `deepfilter.model` | `DeepFilterNet3` | `tools/deepfilter_enhance.py` | Wrong model load |
| `deepfilter.postfilter` | `false` | enhance CLI | Extra post-filter stage |
| `deepfilter.compensate_delay` | `true` | enhance CLI | Alignment vs latency tradeoff |
| `deepfilter.request_timeout_sec` | `600` | `local_runtime` subprocess timeout | Hung or premature timeout |

---

## `mmaudio`

| Key | Default | Used by | If wrong |
|-----|---------|---------|----------|
| `mmaudio.repo_dir` | `ASSETS/local_mmaudio/MMAudio` | `mmaudio_runner`, bootstrap | Clone missing → generation fails |
| `mmaudio.model_id` | `large_44k_v2` | `mmaudio_generate.py` | Wrong HF weights |
| `mmaudio.device` | `auto` | local MMAudio runtime device choice | Wrong backend selection / avoidable runtime failures |
| `mmaudio.default_duration_sec` | `8.0` | craft/generate fallback duration | Unexpected clip length when role duration absent |
| `mmaudio.min_duration_sec` / `max_duration_sec` | `3.0` / `8.0` | `mmaudio_runner.clamp_duration_seconds` | Clamped generation length |
| `mmaudio.duration_bands_by_role` | role map | craft validation and plan-duration sanity | Role-specific lengths drift from product timing policy |
| `mmaudio.theme_fit_threshold` | `0.6` | post-generation thematic QA checks | Too lenient/strict thematic acceptance |
| `mmaudio.silence_rms_threshold` | `0.001` | silence/near-silence QA detection | False silence passes or noisy rejects |
| `mmaudio.semantic_qa_enabled` | `true` | Tier-2 CLAP text–audio similarity via `tools/clap_similarity.py` in MMAudio venv | Requires MMAudio venv bootstrap; fail-open when CLAP unavailable |
| `mmaudio.semantic_qa_threshold` | `0.18` | Minimum CLAP cosine similarity for pass | Low scores warn or fail depending on `semantic_qa_fail_on_low` |
| `mmaudio.semantic_qa_fail_on_low` | `false` | When true, sub-threshold CLAP scores set `verdict=fail` | Stricter auto-refine/regenerate loop |
| `mmaudio.semantic_qa_model_id` | `laion/clap-htsat-fused` | Hugging Face CLAP model id | Model download size / runtime |
| `mmaudio.semantic_qa_timeout_sec` | `120` | Per-asset CLAP subprocess timeout | Timeouts skip Tier-2 with `semantic_qa_verdict=skipped` |
| `mmaudio.cfg_strength_default` | `4.5` | `resolve_cfg_strength` | Global CFG fallback |
| `mmaudio.cfg_strength_by_role` | role map | `resolve_cfg_strength` | Per-role adherence |
| `mmaudio.num_steps` | `25` | `mmaudio_generate.py` | Quality vs speed |
| `mmaudio.seed_strategy` | `asset_id_hash` | `resolve_seed` | `fixed` / `random` / `asset_id_hash` |
| `mmaudio.fixed_seed` | `42` | `resolve_seed` when strategy `fixed` | Reproducibility |
| `mmaudio.legacy_influence_prose` | `false` | append influence to positive prompt | legacy prose-influence fallback |
| `mmaudio.auto_refine_enabled` | `true` | `sfx_mmaudio.maybe_auto_refine` | LLM refine after QA/listen fail |
| `mmaudio.auto_refine_max_attempts_per_asset` | `2` | refine loop cap | Runaway LLM spend |
| `mmaudio.auto_refine_on_qa_fail` / `on_listen_fail` | `true` | auto-refine triggers | Which failures invoke refine |
| `mmaudio.auto_refine_on_trauma` | `true` | auto-refine for `trauma_adjacent` without manual override | Set `false` to require per-asset `sfx_auto_refine_override` |
| `mmaudio.request_timeout_sec` | `900` | `local_runtime` subprocess timeout | Long generations time out |

Craft artifact optional fields (`sound_design/sfx_prompts.json`): `mmaudio_variant`, `cfg_strength`, `num_steps`, `seed`, `regression_notes` — see [mmaudio-prompt-tuning.md](./mmaudio-prompt-tuning.md).

Optional lock files: `requirements-local-mlx.txt`, `requirements-local-deepfilter.txt`, `requirements-local-mmaudio.txt` — regenerate with `pip-compile` when pinning local stacks.

---

## `nle_edits`

| Key | Used by | If wrong |
|-----|---------|----------|
| `nle_edits.strict` | `nle_state.save_nle`, GUI NLE PUT | When `true`, invalid `segments/nle_edits.json` raises HTTP 400 instead of warn-only |

---

## Related

- [model-routing.md](./model-routing.md) — tier registry and v1 mapping
- [llm-orchestration.md](./llm-orchestration.md) — arbiter, shard/collate (spec)
- [llm-stage-model-matrix.md](./llm-stage-model-matrix.md) — per-stage tiers
- [prompts/README.md](../prompts/README.md) — prompt conventions
- `src/interview_mux/config.py` — merge rules
- `config/templates/secrets.env.example` — secret key names
- [../config/README.md](../config/README.md) — resolution order
