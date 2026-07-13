# HTTP API reference (FastAPI)

**Stack pins:** `fastapi`, `uvicorn`, `pydantic` — [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md). Use **Context7** at those versions when changing `server.py`.

Authoritative route list for **`interview_mux` web server** (`src/interview_mux/web/server.py`). The single-page GUI under `/` is a **React + TypeScript** app (source: `frontend/`, built to `web/static/`); all JSON state goes through **`/api/*`**.

**GUI build:** `./scripts/build_gui.sh` or `cd frontend && npm run build`. `./scripts/run.sh` builds automatically if static output is missing.

**Companion:** [gui-surface-map.md](./gui-surface-map.md) maps UI areas to these routes and on-disk artifacts.

---

## Base URL and static

| Item | Value |
|------|--------|
| Default port | From `config/app.defaults.json` → `web_port` (default **8765**) |
| API prefix | **`/api`** |
| Static UI | **`/`** — Vite-built React bundle in `src/interview_mux/web/static/` (source: `frontend/`) |
| CORS | `allow_origins=["*"]` (dev-friendly) |

---

## Conventions

- **`{run_id}`** — Execution directory name. New format: `exec_NNN_<hash12>_TIMESTAMP` (12-char `source_audio_hash_short` embedded). Legacy: `exec_NNN_TIMESTAMP` or `run_NNN`. Unknown id → **404** `Run not found`.
- **Artifact paths** — Query/body paths must be **relative to run root**, no `..`, no leading `/` — else **400** `Invalid artifact path`.
- **JSON responses** — Unless noted, `application/json`. Audio routes return **`FileResponse`** with guessed `Content-Type`.

---

## Global routes

| Method | Path | Query | Body | Response | Errors |
|--------|------|-------|------|----------|--------|
| `GET` | `/api/health` | — | — | `{"status": "ok"}` | — |
| `GET` | `/api/config` | — | — | Paths + feature flags — see **`GET /api/config` response** below | — |
| `GET` | `/api/session/api-consent` | — | — | `providers[]` (id, label, description, cost_hint), `grants` (persisted under `ASSETS/.gui/api_consent.json`) | — |
| `POST` | `/api/session/api-consent` | — | **ApiConsentBody** `{provider, granted}` | `ok`, `provider`, `granted`, `grants` | — |
| `GET` | `/api/session` | — | — | `server`, `active` (run id + optional `selected_stage_id`, `active_tab`, `pipeline_sub_tab`, `activity_log_tab`, `activity_log_collapsed`); if active run valid: `log` (tail 200 entries), `run_summary` | Active run cleared if resolve fails |
| `PUT` | `/api/session/active` | — | **ActiveBody** | Merged `active_execution.json` payload, or `{ok, active: null}` when `run_id` null | **400** invalid tab; **409** source lock |
| `DELETE` | `/api/session/active` | — | — | `{ok: true, active: null}` — clears active execution | — |
| `GET` | `/api/assets` | `recursive` (bool, default `true`) | — | `assets_root`, `files[]` with `path`, `name`, `size_bytes`, `modified_at` | — |

Lists discoverable **source** audio under `assets_root` (default `ASSETS/`). Skips top-level `executions` and `.gui`. Used by the GUI home **Input audio** panel — see [assets-and-executions.md](../cross-cutting/assets-and-executions.md).
| `GET` | `/api/runs` | — | — | `runs[]` — each includes `run_id`, `source_audio_hash`, `source_audio_hash_short`, summary fields; with `enrich=1`: `progress` (`done`/`total`), `last_stage`, `last_log`, `job_status`, `operator_phase`, `next_action` (truncated), `blocking_message`, `attention_count` | Per-run errors swallowed → `progress: {0,0}` |
| `POST` | `/api/runs` | — | **CreateRunBody** | `run_id`, `run_dir`, `execution_number`, `input_audio_path`, `source_audio_hash`, `source_audio_hash_short` | **404** if `input_audio_path` file missing |

### `CreateRunBody`

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `input_audio_path` | string | yes | Repo-relative path to source audio (typically from `GET /api/assets` → `files[].path`, e.g. `ASSETS/input/interview.wav`) |
| `run_id` | string \| null | no | If omitted, server allocates new `exec_*` id |

### `ActiveBody`

