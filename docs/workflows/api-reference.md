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
| `GET` | `/api/config` | — | — | `assets_root`, `executions_root`, `data_root`, `web_port`, `repo_root`, `api_consent_persist` | — |
| `GET` | `/api/session/api-consent` | — | — | `providers[]` (id, label, description, cost_hint), `grants` (persisted under `ASSETS/.gui/api_consent.json`) | — |
| `POST` | `/api/session/api-consent` | — | **ApiConsentBody** `{provider, granted}` | `ok`, `provider`, `granted`, `grants` | — |
| `GET` | `/api/session` | — | — | `server`, `active` (run id + optional `selected_stage_id`); if active run valid: `log` (tail 200 entries), `run_summary` | Active run cleared if resolve fails |
| `PUT` | `/api/session/active` | — | **ActiveBody** | Result of `set_active_execution`, or `{ok, active: null}` when `run_id` omitted/null | **404** if `run_id` set but not found |
| `DELETE` | `/api/session/active` | — | — | `{ok: true, active: null}` — clears active execution | — |
| `GET` | `/api/assets` | `recursive` (bool, default `true`) | — | `assets_root`, `files[]` with `path`, `name`, `size_bytes`, `modified_at` | — |

Lists discoverable **source** audio under `assets_root` (default `ASSETS/`). Skips top-level `executions` and `.gui`. Used by the GUI home **Input audio** panel — see [assets-and-executions.md](../cross-cutting/assets-and-executions.md).
| `GET` | `/api/runs` | — | — | `runs[]` — each includes `run_id`, `source_audio_hash`, `source_audio_hash_short`, summary fields, `progress` (`done`/`total`), `last_stage`, `last_log` (latest `gui_log.jsonl` entry) | Per-run errors swallowed → `progress: {0,0}` |
| `POST` | `/api/runs` | — | **CreateRunBody** | `run_id`, `run_dir`, `execution_number`, `input_audio_path`, `source_audio_hash`, `source_audio_hash_short` | **404** if `input_audio_path` file missing |

### `CreateRunBody`

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `input_audio_path` | string | yes | Repo-relative path to source audio (typically from `GET /api/assets` → `files[].path`, e.g. `ASSETS/input/interview.wav`) |
| `run_id` | string \| null | no | If omitted, server allocates new `exec_*` id |

### `ActiveBody`

| Field | Type | Required |
|-------|------|----------|
| `run_id` | string \| null | no — omit or null to clear active execution |
| `selected_stage_id` | string \| null | no |

---

## Per-run routes (`{run_id}`)

| Method | Path | Query | Body | Response | Errors |
|--------|------|-------|------|----------|--------|
| `GET` | `/api/runs/{run_id}/summary` | — | — | Run summary + `progress`, `last_log`, `handoff_ack` map | **404** |
| `GET` | `/api/runs/{run_id}` | — | — | `run_id`, `meta`, `handoff_ack`, `elevenlabs_generated_assets[]`, `selected_flow`, `transcript_review_*`, `g1_*`, `analysis_complete`, `job`, `stages[]` (each may include `api_providers[]`), `log_tail` | **404** |
| `GET` | `/api/runs/{run_id}/log` | `tail` (int, default **200**) | — | `entries[]` — each `ts`, `level`, `message`, optional `stage`, `detail` | **404** |
| `POST` | `/api/runs/{run_id}/log` | — | **LogBody** | `ok`, `entry` | **404** |
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
| `POST` | `/api/runs/{run_id}/flow` | — | **FlowBody** | `ok`, `selected_flow` | **404** |
| `POST` | `/api/runs/{run_id}/preclean-offer` | — | **PrecleanOfferBody** | `ok`, `changed`, `audio_preclean` | **400** invalid checkpoint/scope, **404** |
| `GET` | `/api/runs/{run_id}/stages/{stage_id}/reuse-offers` | — | — | `eligible`, `blocking`, `candidates[]` (hash fields, `paths[]`, `same_source_audio`), `pending_decision`, `current_source_audio_hash_short` | **404** unknown stage |
| `POST` | `/api/runs/{run_id}/stages/{stage_id}/reuse` | — | **StageReuseBody** `{action, source_run_id?}` | `ok`, `stage_reuse`, `copied[]` on accept | **400** ineligible source, **404** |
| `GET` | `/api/runs/{run_id}/pending-writes` | — | — | `stages[]` with `{stage_id, paths[]}` | **404** |
| `GET` | `/api/runs/{run_id}/pending-writes/{stage_id}` | — | — | `{stage_id, paths[]}` | **404** if none staged |
| `GET` | `/api/runs/{run_id}/pending-writes/{stage_id}/content` | `path` (required) | — | JSON object, or `{text}` for `.md`/`.txt` | **404** |
| `PUT` | `/api/runs/{run_id}/pending-writes/{stage_id}/content` | — | **PendingWriteContentBody** `{path, data? \| text?}` | `ok`, `path` | **400** |
| `POST` | `/api/runs/{run_id}/pending-writes/{stage_id}/approve` | — | — | `ok`, `flushed[]`, `stage_id` — copies staging → final paths, marks stage done | **404** if none staged |
| `POST` | `/api/runs/{run_id}/pending-writes/{stage_id}/discard` | — | — | `ok`, `stage_id` — clears staging, invalidates from stage | **404** |
| `GET` | `/api/runs/{run_id}/elevenlabs-prompts` | — | — | `path`, `prompts[]`, `review`, `review_required`, `can_generate`, `listen_results[]`, `generated_assets[]` (`asset_id`, `path` under `sound_design/assets/`) | **404** missing prompts artifact |
| `PUT` | `/api/runs/{run_id}/elevenlabs-prompts` | — | **ArtifactBody** (`path` must be `sound_design/elevenlabs_prompts.json`) | `ok`, `path`, `review` (approval reset on edit) | **400** invalid path/payload, **404** |
| `POST` | `/api/runs/{run_id}/elevenlabs-prompts/approve` | — | **ElevenLabsPromptApproveBody** | `ok`, `review`, `asset_ids`; logs `elevenlabs_prompts_approved` | **404** missing prompts artifact |
| `POST` | `/api/runs/{run_id}/elevenlabs-prompts/listen-result` | — | **ElevenLabsListenResultBody** (`asset_id`, `result`: `pass`\|`fail`, optional `note`) | `ok`, `entry`, `elevenlabs_listen_results[]`; appends `run_meta.elevenlabs_listen_results`; logs `elevenlabs_post_listen_pass` or `elevenlabs_post_listen_fail` | **400** invalid body |

