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
| `g1_5_require_prompt_approval` | `g15_prompt_review`, `sfx_elevenlabs`, GUI `/elevenlabs-prompts` | When `true` (shipped default), blocks ElevenLabs SFX until operator approves crafted prompts |
| `narrative_qc.strict` | `gates.check_narrative_qc`, `selection_flow1`, `assembly_flow1` | When `true`, blocks `full_master_ranking` / `edl_flow1` on topic/chapter failures (production default `true`) |
| `edl_qc.strict` | `gates.check_edl_qc`, `assembly_flow1`, `tools/validate_edl.py` | When `true`, blocks invalid EDL timeline mechanics before mix/export |
| `edl_narrative_qc.strict` | `gates.check_edl_narrative_qc`, `assembly_flow1`, `tools/validate_narrative.py --include-edl` | When `true`, blocks `edl_flow1` when final EDL breaks coverage, chapter continuity, ordering constraints, transitions, gap placements, or flagship audit findings |
| `show_description_qc.strict` | `publishing_flow3`, `gates.check_show_description_qc` | When `true` (shipped default), blocks persisting invalid show description; when `false`, warn only |
| `value_analysis.enabled` | `tools/run_value_spike.py`, `tools/extract_value_features.py`, gap volleys | Master switch for deterministic value features + investigation triggers (production default `true`) |
| `value_analysis.spike_scoring` | `run_value_spike.py` | Spike scorecard aggregation when master enabled |
| `value_analysis.transcript_features` | `extract_value_features.py --profile transcript` | Transcript-derived metrics artifact |
| `value_analysis.audio_features` | `extract_value_features.py --profile audio` | Audio-derived metrics (normalized.wav) |
| `value_analysis.auto_extract_after_content_context` | `understanding.run_content_context` | When master + this flag on, writes `understanding/value_features.json` after successful `content_context` (default **on** in shipped `app.defaults.json`) |
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

**Spend block:** `spend_block_stages` lists stage ids checked by `llm_flow_hardening.require_spend_prerequisites()` — default `elevenlabs_prompt_craft`, `elevenlabs_sfx_flow1`, `elevenlabs_sfx_flow2`, `mix_flow1`, `mix_flow2`. If upstream `sound_design_plan.json` or craft artifacts are incomplete, the stage is blocked with no ElevenLabs call. Override list only for dev; production should keep defaults.

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
| `ELEVENLABS_API_KEY` | SFX + isolation fail — see [elevenlabs-integration-guide.md](./elevenlabs-integration-guide.md) |
| `CURSOR_API_KEY` | Required for [CURSOR_EXECUTE](../../CURSOR_EXECUTE/README.md) agent runs — optional for main pipeline |

Optional placeholders in `config/templates/secrets.env.example` (AssemblyAI, Deepgram, etc.) are **not wired** until an adapter exists — document when adding code.

---

## `sound_design`

SDP asset caps and post-generation placement QA — [sound-design.md](./sound-design.md), [post-generation-placement.md](./post-generation-placement.md).

| Key | Default | Used by | If wrong |
|-----|---------|---------|----------|
| `max_assets_flow1` | `6` | `sound_design.py` Flow 1 plan | Too many cues → API cost; too few → thin master |
| `max_assets_flow2` | `4` | `sound_design.py` Flow 2 plan | Montage under-designed or over-spent |
| `placement_qa_enabled` | `true` | `placement_qa.py` → `maybe_run_placement_qa` after `elevenlabs_sfx_flow*` (and on mix refresh) | When `true`, writes `sound_design/placement_adjustments.json`; `apply_placement_adjustments` applies hints in `flow1_overlays_from_sdp` / Flow 2 overlay builder at mix |

`placement_qa` is deterministic (no OpenAI) — reads SDP cues + `source_acoustic_profile` and logs hints via `ctx.log()`. Does not auto-rewrite the plan; operator or re-run adjusts.

---

## `mix` — crossfade, slice policy, completeness (gap-closure)

| Key | Used by | If wrong |
|-----|---------|----------|
| `mix.crossfade_ms_flow1` / `mix.crossfade_ms_flow2` | `sound_design.py` speech/overlay concat | Harsh or overly long crossfades (base ms before adaptive scaling) |
| `mix.crossfade_ms_assembly_preview` | `assembly_flow1.run_preview`, `audio_preclean.py` chunk merge | Preview clip seams audible or mushy |
| `mix.adaptive_crossfade` | `audio_timeline.append_with_crossfade` via `sound_design.py` | When `true` (default), crossfade length scales 80–200 ms from tail/head energy |
| `mix.word_boundary_cuts` | `sound_design.py` EDL/highlight slices | When `true`, nudge slice ends to transcript word boundaries |
| `mix.word_boundary_margin_ms` / `mix.word_boundary_max_shift_ms` | `audio_timeline.snap_cut_to_word_boundary` | Too small → mid-word cuts remain; too large → clips drift from EDL |
| `mix.normalize_vo_pickup` | `gaps.ingest_vo_pickup` | When `true`, writes loudnorm copies under `vo_pickup/normalized/` |
| `mix.completeness_gate.enabled` | `mix_completeness.enforce_mix_completeness` | When `true`, logs missing VO/SFX after mix |
| `mix.completeness_gate.mode` | `mix_completeness.enforce_mix_completeness` | `warn` (default) logs only; `block` raises before `master_flow*` |
| `mix.require_preclean_acknowledgment` | *(deprecated — unused)* | Formerly gated mix/master stages on mid-pipeline pre-clean ack; v1 offers only `before_ingest` and `g1_vo_pickup` (non-blocking) |
| `mix.intelligibility_qc.enabled` | `master_qc.maybe_check_mix_intelligibility` | Optional speech-vs-bed check after mix |

## `audio_preclean`

| Key | Used by | If wrong |
|-----|---------|----------|
| `audio_preclean.local_fallback_enabled` | `stages/audio_preclean.py` | When `true` (default), ElevenLabs failure falls back to ffmpeg `afftdn` denoise (`provider: rnnoise_local`) |

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