Partial updates merge into the existing active session (unset fields are preserved). Send `run_id: null` to clear.

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `run_id` | string \| null | no | Omit to update UI fields only; null clears active execution |
| `selected_stage_id` | string \| null | no | Pipeline stage focus |
| `active_tab` | string \| null | no | `start` \| `executions` \| `pipeline` \| `logs` |
| `pipeline_sub_tab` | string \| null | no | `stage` \| `story` \| `timeline` \| `profile` \| `files` \| `llm_calls` \| `volley_memory` |
| `activity_log_tab` | string \| null | no | `live` \| `step` \| `all` — Pipeline inline activity panel tab |
| `activity_log_collapsed` | bool \| null | no | When `true`, collapses the Pipeline activity log panel |
| `pipeline_collapsed_stages` | string[] \| null | no | Stage ids the operator collapsed in the Steps sidebar |
| `pipeline_expanded_done_stages` | string[] \| null | no | Done stage ids manually expanded for audit |
| `pipeline_filter_needs_you` | bool \| null | no | When `true`, Steps sidebar shows only stages with todo substeps |

### `GET /api/runs/{run_id}` — `journey` snapshot

| Field | Type | Notes |
|-------|------|--------|
| `journey.active_substep_id` | string \| null | Server-driven focus substep (`write_approval`, `running`, `gate:{stage}`, `blocked:{stage}`, …) — mirrors GUI `findActiveSubstep` |
| `journey.active_substep_label` | string \| null | Human label for the active substep (headline / sidebar hint) |
| `journey.phase_progress` | object | Per-phase `{done, total}` counts |
| `journey.phase_guidance` | object | Phase goals and actionable items |

### `GET /api/config` response

| Field | Notes |
|-------|-------|
| `assets_root`, `executions_root`, `data_root`, `web_port`, `repo_root` | Paths for GUI bootstrap |
| `api_consent_persist` | From `web.api_consent_persist` (default `true`) |
| `value_analysis_enabled` | Master `value_analysis.enabled` |
| `disfluency_extract_enabled` | `disfluency_extract.enabled` |
| `disfluency_restore_enabled` | `disfluency_restore.enabled` |
| `journey_ui` | Full `journey_ui` object from merged config (phase sidebar, story board, write approval, etc.) |
| `llm_routing_stage_ids` | Sorted stage ids with LLM routing debug summaries (`web/stages.py` → `LLM_ROUTING_STAGE_IDS`) |

---

## Per-run routes (`{run_id}`)

