# HTTP API reference (FastAPI)

**Stack pins:** `fastapi`, `uvicorn`, `pydantic` — [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md). Use **Context7** at those versions when changing `server.py`.

Authoritative route list for **`interview_mux` web server** (`src/interview_mux/web/server.py`). The single-page GUI under `/` is static files; all JSON state goes through **`/api/*`**.

**Companion:** [gui-surface-map.md](./gui-surface-map.md) maps UI areas to these routes and on-disk artifacts.

---

## Base URL and static

| Item | Value |
|------|--------|
| Default port | From `config/app.defaults.json` → `web_port` (default **8765**) |
| API prefix | **`/api`** |
| Static UI | **`/`** — `StaticFiles` from `src/interview_mux/web/static/` when present |
| CORS | `allow_origins=["*"]` (dev-friendly) |

---

## Conventions

- **`{run_id}`** — Execution directory name (`exec_NNN_…` or legacy `run_NNN`). Unknown id → **404** `Run not found`.
- **Artifact paths** — Query/body paths must be **relative to run root**, no `..`, no leading `/` — else **400** `Invalid artifact path`.
- **JSON responses** — Unless noted, `application/json`. Audio routes return **`FileResponse`** with guessed `Content-Type`.

---

## Global routes

| Method | Path | Query | Body | Response | Errors |
|--------|------|-------|------|----------|--------|
| `GET` | `/api/health` | — | — | `{"status": "ok"}` | — |
| `GET` | `/api/config` | — | — | `assets_root`, `executions_root`, `data_root`, `web_port`, `repo_root` | — |
| `GET` | `/api/session` | — | — | `server`, `active` (run id + optional `selected_stage_id`); if active run valid: `log` (tail 200 entries), `run_summary` | Active run cleared if resolve fails |
| `PUT` | `/api/session/active` | — | **ActiveBody** | Result of `set_active_execution` | **404** if `run_id` not found |
| `GET` | `/api/assets` | `recursive` (bool, default `true`) | — | `assets_root`, `files[]` with `path`, `name`, `size_bytes`, `modified_at` | — |

Lists discoverable **source** audio under `assets_root` (default `ASSETS/`). Skips top-level `executions` and `.gui`. Used by the GUI home **Input audio** panel — see [assets-and-executions.md](../cross-cutting/assets-and-executions.md).
| `GET` | `/api/runs` | — | — | `runs[]` — each includes `run_id`, `meta` summary fields, `progress`, `last_stage` when resolvable | Per-run errors swallowed → `progress: {0,0}` |
| `POST` | `/api/runs` | — | **CreateRunBody** | `run_id`, `run_dir`, `execution_number` | **404** if `input_audio_path` file missing |

### `CreateRunBody`

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `input_audio_path` | string | yes | Repo-relative path to source audio (typically from `GET /api/assets` → `files[].path`, e.g. `ASSETS/input/interview.wav`) |
| `run_id` | string \| null | no | If omitted, server allocates new `exec_*` id |

### `ActiveBody`

| Field | Type | Required |
|-------|------|----------|
| `run_id` | string | yes |
| `selected_stage_id` | string \| null | no |

---

## Per-run routes (`{run_id}`)

| Method | Path | Query | Body | Response | Errors |
|--------|------|-------|------|----------|--------|
| `GET` | `/api/runs/{run_id}` | — | — | `run_id`, `meta`, `selected_flow`, `transcript_review_*`, `g1_*`, `analysis_complete`, `job`, `stages[]`, `log_tail` | **404** |
| `GET` | `/api/runs/{run_id}/log` | `tail` (int, default **200**) | — | `entries[]` — each `ts`, `level`, `message`, optional `stage`, `detail` | **404** |
| `POST` | `/api/runs/{run_id}/log` | — | **LogBody** | `ok`, `entry` | **404** |
| `GET` | `/api/runs/{run_id}/timeline` | — | — | `duration_ms`, `segments`, `vo_lines`, `nle`, `normalized_audio` | **404** |
| `GET` | `/api/runs/{run_id}/nle` | — | — | NLE JSON object | **404** |
| `PUT` | `/api/runs/{run_id}/nle` | — | **NleBody** | `ok: true` | **404** |
| `PATCH` | `/api/runs/{run_id}/nle/segment` | — | **NleSegmentBody** | `ok`, `nle` | **404** |
| `POST` | `/api/runs/{run_id}/nle/split` | — | **SplitBody** | `ok`, `nle` | **404** |
| `GET` | `/api/runs/{run_id}/artifact` | `path` (string, **required**) | — | Parsed JSON or `{path, text}` for non-JSON | **404** artifact, **400** path |
| `PUT` | `/api/runs/{run_id}/artifact` | — | **ArtifactBody** | `ok`, `path` | **400** if not `.json`, **404** |
| `POST` | `/api/runs/{run_id}/flow` | — | **FlowBody** | `ok`, `selected_flow` | **404** |
| `POST` | `/api/runs/{run_id}/preclean-offer` | — | **PrecleanOfferBody** | `ok`, `changed`, `audio_preclean` | **400** invalid checkpoint/scope, **404** |
| `GET` | `/api/runs/{run_id}/elevenlabs-prompts` | — | — | `path`, `prompts[]` (one row per SDP `asset_id`; `duration_seconds` normalized from plan on craft persist), `review`, `review_required`, `can_generate` | **404** missing prompts artifact |
| `PUT` | `/api/runs/{run_id}/elevenlabs-prompts` | — | **ArtifactBody** (`path` must be `sound_design/elevenlabs_prompts.json`) | `ok`, `path`, `review` (approval reset on edit) | **400** invalid path/payload, **404** |
| `POST` | `/api/runs/{run_id}/elevenlabs-prompts/approve` | — | **ElevenLabsPromptApproveBody** | `ok`, `review`, `asset_ids`; logs `elevenlabs_prompts_approved` | **404** missing prompts artifact |
| `POST` | `/api/runs/{run_id}/elevenlabs-prompts/listen-result` | — | **ElevenLabsListenResultBody** (`asset_id`, `result`: `pass`\|`fail`, optional `note`) | `ok`, `entry`, `elevenlabs_listen_results[]`; appends `run_meta.elevenlabs_listen_results`; logs `elevenlabs_post_listen_pass` or `elevenlabs_post_listen_fail` | **400** invalid body |