**G1.5 (optional):** When `g1_5_require_prompt_approval` is true in merged config, `can_generate` is false until approve; `elevenlabs_sfx_flow*` stages raise at runtime if unapproved. Review UI is on stage `elevenlabs_prompt_craft`. **Post-listen** Pass/Fail is advisory (`POST …/listen-result`); panels on `elevenlabs_prompt_craft` and `elevenlabs_sfx_flow*` — see [gui-surface-map.md](./gui-surface-map.md#elevenlabs-operator-journey-sfx--g15).
| `POST` | `/api/runs/{run_id}/execute` | — | **ExecuteBody** | `ok`, `run_id`, `mode` (immediate ack; work runs in thread); or `ok: false`, `needs_api_consent` if providers not granted | **409** job already running, **404** |
| `GET` | `/api/runs/{run_id}/job` | — | — | `gui_job.json` payload or `{status: idle, run_id}` | — |
| `GET` | `/api/runs/{run_id}/transcript-review` | — | — | See **Transcript review response** below | **404** |
| `PUT` | `/api/runs/{run_id}/transcript-review/{chunk_id}` | — | **TranscriptChunkBody** | From `save_chunk_correction` | **404** no queue |
| `POST` | `/api/runs/{run_id}/transcript-review/complete` | — | **TranscriptReviewCompleteBody** | `ok`, `transcript_review_clear` | **400** queue not ready or pending chunks |
| `GET` | `/api/runs/{run_id}/analysis-profile` | — | — | `analysis_state`, `investigation_queue`, `editable_paths`, `operator_verified`, `completion` | **404** |
| `PUT` | `/api/runs/{run_id}/analysis-profile` | — | **AnalysisProfileBody** | `ok`, `operator_verified`, `completion` | **404** |
| `POST` | `/api/runs/{run_id}/analysis-profile/verify` | — | — | `ok`, `operator_verified: true` | **404** |
| `POST` | `/api/runs/{run_id}/vo/{line_id}` | — | **multipart** field `file` (WAV) | `ok`, `path`, `g1_missing` | **404** |
| `POST` | `/api/runs/{run_id}/reset` | — | **ResetBody** | `ok: true` | **400** missing both fields, **404** audio |
| `GET` | `/api/runs/{run_id}/audio` | `path` (required); optional `pending=1`, `pending_stage=<stage_id>` | — | Binary file (final path, or staged copy when pending query set) | **404**, **400** |
| `GET` | `/api/runs/{run_id}/source-audio` | — | — | Original input from `run_meta.json` | **404** |

### `ExecuteBody`

| Field | Type | Notes |
|-------|------|--------|
| `mode` | string | **`stage`** \| **`analysis`** \| **`analysis_until_g0`** \| **`flow1`** \| **`flow1_until_preview`** \| **`flow1_polish`** \| **`flow2`** \| **`flow3`** \| **`nle_apply`** |
| `nle_full_refresh` | bool | Optional for **`nle_apply`** — also run `transitions` and `edl_narrative_audit` before EDL rebuild (legacy; prefer `nle_apply_mode: full_refresh`) |
| `nle_apply_mode` | string | Optional for **`nle_apply`**: `trim_only` (EDL + preview only), `structural` (default — ranking when structural edits), `full_refresh` (structural + transitions + EDL narrative audit) |
| `stage` | string \| null | For `mode=stage`: stage id to run. Special: `transcript_review` triggers sign-off helper (see code). |
| `from_stage` | string \| null | If set and differs from `stage` for single-stage runs, **invalidates** from `from_stage` first. For `analysis` / `flow*`, passed as pipeline `from_stage`. |
| `api_consents` | object \| null | Map `openai` \| `aws` \| `elevenlabs` → `true` when operator granted session access (merged with `ASSETS/.gui/api_consent.json`) |

**Implementation:** `runner.start` returns immediately; poll **`GET …/job`** and **`GET …/log`**. Job `status` values include `running`, `running_with_warnings`, `complete`, `error`, `gate`, `needs_operator`, `awaiting_write_approval`, `idle`. Additional job fields: `needs_stage_reuse`, `reuse_candidates[]`, `awaiting_write_approval`, `pending_write_stage`.

Stage `status` in **`GET /api/runs/{run_id}`** may be `awaiting_write_approval` when `.pending_writes/<stage_id>/` has unapproved files.

Mutating endpoints (artifact PUT, pending-write PUT, handoff-ack, NLE, VO upload, etc.) return **HTTP 409** `{"error": "run_busy"}` when `RunDirectoryLock` or the in-process job lock is held.

When `journey_ui.require_write_approval_per_stage` is `true`, stage outputs land in `.pending_writes/<stage_id>/` until `POST …/approve`. Reuse copies use the same staging path when approval is enabled.

**Log handoff:** On stage completion, `gui_log.jsonl` may include `detail` JSON with `handoff: [paths…]` and optional `audit_path` for LLM `stage_runs` audit files.

**ElevenLabs sound-design stages (`elevenlabs_sfx_flow1` / `elevenlabs_sfx_flow2`):** one REST `POST /v1/music` per unique SDP `asset_id` (`model_id`: `music_v2`, `force_instrumental`: true by default); canonical WAVs at `sound_design/assets/{asset_id}.wav` (mirrored under `flow_*_*/sfx/`). `music_length_ms` is derived from plan `duration_seconds` (not operator-edited craft rows); outputs shorter than 3 s are trimmed after generation. Listen via **`GET …/audio?path=sound_design/assets/{asset_id}.wav`**.

**Mix stages (`mix_flow1` / `mix_flow2`):** canonical pipeline ids after BUILD-066 (VO + SFX assembly). Legacy ids `mux_flow1` / `mux_flow2` still accepted for `mode: stage` single runs. v1 `podcast_sfx_brief` / `sfx_brief` are not in default `FLOW1_ORDER` / `FLOW2_ORDER`.

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

### `ElevenLabsPromptApproveBody`

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
| `level` | string | `"info"` |
| `stage` | string \| null | — |

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

## Acoustic profile recompute

`POST /api/runs/{run_id}/recompute-acoustic-profile` — re-runs `source_acoustic_profile` from current ingest/transcript. Response: `{ "profile": {…}, "derived_from": {…} }`. Logs `acoustic_profile_recomputed` to `gui_log.jsonl`.

---

## `GET /api/runs/{run_id}` — `stages[]` entries

Each stage object includes at least: `id`, `title`, `description`, `phase`, `artifacts`, `editable`, `audio_outputs`, `status` (`locked` \| `pending` \| `done` \| `action_required`), and when applicable:

| Field | Description |
|-------|-------------|
| `artifacts_present` | Paths that exist on disk (legacy checklist) |
| `artifacts_status` | Per artifact path: `pending` (missing), `partial` (exists but schema or semantic gaps), `complete` |
| `audio_outputs_present` | Playable WAV paths via `GET /api/runs/{run_id}/audio` |

Completeness rules and validation: [artifact-generation-and-validation.md](../cross-cutting/artifact-generation-and-validation.md).

Stage ids match `src/interview_mux/web/stages.py` (`STAGE_BY_ID`).

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