| Method | Path | Query | Body | Response | Errors |
|--------|------|-------|------|----------|--------|
| `GET` | `/api/runs/{run_id}/summary` | — | — | Run summary + `progress`, `last_log`, `handoff_ack` map | **404** |
| `GET` | `/api/runs/{run_id}` | — | — | `run_id`, `meta`, `handoff_ack`, `sfx_generated_assets[]`, `legacy_migration_warnings[]`, `REMOVED_selected_flow`, … | **404** |
| `GET` | `/api/runs/{run_id}/log` | `tail` (int, default **200**); optional `stage` (filter by stage id); optional `since_ts` (ISO timestamp — entries after this time) | — | `entries[]` — each `ts`, `level`, `message`, optional `stage`, `detail` | **404** |
| `POST` | `/api/runs/{run_id}/log` | — | **LogBody** (`message`, `level`, `stage`, optional `action_id`) | `ok`, `entry` | **404** |
| `GET` | `/api/runs/{run_id}/action-trace` | `tail` (int, default 50) | — | `entries[]` — structured action trace rows | **404** |
| `POST` | `/api/runs/{run_id}/action-trace/dump-last` | — | — | `ok`, `text`, `entries_used`; also appends dump to `gui_log.jsonl` | **404** |
| `GET` | `/api/runs/{run_id}/llm-routing` | — | — | `attempts[]` — per-stage routing summaries (`stage`, `task_kind`, `attempt`, `verdict`, `model_tier`, `shard_count`, `primary_attempt_count`, `budget_remaining_primary`, `stuck_count`, `deterministic_lint_errors[]`) from `understanding/stage_runs/` | **404** |
| `GET` | `/api/runs/{run_id}/llm-calls` | — | — | `call_count`, `calls[]` (summaries), `tree`, `stages` — [llm-call-record-framework.md](../cross-cutting/llm-call-record-framework.md) | **404** |
| `GET` | `/api/runs/{run_id}/llm-calls/record` | `path` (required, under `understanding/llm_calls/`) | — | Full call record + `_gui.openai_messages` | **404**, **400** |
| `PUT` | `/api/runs/{run_id}/llm-calls/record` | — | **LlmCallRecordUpdateBody** `{path, volley?, raw_response?}` | `ok`, `record` | **404**, **400** |
| `GET` | `/api/runs/{run_id}/timeline` | — | — | `duration_ms`, `segments` (with `_manifest_*` bounds), `vo_lines`, `nle`, `normalized_audio` | **404** |
| `GET` | `/api/runs/{run_id}/assembly-timeline` | — | — | `ready`, `clips[]`, `chapters[]`, `timeline_duration_ms`, `preview_audio` | **404** |
| `GET` | `/api/runs/{run_id}/waveform` | `path` (default `ingest/normalized.wav`) | — | `peaks[]`, `window_ms`, `duration_ms` | **404** |
| `GET` | `/api/runs/{run_id}/transcript` | — | — | `ready`, `words[]`, `duration_ms`, `audio_path`, `low_confidence_threshold`, `review_applied_at` — see **Transcript dock word edits** | **404** |
| `PATCH` | `/api/runs/{run_id}/transcript/words` | — | **TranscriptWordsPatchBody** | `ok`, `updated_count`, `words`, `text` — batch-safe (fuzzy replace) | **404** |
| `GET` | `/api/runs/{run_id}/nle` | — | — | NLE JSON object | **404** |
| `PUT` | `/api/runs/{run_id}/nle` | — | **NleBody** | `ok: true` | **404** |
| `PATCH` | `/api/runs/{run_id}/nle/segment` | — | **NleSegmentBody** | `ok`, `nle` | **404** |
| `POST` | `/api/runs/{run_id}/nle/batch` | — | **NleBatchBody** `{operations: [{segment_id, patch}]}` | `ok`, `updated`, `nle` | **400** schema, **404** |
| `POST` | `/api/runs/{run_id}/nle/split` | — | **SplitBody** | `ok`, `nle` | **404** |
| `POST` | `/api/runs/{run_id}/nle/snap-boundary` | — | **SnapBoundaryBody** `{segment_id, ms, edge}` | `ok`, `snapped_ms` | **400**, **404** |
| `GET` | `/api/runs/{run_id}/artifact` | `path` (string, **required**) | — | Parsed JSON or `{path, text}` for non-JSON | **404** artifact, **400** path |
| `PUT` | `/api/runs/{run_id}/artifact` | — | **ArtifactBody** | `ok`, `path` | **400** `schema_validation_failed` if path is in `ARTIFACT_WRITE_VALIDATORS` and data fails jsonschema, **400** if not `.json`, **404** |
| `POST` | `/api/runs/{run_id}/fill-artifact-gaps` | — | **FillArtifactGapsBody** `{path, api_consents?}` | Same ack shape as `execute` — background `mode: stage` for producing stage | **400** unknown path, **409** job running, **404** |
| `POST` | `/api/runs/{run_id}/extract-value-features` | — | — | `{ok, profiles_written[]}` when `value_analysis.enabled` | **400** if disabled, **404** |
| `PUT` | `/api/runs/{run_id}/artifact/text` | — | **ArtifactTextBody** `{path, text, invalidate_from?}` | `ok`, `path` | **400** if path not in stage editable/artifacts or is `.json`, **404** |
| `POST` | `/api/runs/{run_id}/handoff-ack` | — | **HandoffAckBody** `{stage_id}` | `ok`, `handoff_ack` (updates `run_meta.handoff_ack`) | **404** |
| `POST` | `/api/runs/{run_id}/flow` | — | **FlowBody** | `ok`, `REMOVED_selected_flow` | **404** |
| `POST` | `/api/runs/{run_id}/preclean-offer` | — | **PrecleanOfferBody** | `ok`, `changed`, `audio_preclean` | **400** invalid checkpoint/scope, **404** |
| `GET` | `/api/runs/{run_id}/stages/{stage_id}/reuse-offers` | — | — | `eligible`, `blocking`, `candidates[]` (hash fields, `paths[]`, `same_source_audio`), `pending_decision`, `current_source_audio_hash_short` | **404** unknown stage |
| `POST` | `/api/runs/{run_id}/stages/{stage_id}/reuse` | — | **StageReuseBody** `{action, source_run_id?}` | `ok`, `stage_reuse`, `copied[]` on accept | **400** ineligible source, **404** |
| `GET` | `/api/runs/{run_id}/pending-writes` | — | — | `stages[]` with `{stage_id, paths[]}` | **404** |
| `GET` | `/api/runs/{run_id}/pending-writes/{stage_id}` | — | — | `{stage_id, paths[]}` | **404** if none staged |
| `GET` | `/api/runs/{run_id}/pending-writes/{stage_id}/content` | `path` (required) | — | JSON object, or `{text}` for `.md`/`.txt` | **404** |
| `PUT` | `/api/runs/{run_id}/pending-writes/{stage_id}/content` | — | **PendingWriteContentBody** `{path, data? \| text?}` | `ok`, `path` | **400** |
| `POST` | `/api/runs/{run_id}/pending-writes/{stage_id}/approve` | — | — | `ok`, `flushed[]`, `stage_id` — copies staging → final paths, marks stage done | **404** if none staged |
| `POST` | `/api/runs/{run_id}/pending-writes/approve-batch` | — | optional `{phases?: string[], stage_ids?: string[]}` | `ok`, `approved{}`, `errors{}` — batch Save for first-try phase end | **409** run_busy |
| `POST` | `/api/runs/{run_id}/g1/skip-optional` | — | optional `{line_ids?: string[]}` | `ok`, `skipped[]`, `g1_missing[]` — mark non-blocking VO optional | **404** |
| `POST` | `/api/runs/{run_id}/pending-writes/{stage_id}/discard` | — | — | `ok`, `stage_id` — clears staging, invalidates from stage | **404** |