**G1.5 (optional):** When `g1_5_require_prompt_approval` is true in merged config, `can_generate` is false until approve; `elevenlabs_sfx_flow*` stages raise at runtime if unapproved. Review UI is on stage `elevenlabs_prompt_craft` — see [gui-surface-map.md](./gui-surface-map.md#elevenlabs-operator-journey-sfx--g15).
| `POST` | `/api/runs/{run_id}/execute` | — | **ExecuteBody** | `ok`, `run_id`, `mode` (immediate ack; work runs in thread) | **409** job already running, **404** |
| `GET` | `/api/runs/{run_id}/job` | — | — | `gui_job.json` payload or `{status: idle, run_id}` | — |
| `GET` | `/api/runs/{run_id}/transcript-review` | — | — | See **Transcript review response** below | **404** |
| `PUT` | `/api/runs/{run_id}/transcript-review/{chunk_id}` | — | **TranscriptChunkBody** | From `save_chunk_correction` | **404** no queue |
| `POST` | `/api/runs/{run_id}/transcript-review/complete` | — | **TranscriptReviewCompleteBody** | `ok`, `transcript_review_clear` | **400** queue not ready or pending chunks |
| `GET` | `/api/runs/{run_id}/analysis-profile` | — | — | `analysis_state`, `investigation_queue`, `editable_paths`, `operator_verified`, `completion` | **404** |
| `PUT` | `/api/runs/{run_id}/analysis-profile` | — | **AnalysisProfileBody** | `ok`, `operator_verified`, `completion` | **404** |
| `POST` | `/api/runs/{run_id}/analysis-profile/verify` | — | — | `ok`, `operator_verified: true` | **404** |
| `POST` | `/api/runs/{run_id}/vo/{line_id}` | — | **multipart** field `file` (WAV) | `ok`, `path`, `g1_missing` | **404** |
| `POST` | `/api/runs/{run_id}/reset` | — | **ResetBody** | `ok: true` | **400** missing both fields, **404** audio |
| `GET` | `/api/runs/{run_id}/audio` | `path` (required) | — | Binary file | **404**, **400** |
| `GET` | `/api/runs/{run_id}/source-audio` | — | — | Original input from `run_meta.json` | **404** |

### `ExecuteBody`

| Field | Type | Notes |
|-------|------|--------|
| `mode` | string | **`stage`** \| **`analysis`** \| **`flow1`** \| **`flow2`** \| **`flow3`** |
| `stage` | string \| null | For `mode=stage`: stage id to run. Special: `transcript_review` triggers sign-off helper (see code). |
| `from_stage` | string \| null | If set and differs from `stage` for single-stage runs, **invalidates** from `from_stage` first. For `analysis` / `flow*`, passed as pipeline `from_stage`. |

**Implementation:** `runner.start` returns immediately; poll **`GET …/job`** and **`GET …/log`**. Job `status` values include `running`, `complete`, `error`, `gate`, `idle`.

**ElevenLabs SFX stages (`elevenlabs_sfx_flow1` / `elevenlabs_sfx_flow2`):** one REST `POST /v1/sound-generation` per unique SDP `asset_id`; canonical WAVs at `sound_design/assets/{asset_id}.wav` (mirrored under `flow_*_*/sfx/`). `duration_seconds` sent to ElevenLabs always comes from the plan asset, not operator-edited craft rows. Listen via **`GET …/audio?path=sound_design/assets/{asset_id}.wav`**.

**Mix stages (`mix_flow1` / `mix_flow2`):** canonical pipeline ids after BUILD-066 (VO + SFX assembly). Legacy ids `mux_flow1` / `mux_flow2` still accepted for `mode: stage` single runs. v1 `podcast_sfx_brief` / `sfx_brief` are not in default `FLOW1_ORDER` / `FLOW2_ORDER`.

### `FlowBody`

| Field | Type | Notes |
|-------|------|-------|
| `flow` | string | **`flow1`** \| **`flow2`** \| **`flow3`** (`FlowBody` pattern in `server.py`) |

### `PrecleanOfferBody`

| Field | Type | Notes |
|-------|------|-------|
| `checkpoint` | string | One of `before_ingest`, `after_g0`, `after_profile_or_segmentation`, `g1_vo_pickup`, `before_flow_mix`, `before_master_export` |
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

---

## VO upload

`POST /api/runs/{run_id}/vo/{line_id}` — **`multipart/form-data`** with a single file field **`file`** (raw bytes stored as `vo_pickup/{line_id}.wav`).

---

## `GET /api/runs/{run_id}` — `stages[]` entries

Each stage object includes at least: `id`, `title`, `description`, `phase`, `artifacts`, `editable`, `audio_outputs`, `status` (`locked` \| `pending` \| `done` \| `action_required`), and when applicable `artifacts_present` + `audio_outputs_present` (present files that can be played via `GET /api/runs/{run_id}/audio`).

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
- [operator-gates.md](./operator-gates.md)
- [transcript-review.md](../pipeline/transcription/transcript-review.md)
- [artifact-layout.md](../cross-cutting/artifact-layout.md)