**GUI after approve/discard/gate complete:** The React client calls `advanceFromCheckpoint()` (refresh run → auto-execute next stage or focus blocker). See [gui-flow-hardening.md](./gui-flow-hardening.md).
| `GET` | `/api/runs/{run_id}/sfx-prompts` | — | — | `path`, `prompts[]`, `review`, `review_required`, `can_generate`, `listen_results[]`, `generated_assets[]` (`asset_id`, `path` under `sound_design/assets/`) | **404** missing prompts artifact |
| `PUT` | `/api/runs/{run_id}/sfx-prompts` | — | **ArtifactBody** (`path` must be `sound_design/sfx_prompts.json`) | `ok`, `path`, `review` (approval reset on edit) | **400** invalid path/payload, **404** |
| `POST` | `/api/runs/{run_id}/sfx-prompts/approve` | — | **SfxPromptApproveBody** | `ok`, `review`, `asset_ids`; logs `sfx_prompts_approved` | **404** missing prompts artifact |
| `POST` | `/api/runs/{run_id}/sfx-prompts/listen-result` | — | **SfxListenResultBody** (`asset_id`, `result`: `pass`\|`fail`, optional `note`, optional `mode`: `post_listen`\|`under_speech`) | `post_listen` (default): `ok`, `entry`, `sfx_listen_results[]`; appends `run_meta.sfx_listen_results`; logs `sfx_post_listen_pass` or `sfx_post_listen_fail`. `under_speech`: `ok`, `entry`, `speech_under_listen_results[]`; appends `run_meta.speech_under_listen_results` | **400** invalid body |
| `POST` | `/api/runs/{run_id}/sfx-prompts/refine` | — | **SfxPromptRefineBody** (`asset_ids?`, `force?`) | `ok`, `prompts[]`, `review`, `refined_asset_ids` — runs LLM `sfx_prompt_refine` | **409** job running |
| `POST` | `/api/runs/{run_id}/sfx-prompts/regenerate` | — | **SfxPromptRegenBody** (`asset_ids[]`) | Sets `sfx_regen_asset_ids`, clears stage done, starts `mmaudio_sfx_flow*` | **400** empty ids, **409** job running |
| `GET` | `/api/runs/{run_id}/sfx-qa` | — | — | `mmaudio_qa.json` contents (`version`, `assets[]` with verdict/reasons) | — |

**G1.5 response fields:** `GET /sfx-prompts` also returns `mmaudio_qa`, `generation_meta` (per-asset CFG/seed from last run).
| `POST` | `/api/runs/{run_id}/execute` | — | **ExecuteBody** | `ok`, `run_id`, `mode` (immediate ack; work runs in thread); or `ok: false`, `needs_api_consent` if providers not granted | **409** job already running, **404** |
| `GET` | `/api/runs/{run_id}/job` | — | — | `gui_job.json` payload or `{status: idle, run_id}` | — |
| `GET` | `/api/runs/{run_id}/transcript-review` | — | — | See **Transcript review response** below | **404** |
| `PUT` | `/api/runs/{run_id}/transcript-review/{chunk_id}` | — | **TranscriptChunkBody** | From `save_chunk_correction` | **404** no queue |
| `POST` | `/api/runs/{run_id}/transcript-review/complete` | — | **TranscriptReviewCompleteBody** | `ok`, `transcript_review_clear` | **400** queue not ready or pending chunks |
| `GET` | `/api/runs/{run_id}/disfluency-review` | — | — | Events, stats, `pending_count`, `review_complete` | **404** |
| `PUT` | `/api/runs/{run_id}/disfluency-review/{event_id}` | — | **DisfluencyEventBody** (`review_status`, optional `text`, `include_in_restore`) | `ok`, `stats` | **404** unknown event |
| `POST` | `/api/runs/{run_id}/disfluency-review/complete` | — | — | `ok`, `disfluency_review_clear` | **400** pending events |
| `PATCH` | `/api/runs/{run_id}/disfluency-restore` | — | **DisfluencyRestoreBody** (`enabled`) | `ok`, `disfluency_restore_enabled` | **404** |
| `GET` | `/api/runs/{run_id}/story-board` | — | — | `analysis_state`, `investigation_queue`, `content_brief`, `narrative_plan` (nullable), `source_acoustic_profile` (nullable), `value_features` (nullable), `operator_verified` | **404** |
| `PATCH` | `/api/runs/{run_id}/investigation-queue/{item_id}` | — | **InvestigationPatchBody** `{status}` | `ok`, `investigation_queue` — updates `understanding/investigation_queue.json` | **404** item/queue, **400** invalid queue |

| `GET` | `/api/session/lineage` | — | — | Immediate-previous run + per-stage reuse eligibility | — |
| `GET` | `/api/runs/{run_id}/workspace` | — | — | Working directory summary | — |
| `POST` | `/api/runs/{run_id}/reuse-from-previous` | `{ accept_all?: bool, stage_ids?: string[] }` | — | Bulk copy from immediate previous execution (hash-gated) | **409** busy |

**Removed:** `GET /api/runs/{run_id}/audio-quality` (404 — use journey snapshot + `PrecleanOfferCard`).
| `POST` | `/api/runs/{run_id}/milestones/preview-listened` | — | — | `ok`, `journey` — sets `preview_listened_at` when `journey_ui.require_preview_listen` gates polish CTAs | **404** |
| `GET` | `/api/runs/{run_id}/analysis-profile` | — | — | `analysis_state`, `investigation_queue`, `editable_paths`, `operator_verified`, `completion` | **404** |
| `PUT` | `/api/runs/{run_id}/analysis-profile` | — | **AnalysisProfileBody** | `ok`, `operator_verified`, `completion` | **404** |
| `POST` | `/api/runs/{run_id}/analysis-profile/verify` | — | — | `ok`, `operator_verified: true` | **404** |
| `POST` | `/api/runs/{run_id}/vo/{line_id}` | — | **multipart** field `file` (WAV) | `ok`, `path`, `g1_missing` | **404** |
| `POST` | `/api/runs/{run_id}/reset` | — | **ResetBody** | `ok: true` | **400** missing both fields, **404** audio |
| `GET` | `/api/runs/{run_id}/audio` | `path` (required); optional `pending=1`, `pending_stage=<stage_id>` | — | Binary file (final path, or staged copy when pending query set) | **404**, **400** |
| `GET` | `/api/runs/{run_id}/audio/sfx-under-speech` | `asset_id` (required) | — | Best-effort preview render for `SfxPostListenPanel` under-speech audition | **404** when preview backend unavailable or asset missing |
| `GET` | `/api/runs/{run_id}/source-audio` | — | — | Original input from `run_meta.json` | **404** |

### `ExecuteBody`

| Field | Type | Notes |
|-------|------|--------|
| `mode` | string | **`stage`** \| **`analysis`** \| **`analysis_until_g0`** \| **`flow1`** \| **`flow1_until_preview`** \| **`flow1_polish`** \| **`flow2`** \| **`flow3`** \| **`nle_apply`** |
| `nle_full_refresh` | bool | Optional for **`nle_apply`** — also run `transitions` and `edl_narrative_audit` before EDL rebuild (legacy; prefer `nle_apply_mode: full_refresh`) |
| `nle_apply_mode` | string | Optional for **`nle_apply`**: `trim_only` (EDL + preview only), `structural` (default — ranking when structural edits), `full_refresh` (structural + transitions + EDL narrative audit) |
| `stage` | string \| null | For `mode=stage`: stage id to run. Special: `transcript_review` triggers sign-off helper (see code). |
| `from_stage` | string \| null | If set and differs from `stage` for single-stage runs, **invalidates** from `from_stage` first. For `analysis` / `flow*`, passed as pipeline `from_stage`. |
| `until_stage` | string \| null | For batch modes (`analysis`, `flow1`, `flow2`, `flow3`, `flow1_until_preview`, `flow1_polish`): stop after this stage id (inclusive). Journey hints may set this (e.g. `transcript_review_build` for analysis-until-G0). |
| `api_consents` | object \| null | Map `openai` \| `aws` → `true` when operator granted session access (merged with `ASSETS/.gui/api_consent.json`) |

**Implementation:** `runner.start` returns immediately; poll **`GET …/job`** and **`GET …/log`**. Job `status` values include `running`, `running_with_warnings`, `complete`, `error`, `gate`, `needs_operator`, `awaiting_write_approval`, `interrupted`, `idle`. Additional job fields: `current_stage`, `stage_index`, `stage_total`, `stages_planned` (batch progress), `phase`, `step_index`, `step_total` (intra-stage checkpoint progress for long local stages), `needs_stage_reuse`, `reuse_candidates[]`, `awaiting_write_approval`, `pending_write_stage`. On **`GET /api/runs/{run_id}`**, when `job.status === "error"`, the response includes `job.last_error` with `message`, `stage`, and optional `traceback_excerpt`.

Stage `status` in **`GET /api/runs/{run_id}`** may be `awaiting_write_approval` when `.pending_writes/<stage_id>/` has unapproved files.

Mutating endpoints (artifact PUT, pending-write PUT, handoff-ack, NLE, VO upload, etc.) return **HTTP 409** `{"error": "run_busy"}` when `RunDirectoryLock` or the in-process job lock is held.

**Global exception handler:** Unhandled exceptions and **HTTP 5xx** on routes under `/api/runs/{run_id}/…` append one line to that run’s `gui_log.jsonl` (`stage: api`, `level: error`, message `API {status}: …`, `detail` with path/method/error_class/traceback). Client **4xx** (404 run, 400 validation, 409 busy) are not logged. Handler registered in `create_app()` (`server.py`).

When `journey_ui.require_write_approval_per_stage` is `true`, stage outputs land in `.pending_writes/<stage_id>/` until `POST …/approve`. Reuse copies use the same staging path when approval is enabled.

**Log handoff:** On stage completion, `gui_log.jsonl` may include `detail` JSON with `handoff: [paths…]` and optional `audit_path` for LLM `stage_runs` audit files.

**MMAudio sound-design stages (`mmaudio_sfx` / `REMOVED_mmaudio_flow2`):** local MMAudio text-to-audio per asset per unique SDP `asset_id` (variant `large_44k_v2` default, `force_instrumental`: true by default); canonical WAVs at `sound_design/assets/{asset_id}.wav` (mirrored under `flow_*_*/sfx/`). `music_length_ms` is derived from plan `duration_seconds` (not operator-edited craft rows); outputs shorter than 3 s are trimmed after generation. Listen via **`GET …/audio?path=sound_design/assets/{asset_id}.wav`**.

**Mix stages (`mix` / `REMOVED_mix_flow2`):** canonical pipeline ids after BUILD-066 (VO + SFX assembly). Legacy ids `mux_flow1` / `mux_flow2` still accepted for `mode: stage` single runs. v1 `podcast_sfx_brief` / `sfx_brief` are not in default `DELIVERY_ORDER` / `REMOVED_FLOW2_ORDER`.

### `FlowBody`

| Field | Type | Notes |
|-------|------|-------|
| `flow` | string | **`flow1`** \| **`flow2`** \| **`flow3`** (`FlowBody` pattern in `server.py`) |

### `PendingWriteContentBody`

| Field | Type | Notes |
|-------|------|-------|
| `path` | string | Relative path under run (same as final artifact path) |
| `data` | any | Full JSON document (for `.json` paths) |
| `text` | string | Plain text (for `.md`, `.txt`) |

Exactly one of `data` or `text` required.

### `StageReuseBody`

| Field | Type | Notes |
|-------|------|-------|
| `action` | string | `accept` \| `decline` |
| `source_run_id` | string \| null | Required when `action` is `accept` |

### `PrecleanOfferBody`

| Field | Type | Notes |
|-------|------|-------|
| `checkpoint` | string | One of `before_ingest`, `g1_vo_pickup` |
| `action` | string | `offer` \| `accept` \| `dismiss` |
| `scope` | string \| null | Optional override: `full_source` \| `vo_pickup` \| `normalized_rebuild` |

### `SfxPromptApproveBody`

| Field | Type | Notes |
|-------|------|-------|
| `approved_by` | string \| null | Optional reviewer identity; defaults to `operator` |

### `ArtifactBody`

| Field | Type | Notes |
|-------|------|-------|
| `path` | string | Relative JSON path under run |
| `data` | any | Full JSON document to write |
| `invalidate_from` | string \| null | If set, `runner.invalidate_from(run_id, …)` after save |

### `ResetBody`

| Field | Type | Notes |
|-------|------|-------|
| `from_stage` | string \| null | Invalidate markers from this stage (exclusive of mutual exclusivity with new input) |
| `new_input_audio_path` | string \| null | If set: re-init `run_meta`, clear pipeline markers from first stage of each order |

Exactly one of `from_stage` or `new_input_audio_path` must be provided — else **400**.

### `NleBody` / `NleSegmentBody` / `SplitBody`

- **NleBody:** `{ "data": { … full NLE document … } }`
- **NleSegmentBody:** `{ "segment_id": "…", "patch": { … } }` — merged into `segment_overrides[segment_id]`
- **SplitBody:** `{ "segment_id": "…", "at_ms": <int> }`

### `LogBody`

| Field | Type | Default |
|-------|------|---------|
| `message` | string | — |
| `level` | string | `"info"` — one of **`info`**, **`success`**, **`warning`**, **`error`**, **`action`** (GUI milestone / operator step; same append path as `RunContext.log()`) |
| `stage` | string \| null | — |

Levels are stored verbatim in `gui_log.jsonl`; the Logs tab filter matches `level` client-side.

### `TranscriptChunkBody`

| Field | Type | Default |
|-------|------|---------|
| `text` | string | — |
| `reviewed` | bool | `true` |

### `TranscriptReviewCompleteBody`

| Field | Type | Default |
|-------|------|---------|
| `accept_unreviewed` | bool | `false` — if `true`, allows complete with pending chunks |

### `AnalysisProfileBody`

| Field | Type | Notes |
|-------|------|-------|
| `data` | object | Full `analysis_state`-compatible document |
| `operator_verified` | bool \| null | If non-null, updates verification flag |
| `invalidate_from` | string \| null | Optional pipeline invalidation after save |

### `InvestigationPatchBody`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `status` | string | `"resolved"` | Written to matching `items[].status` in `understanding/investigation_queue.json` |

### Transcript review `GET` response

| Key | When |
|-----|------|
| `ready` | `false` if no `transcript/review_queue.json` |
| `ready` | `true` if queue exists |
| `complete` | Whether `.stage_done/transcript_review` exists |
| `chunks` | From `review_queue.json` |
| `pending_count` / `chunk_count` / `low_confidence_threshold` | When `ready` |

### Transcript dock word edits

**`GET /api/runs/{run_id}/transcript`** — word-level karaoke editor state.

| Key | Notes |
|-----|-------|
| `ready` | `false` until `transcript/full.json` exists |
| `words[]` | `{ text, start_ms, end_ms, speaker_id?, confidence?, corrected? }` |
| `duration_ms` | From ingest audio |
| `audio_path` | Typically `ingest/normalized.wav` for synced playback |
| `low_confidence_threshold` | Default **0.85** — UI flags words below this |
| `review_applied_at` | Set after G0 complete |

**`PATCH /api/runs/{run_id}/transcript/words`** — body **TranscriptWordsPatchBody**:

| Field | Type | Notes |
|-------|------|-------|
| `updates` | `TranscriptWordPatch[]` | One or more word edits |

**TranscriptWordPatch:**

| Field | Type | Notes |
|-------|------|-------|
| `index` | int | Zero-based index into `full.json` `words[]` |
| `text` | string | Replacement token (trimmed server-side) |

**Response:** `{ ok, updated_count, words, text }` — writes `transcript/full.json` immediately, sets `words[i].corrected = true`, rebuilds `full.text`, persists `operator/transcript_corrected.*` (`source: dock_edit`).

The GUI **Fix similar words** panel is a client-side fuzzy matcher over `words[]` that batches multiple `updates` through this endpoint (no separate fuzzy API). See [transcript-review.md](../pipeline/transcription/transcript-review.md#fuzzy-find-and-replace-similar-words).

---

## VO upload

`POST /api/runs/{run_id}/vo/{line_id}` — **`multipart/form-data`** with a single file field **`file`** (raw bytes stored as `vo_pickup/{line_id}.wav`).

---

## Acoustic profile

| Method | Path | Body | Response |
|--------|------|------|----------|
| `POST` | `/api/runs/{run_id}/recompute-acoustic-profile` | — | `ok`, `profile`, `derived_from`, optional `invalidated_from` when `pace_class` changes |
| `GET` | `/api/runs/{run_id}/interview-spine` | query: `offset`, `limit` | Paginated spine manifest + windows |
| `POST` | `/api/runs/{run_id}/recompute-interview-spine` | — | `ok`, `spine`, `derived_from`, window counts |
| `POST` | `/api/runs/{run_id}/interview-spine/query` | `{ "query": "…", "top_k": 5 }` | `{ "ok", "query", "hits" }` CLAP or text fallback |
| `GET` | `/api/runs/{run_id}/coherence-report` | — | Full `understanding/coherence_report.json`; when missing, **200** inactive stub (`gate.activated: false`) |
| `POST` | `/api/runs/{run_id}/recompute-coherence` | `{ "phase": "post_reanchor" }` optional | `ok`, `report` — rebuild from spine + brief |
| `PATCH` | `/api/runs/{run_id}/acoustic-profile/overrides` | **AcousticProfileOverridesBody** | `ok`, `operator_overrides`, `effective` (`pace_class`, `underscore_policy`), `profile` |

**`AcousticProfileOverridesBody`:** `{ overrides: {…}, invalidate_from?: string }` — merges operator overrides into `understanding/source_acoustic_profile.json`; optional pipeline invalidation after save. Logs `acoustic_profile_override_saved`.

`POST …/recompute-acoustic-profile` re-runs deterministic DSP from ingest/transcript. Logs `acoustic_profile_recomputed` to `gui_log.jsonl`.

`SonicContextPanel` reads `understanding/sonic_context.json` through the generic artifact route (`GET /api/runs/{run_id}/artifact?path=understanding/sonic_context.json`).

---

## Run-scoped mutation guards

Disk-writing routes under `/api/runs/{run_id}/` acquire `operator_guard` (via `_guarded_run` in `server.py`) before mutating run state. Concurrent background jobs or another operator mutation returns **HTTP 409**:

```json
{ "detail": { "error": "run_busy", "message": "…" } }
```

The GUI `api()` client retries 409 briefly; persistent busy states surface as `ApiError.runBusy`. Registry: `src/interview_mux/web/route_guard_registry.py`, CI audit: `tools/audit_route_guards.py`.

Read-only routes (e.g. `POST …/interview-spine/query`) are exempt. `POST …/execute` and `POST …/fill-artifact-gaps` use the same guard at start.

---

## `GET /api/runs/{run_id}` — `stages[]` entries

Each stage object includes at least: `id`, `title`, `description`, `phase`, `artifacts`, `editable`, `audio_outputs`, `status` (`locked` \| `pending` \| `done` \| `action_required`), and when applicable:

| Field | Description |
|-------|-------------|
| `artifacts_present` | Paths that exist on disk (legacy checklist) |
| `artifacts_status` | Per artifact path: `pending` (missing), `partial` (exists but schema or semantic gaps), `complete` |
| `outputs_view` | Rich checklist rows including `sufficiency_status` (`ok` \| `blocking` \| `unknown`) |
| `audio_outputs_present` | Playable WAV paths via `GET /api/runs/{run_id}/audio` |

`job.sufficiency_blocking` counts blocking sufficiency findings across done stages when sufficiency is enabled.

Completeness rules and validation: [artifact-generation-and-validation.md](../cross-cutting/artifact-generation-and-validation.md).

Stage ids match `src/interview_mux/web/stages.py` (`STAGE_BY_ID`).

---

## Delivery brief (adaptive policy)

| Method | Path | Body | Notes |
|--------|------|------|-------|
| `GET` | `/api/runs/{run_id}/delivery-brief` | — | `{ brief }` from `understanding/delivery_brief.json` (or `null`) |
| `PATCH` | `/api/runs/{run_id}/delivery-brief` | operator override fields (`target_duration_sec`, `question_budget`, `chapter_budget`, …) | Rebuilds brief with overrides; logs `gui.delivery_brief.save` |
| `POST` | `/api/runs/{run_id}/delivery-brief/rebuild` | — | Deterministic rebuild preserving prior overrides unless cleared; logs `gui.delivery_brief.reset` |

Also mirrored on `GET /api/runs/{run_id}` as `delivery_brief`. See [delivery-quality-preservation-matrix.md](../cross-cutting/delivery-quality-preservation-matrix.md).

---

## OpenAPI / machine discovery

FastAPI exposes interactive docs when the server runs:

- **`/docs`** — Swagger UI  
- **`/redoc`** — ReDoc  

Use these for live schema inspection if this markdown drifts from code.

---

## Related

- [gui-surface-map.md](./gui-surface-map.md)
- [stage-execution-reuse.md](./stage-execution-reuse.md)
- [operator-gates.md](./operator-gates.md)
- [transcript-review.md](../pipeline/transcription/transcript-review.md)
- [artifact-layout.md](../cross-cutting/artifact-layout.md)
