# GUI surface map — panels, APIs, logs, artifacts

Single reference for **what the operator sees**, which **HTTP API** backs it, and which **artifacts** on disk are read or written. Source: `src/interview_mux/web/server.py`, `frontend/src/` (React + TypeScript GUI), `web/stages.py`, `session_log.py`, `web/runner.py`.

**Logging policy (do not duplicate elsewhere):** `.cursor/rules/interview-helper-mux.mdc` → **Centralized operator status and logs** — write operator-visible status only via `RunContext.log()` / `append_log` → `gui_log.jsonl`, and background execute state via `gui_job.json`.

**HTTP companion:** [api-reference.md](./api-reference.md) — method/path/body tables and common status codes. Stack pins: [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md).

**Convention:** `{run_id}` is the execution id (e.g. `exec_001_a1b2c3d4e5f6_20260523T120000Z`, legacy `exec_001_20260523T120000Z`, or `run_001`). Run root = that folder under `executions_root` or `data_root` — see [artifact-layout.md](../cross-cutting/artifact-layout.md).

**ASSETS-first flow:** Operators do not configure a WAV path in secrets for GUI use. Home screen **Input audio** lists files under `ASSETS/` (via `GET /api/assets`); **Previous executions** lists `ASSETS/executions/exec_*` for resume. Canonical spec: [assets-and-executions.md](../cross-cutting/assets-and-executions.md).

---

## Operator console layout (tabbed shell)

| Zone | Element | Behavior |
|------|---------|----------|
| Header | **`LiveStatusBar`** (sticky, all tabs) | Compact status surface: **Workflow phase** chips (with attention dots), primary CTA uses `journey.next_action` / contextual checkpoint labels, error chip, batch progress bar, compact preview-listen promo, Mute / Menu |
| Header | **Action** badge | Opens operator action modal when checkpoints/handoffs pending |
| Header | **Mute** / **Menu** | Mute attention sounds; **View full log**, **Clear session** |
| Tabs | **Start \| Executions \| Pipeline \| Logs** | Tab switch does **not** stop polling or clear `runId` |
| **Start** | Input audio list | Pick source WAV, start new execution → switches to Pipeline |
| **Executions** | Previous runs list | Resume any `exec_*`; active run highlighted; **Same audio** pill when hash matches active session; hash badge per run; refresh on tab focus |
| **Pipeline** | 3-column layout | **`PipelineStepList`** \| main pane (tool row + **`StageDetail`** / tools) \| **`ActivityLogPanel`** (Live / This step / All) |
| **Pipeline** | **`PipelineCommandCenter`** | Phase guidance banner, **Needs your attention** queue, preview-listen promo, read-only step context (no duplicate Run when LiveStatusBar owns CTA) |
| **Pipeline** | **Tool icon row** | Stage \| Story \| Timeline \| Profile \| Files \| Debug \| Volley |
| **Pipeline** | **`StageActivityStrip`** | Last 3 log lines for selected step + link to activity panel |
| **Logs** | Full log viewer | Filters (level, stage, search), tail size, detail expand, **Jump to active stream** |
| Footer | **`ActivityTeaser`** (non-Pipeline tabs) | One-line latest activity; click → Pipeline + expand activity log |
| Modals | `OperatorActionModal` | Full-screen duplicate of blocking gate UI — auto-open on `action_required`, `needs_stage_reuse`, or `awaiting_write_approval`; **`PendingActionBanner`** (Pipeline command center + non-Pipeline tabs) and **`StageActivityStrip`** CTA surface the same pending action inline; **`ReviewPanelControls`** toggles full-screen vs inline review. Reuse and write-approval panels stay on `StageDetail` when modal closed. |
| Pipeline chrome | `JourneyShell` / `AudioQualityDrawer` | When `journey_ui.enabled`, collapsible **Audio quality** drawer polls deprecated `GET …/audio-quality`; pre-clean offers also appear inline via `PrecleanOfferCard` on matching stages |
| Modals | API consent / Confirm | Existing API consent; shared confirm dialog replaces `window.confirm` |

**Attention sound:** Short browser ping on new `level=action` log lines, job `gate` / `needs_operator`, and new `action_required` stages (unless muted).

**API consent:** GUI sends `api_consents` on every execute (assumes configured providers). Optional persist to `ASSETS/.gui/api_consent.json` via `POST /api/session/api-consent` for cross-relaunch convenience. Backend `runner.start` can reject execute when required providers are not granted (`job.status: needs_operator`).

**Session persistence:** `ASSETS/.gui/active_execution.json` stores `run_id`, `selected_stage_id`, `active_tab`, `pipeline_sub_tab`, `activity_log_tab`, `activity_log_collapsed`. Browser refresh and `./scripts/run.sh` restart (default) restore the last operator view via `GET /api/session` → `openRun`. Stale `gui_job.json` with `status: running` is reconciled to `interrupted` on server start — **`LiveStatusBar`** shows **Run interrupted**, not Idle.

**Job progress:** During batch executes, `gui_job.json` updates `current_stage`, `stage_index`, `stage_total`, `stages_planned` per stage. Frontend merges polled job into `run.job` every 1s while active.

**Terminology:** Job complete → **Step finished**; operator phase `complete` → **Record & choose**; stage done → **Done**.

**Clear session:** Header menu — stops job poll, clears UI state, and clears server active run (`DELETE /api/session/active` or `PUT` with `run_id: null`). **Resume server session** appears on empty Pipeline when server still has an active `exec_*`; **Retry load** when the run id is set but data failed to load.

**Stage reuse:** `StageReuseSection` + `StageReuseOfferCard` (`frontend/src/components/guidance/`) on Stage detail (hidden while action modal is open) and in the action modal. Single `useStageReuseOffers` hook fetches offers; server blocks execute when `journey_ui.enable_stage_reuse_offers` is true (default). **Reuse outputs** copies artifacts (through write staging when approval enabled); **Run fresh instead** declines then runs the stage. Hash-match banner when candidate shares `source_audio_hash` (normalized via `sourceHashShort` util).

**Write approval:** When `journey_ui.require_write_approval_per_stage` is true (default), `WriteApprovalPanel` lists staged files under `.pending_writes/<stage>/`. Preview JSON/text, listen to staged WAV (`GET …/audio?pending=1&pending_stage=…`), edit staging, then **Save & continue** (`POST …/approve`) or **Discard & re-run** (`POST …/discard`). Job status `awaiting_write_approval` until resolved.

**Flow intent:** Optional at Start (`flow_intent` in `run_meta`); at G2 **Use planned choice** confirms intent without auto-running until clicked.

---

## Start tab (no active run required)

| User-visible | API | Log / session | Artifact / disk |
|--------------|-----|---------------|-----------------|
| **Input audio** list + Refresh | `GET /api/assets` | — | Scans `ASSETS/`; skips `executions/`, `.gui/` |
| Start execution on a file | `POST /api/runs` body `{ input_audio_path }` | `gui_log.jsonl` (`setup`) on new run | Creates `ASSETS/executions/exec_NNN_…/`, `run_meta.json` |

After create, UI switches to **Pipeline → Stage** (`GET /api/runs/{id}`).

---

## Executions tab

| User-visible | API | Log / session | Artifact / disk |
|--------------|-----|---------------|-----------------|
| **Previous executions** list + Refresh | `GET /api/runs` | `last_log` tail per run | Summaries + `progress` %, `source_audio_hash_short`; **Same audio** when hash matches active session |
| Resume execution | `PUT /api/session/active` `{ run_id }` | `ASSETS/.gui/active_execution.json` | Reopens existing `exec_*` workspace; switches to Pipeline |

Browsing executions while another run is active does **not** stop job/log polling for the current session until the operator resumes a different run or clears the session.

---

## Pipeline tab (sub-tabs)

| Sub-tab / pane | Component | Content | When visible |
|----------------|-----------|---------|--------------|
| **Step detail** (default) | `StageDetail` | Title, `StageGuidancePanel`, **Previous execution reuse** (`StageReuseSection`), **Review outputs before saving** (`WriteApprovalPanel`), **Your action** checkpoint (`GateActions` inline), artifact checklist, **LLM routing** panel (`GET …/llm-routing` for LLM stages), transcript dock on transcribe/review stages | Always when `run_id` set |
| **Story board** | `StoryBoardPanel` | Themes, investigations (`GET …/story-board`; `PATCH …/investigation-queue/{id}`), profile verify CTA | When analysis workspace exists |
| **Timeline** | `NlePanel` | Mouse-first NLE: smart actions, review queue, filters, undo history, transport, transcript trim, assembly A/B preview | After segment classification |
| **Profile JSON** | `ProfilePanel` | Analysis profile form | When `profile_ready_for_review` or profile verified |
| **Files** | `ArtifactEditor` | JSON / text artifact editor (Zod pre-save for registered paths) | When stage has editable artifacts |
| **Debug** | `LlmCallsPanel` | LLM call record index/editor + routing summary tab (`GET …/llm-calls`, `GET …/llm-routing`) | Power-user audit path |
| **Volley** | `VolleyMemoryPanel` | Volley Q&A memory index — view/edit/invalidate entries, rebuild from disk (`GET/PUT/POST …/context-index/*`) | Operator steering of prior context |

**Gate rendering:** `GateActions` mounts **inline** on `StageDetail` (checkpoint inset when `action_required` / handoff pending; always for non-blocking panels like `AcousticProfilePanel`, `PlacementAdjustmentsPanel`). The same `GateActions` tree also mounts in `OperatorActionModal` for full-screen review. Blocking G0/G0.5 gates show inline first; modal is optional via **Review in full-screen panel**.

### Sonic context panel (`SonicContextPanel`)

| Component | APIs | Artifacts |
|-----------|------|-----------|
| `SonicContextPanel` | `GET /api/runs/{run_id}/artifact?path=understanding/sonic_context.json` | `understanding/sonic_context.json` |

Shown on `source_acoustic_profile`, `sonic_context_build`, and `sound_design_palettes` stage detail as a compact scenario/tag provenance view.

### G0 transcript review (`TranscriptReviewPanel`)

| Component | File | APIs | Operator actions |
|-----------|------|------|------------------|
| Chunk navigator + clip audio + bulk textarea | `TranscriptReviewPanel` | `GET/PUT …/transcript-review`, `POST …/complete` | Previous/Next clip, **Save chunk**, **Complete transcript review** |
| Synced word-level dock | `TranscriptDockViewer` | `GET …/transcript`, `PATCH …/transcript/words` | Click seek, double-click edit, debounced save |
| Fuzzy similar-word panel | `FuzzyReplacePopover` | *(client)* → batch `PATCH …/transcript/words` | Match strictness 80–100%, jump to match, **Replace N words** |

Inline on `StageDetail` when `transcript_review` is `action_required`; also in `OperatorActionModal`. Transcript dock also on **Transcribe** / **Transcript review build** without the chunk navigator.

### G0.5 disfluency review (`DisfluencyReviewPanel`)

| Component | APIs | Artifacts |
|-----------|------|-----------|
| `DisfluencyReviewPanel` | `GET/PUT …/disfluency-review`, `POST …/disfluency-review/complete`, `PATCH …/disfluency-restore` | `transcript/disfluencies.json`, `transcript/disfluency_clips/`, `.stage_done/disfluency_review` |

Inline when `disfluency_review` is `action_required` (skipped when `disfluency_extract.enabled` is false). `DisfluencyRestorePanel` on `edl_flow1` / `assembly_preview` toggles per-run restore.

---

## Logs tab

| Control | Behavior |
|---------|----------|
| Level / stage filters | Client-side filter on fetched tail |
| Search | Text match on message, stage, detail |
| Tail size | 200 / 500 / all fetched (poll fetches up to 500 lines) |
| Auto-scroll | Default on; pauses when operator scrolls up |
| Detail expand | Per-row JSON / text detail |

**Where log data comes from:** `GET /api/runs/{id}/log?tail=…` polled every 2s while `runId` is set (all tabs).

---

## Log and job files (all runs)

| File | Purpose |
|------|---------|
| `gui_log.jsonl` | Append-only **operator-visible** messages (`ts`, `level`, `message`, optional `stage`, `detail`). Written via `RunContext.log()` and `POST /api/runs/{id}/log`. |
| `gui_job.json` | **Current / last background job** for pipeline execute (`status`, `mode`, `stage`, `message`, `updated_at`, `needs_stage_reuse`, `reuse_candidates`, `awaiting_write_approval`, `pending_write_stage`). |

**Where the UI shows them:** **Logs** tab and mini log strip load `GET /api/runs/{id}` → `log_tail` and poll `GET /api/runs/{id}/log?tail=…`; **job status** from `GET /api/runs/{id}/job` (nested under `job` on run fetch). Custom-run descriptive JSON writes trigger **handoff** only when artifacts are **complete** (`detail.handoff` / stage `handoff_paths`); batch runs pause until **Acknowledge & continue** (`POST …/handoff-ack`). Config: `journey_ui.require_handoff_between_stages`.

---

## Global (no `run_id`)

| User-visible / area | API | Log file | Artifact |
|----------------------|-----|----------|----------|
| Health | `GET /api/health` | — | — |
| Paths / port / feature flags | `GET /api/config` | — | `journey_ui`, `value_analysis_enabled`, `disfluency_*_enabled`, `llm_routing_stage_ids` |
| Active run + tail log | `GET /api/session` | `gui_log.jsonl` of active run | — |
| Set active run / UI chrome | `PUT /api/session/active` `{ run_id?, selected_stage_id?, active_tab?, pipeline_sub_tab? }` | — | `ASSETS/.gui/active_execution.json`; partial merge; null `run_id` clears |
| Clear active run | `DELETE /api/session/active` | — | removes active execution pointer |
| Browse input audio | `GET /api/assets` | — | scans `ASSETS/` (skips `executions`, `.gui`) — see [assets-and-executions.md](../cross-cutting/assets-and-executions.md) |
| List runs | `GET /api/runs` | — | summarizes each `run_meta.json` under `executions_root` |
| Create run from asset | `POST /api/runs` | `gui_log.jsonl` (`setup`) | creates `ASSETS/executions/exec_*`, `run_meta.json`, dirs |

---

## Per-run core

| User-visible (sidebar / title from `stages.py`) | Stage `id` | Primary APIs | Log file | Primary artifacts (read/write) |
|--------------------------------------------------|------------|--------------|----------|----------------------------------|
| Run overview + stage list + embedded log tail | *(all)* | `GET /api/runs/{id}`, `GET /api/runs/{id}/job` | `gui_log.jsonl`, `gui_job.json` | `run_meta.json`, `.stage_done/*`; `profile_ready_for_review`; per-stage `handoff_paths` (complete artifacts only) |
| Append user or script note to log | *(optional)* | `POST /api/runs/{id}/log` | `gui_log.jsonl` | — |
| Timeline (source + assembly views, waveform, trim, transcript strip) | *(view)* | `GET /api/runs/{id}/timeline`, `GET …/assembly-timeline`, `GET …/waveform`, `GET …/transcript` | — | `segments/manifest.json`, `segments/nle_edits.json`, `flow_1_master/edl.json`, `ingest/waveform_peaks.json`, `understanding/gap_report.json`, `vo_pickup/*.wav`, `ingest/normalized.wav` |
| NLE editor state | `nle` | `GET/PUT /api/runs/{id}/nle`, `PATCH …/nle/segment`, `POST …/nle/batch`, `POST …/nle/split`, `POST …/nle/snap-boundary` | `gui_log.jsonl` (`stage: nle`, cascade on **Apply timeline edits**) | `segments/nle_edits.json`; **`POST …/execute` `mode: nle_apply`** with optional `nle_apply_mode` (`trim_only` \| `structural` \| `full_refresh`) rebuilds selection (when structural), EDL, and `assembly_preview.wav` |
| JSON artifact editor | *(per path)* | `GET/PUT /api/runs/{id}/artifact?path=…` | `gui_log.jsonl` | Editable JSON; Zod pre-save + server `validate_artifact_write`; optional `invalidate_from` — [artifact-generation-and-validation.md](../cross-cutting/artifact-generation-and-validation.md) |
| Fill artifact gaps | *(partial checklist row)* | `POST /api/runs/{id}/fill-artifact-gaps` `{path}` | `gui_log.jsonl` | Re-runs producing LLM stage when artifact is partial |
| Play clip / source audio | *(audio)* | `GET /api/runs/{id}/audio?path=…`, `GET …/source-audio` | — | WAV under run or source path from `run_meta.json` |
| Run pipeline / stage | *(execute)* | `POST /api/runs/{id}/execute` body: `mode` = `stage` \| `analysis` \| `flow1` \| `flow2` \| `flow3` \| `nle_apply`, `stage`, `from_stage`, `until_stage`, `nle_full_refresh`, `nle_apply_mode` | `gui_log.jsonl`, `gui_job.json` | markers + stage outputs per `pipeline.py` orders |
| Preview listened milestone | `assembly_preview` polish CTA | `POST …/milestones/preview-listened` | `gui_log.jsonl` | `run_meta.journey.preview_listened_at` when `require_preview_listen` |
| Acoustic profile overrides | `source_acoustic_profile` | `PATCH …/acoustic-profile/overrides`, `POST …/recompute-acoustic-profile` | `gui_log.jsonl` | `understanding/source_acoustic_profile.json` → `operator_overrides` |
| Interview spine | `interview_spine_build` | `GET …/interview-spine`, `POST …/recompute-interview-spine`, `POST …/interview-spine/query` | Story Board summary · pipeline gate panel | `understanding/interview_spine.json` |
| Coherence (H-ORC-03) | hooks after `content_context`, `content_brief_reanchor`, `topic_coverage_audit` | `GET …/coherence-report`, `POST …/recompute-coherence` | Story Board **Coherence risks** panel | `understanding/coherence_report.json` |
| Placement QA hints | `mmaudio_sfx_flow*`, `mix_flow*` | *(read)* `sound_design/placement_adjustments.json` | — | `PlacementAdjustmentsPanel` after SFX/mix when `sound_design.placement_qa_enabled` |
| Reset / invalidate | *(danger)* | `POST /api/runs/{id}/reset` | `gui_log.jsonl` | clears markers or re-inits run meta |

---

## Quality offers (pre-clean, BUILD-072)

Non-blocking cards in the workspace **gate-actions** panel when the selected stage matches a [quality roadmap](../cross-cutting/podcast-quality-roadmap.md) checkpoint. Pre-clean never auto-runs.

| Checkpoint | GUI stage focus | Default `scope` | API |
|------------|-----------------|-----------------|-----|
| `before_ingest` | `audio_preclean` | `full_source` | `POST …/preclean-offer` |
| `g1_vo_pickup` | `g1_vo_pickup` (all lines recorded) | **`vo_pickup`** | same |

**`action` values:** `offer` (card shown), `accept`, `dismiss`. Persisted under `run_meta.json` → `audio_preclean` (`enabled`, `scope`, `offered_at`, `decisions`). Log lines use `RunContext.log()` → `gui_log.jsonl`.

---

## Gates and dedicated flows

| User-visible | Stage `id` | API | Log file | Artifacts |
|--------------|------------|-----|----------|-----------|
| **Transcript review** (G0) | `transcript_review` | `GET …/transcript`, `PATCH …/transcript/words`, `GET …/transcript-review`, `PUT …/transcript-review/{chunk_id}`, `POST …/transcript-review/complete` | `gui_log.jsonl` (`Transcript dock: saved N word edit(s).`) | `transcript/full.json`, `transcript/review_queue.json`, `transcript/review_clips/*`, `transcript/corrections.json`, `operator/transcript_corrected.*`, `.stage_done/transcript_review` |
| **Disfluency review** (G0.5) | `disfluency_review` | `GET/PUT …/disfluency-review`, `POST …/disfluency-review/complete`, `PATCH …/disfluency-restore` | `gui_log.jsonl` (`disfluency_review`) | `transcript/disfluencies.json`, `transcript/disfluency_clips/`, `.stage_done/disfluency_review` |
| **Interview profile** | `analysis_profile` | `GET/PUT …/analysis-profile`, `POST …/analysis-profile/verify`, `GET …/story-board`, `PATCH …/investigation-queue/{id}` | `gui_log.jsonl` (`analysis_profile`) | `understanding/analysis_state.json`, `understanding/investigation_queue.json`; stage status `locked` until `optimal_questions` done; run payload includes `profile_ready_for_review` |
| **VO pickup (G1)** | `g1_vo_pickup` | `POST …/vo/{line_id}` (multipart WAV), `POST …/preclean-offer` (`checkpoint: g1_vo_pickup`) | `gui_log.jsonl` (`g1_vo_pickup`, `audio_preclean`) | `vo_pickup/{line_id}.wav`, `understanding/gap_report.json`, `run_meta.json.audio_preclean.scope=vo_pickup` |
| **Choose output (G2)** | `g2_flow_select` | `POST …/flow` body `{ "flow": "flow1" \| "flow2" \| "flow3" }` | `gui_log.jsonl` (`g2_flow_select`) | `run_meta.json` (`selected_flow`) |

---

## Automated analysis stages (titles → ids)

Executed via `POST …/execute` with `mode: "stage"` and `stage: <id>` or `mode: "analysis"`. Completion: `.stage_done/<id>` and `gui_log.jsonl`.

| Title (UI) | `id` | Main output artifacts |
|------------|------|-------------------------|
| Ingest | `ingest` | `ingest/normalized.wav`, `ingest/checksums.json` |
| Transcribe | `transcribe` | `transcript/full.json`, `transcript/speakers.json` |
| STT review prep | `transcript_review_build` | `transcript/review_queue.json`, clips |
| Disfluency extract | `disfluency_extract` | `transcript/disfluencies.json`, `transcript/disfluency_clips/` |
| Source acoustic profile | `source_acoustic_profile` | `understanding/source_acoustic_profile.json` |
| Sonic context build | `sonic_context_build` | `understanding/sonic_context.json` |
| Speaker roles | `speaker_roles` | `understanding/speakers.json` |
| Content understanding | `content_context` | `understanding/content_brief.json` |
| Segment boundaries | `boundary_detection` | `segments/boundaries.json` |
| Segment classification | `segment_classification` | `segments/manifest.json` |
| Content brief re-anchor | `content_brief_reanchor` | `understanding/content_brief.json` (patch) |
| Sound design palettes | `sound_design_palettes` | SDP `palettes`, `coherence` in `understanding/sound_design_plan.json` |
| Gap evaluation | `missing_framing` | `understanding/gap_evaluations.json` |
| Interviewer script | `optimal_questions` | `understanding/gap_report.json`, `understanding/interviewer_script.txt` |
| VO ingest *(on-demand)* | `vo_ingest` | Merges `vo_pickup/*.wav`; not in `ANALYSIS_ORDER` — runs on next batch execute or `mode: stage` |

---

## Flow 1 / Flow 2 / Flow 3 stages (after G2)

Shown only when `run_meta.selected_flow` matches. Same execute endpoint: `mode: "flow1"` \| `"flow2"` \| `"flow3"` runs the full selected flow (or pass `from_stage`), or use `mode: "stage"` with a single stage id.

**Flow 3** is text-only publishing copy (`flow_3_description/show_description.json` + `.md`); no audio mux or `master.wav`. Prerequisites: shared analysis complete (`require_analysis_artifacts_complete`), G1 clear; preflight for `podcast_show_description` uses `content_brief`, `speakers`, `manifest` (not Flow 1 ranking).

| Flow | Title | `id` | Main artifacts |
|------|-------|------|------------------|
| 1 | Topic coverage | `topic_coverage_audit` | `flow_1_master/coverage_audit.json` |
| 1 | Narrative arc | `narrative_arc_plan` | `flow_1_master/narrative_plan.json` |
| 1 | Segment ordering | `full_master_ranking` | `flow_1_master/selection.json` |
| 1 | EDL narrative audit | `edl_narrative_audit` | `flow_1_master/edl_narrative_audit.json` |
| 1 | Transitions | `transitions` | `flow_1_master/transitions.json` |
| 1 | Sound design plan | `sound_design_plan_flow1` | `understanding/sound_design_plan.json` |
| 1 | VO finalize | `sound_design_vo_finalize` | Updates SDP cues with `measured_duration_ms` from `vo_pickup/` |
| 1 | EDL | `edl_flow1` | `flow_1_master/edl.json` |
| 1 | Assembly preview | `assembly_preview` | `flow_1_master/assembly_preview.wav` (speech + VO only; listen before SFX spend) |
| 1 | Craft MMAudio prompts | `sfx_prompt_craft` | `sound_design/sfx_prompts.json` |
| 1 | Generate SFX | `mmaudio_sfx_flow1` | `sound_design/assets/{asset_id}.wav` (+ mirror `flow_1_master/sfx/`) |
| 1 | Mix assembly | `mix_flow1` | `flow_1_master/assembly.wav` |
| 1 | Master export | `master_flow1` | `flow_1_master/master.wav` |
| 2 | Highlight selection | `highlight_selection` | `flow_2_highlights/selection.json` |
| 2 | Sound design plan | `sound_design_plan_flow2` | `understanding/sound_design_plan.json` |
| 2 | Craft MMAudio prompts | `sfx_prompt_craft` | `sound_design/sfx_prompts.json` |
| 2 | Generate SFX | `mmaudio_sfx_flow2` | `sound_design/assets/{asset_id}.wav` (+ mirror `flow_2_highlights/sfx/`) |
| 2 | Mix assembly | `mix_flow2` | `flow_2_highlights/assembly.wav` |
| 2 | Master export | `master_flow2` | `flow_2_highlights/master.wav` |
| 1 / 2 | Master QA (post-flow, automatic) | `verify_master` | `gui_log.jsonl` (`stage: verify_master`); validates `flow_*_*/master.wav` LUFS + true peak |
| 3 | Show description | `podcast_show_description` | `flow_3_description/show_description.json` |
| 3 | Export blurb | `export_show_description` | `flow_3_description/show_description.md` |

### MMAudio operator journey (SFX + G1.5)

**G1.5 (shipped):** Optional pre-spend prompt review when `g1_5_require_prompt_approval: true` in merged config.

Step-by-step: which panel, artifacts, and `gui_log.jsonl` events — [local-audio-stack.md § GUI operator journey](../cross-cutting/local-audio-stack.md#gui-operator-journey).

| User-visible | Stage `id` | API | Log file | Artifacts |
|--------------|------------|-----|----------|-----------|
| **G1.5 prompt review** (optional) | `sfx_prompt_craft` | `GET/PUT …/sfx-prompts`, `POST …/sfx-prompts/approve` | `gui_log.jsonl` (`sfx_prompt_craft`) | `sound_design/sfx_prompts.json`, `run_meta.json` → `sfx_prompt_review` |
| **Post-listen QA** (advisory; **block_mix** when configured) | `sfx_prompt_craft`, `mmaudio_sfx_flow1`, `mmaudio_sfx_flow2`, **`mix_flow1`**, **`mix_flow2`** | `POST …/sfx-prompts/listen-result` (`mode`: `post_listen` \| `under_speech`); `GET …/sfx-prompts` → `mmaudio_qa`, `listen_results` | `sfx_post_listen_pass` / `sfx_post_listen_fail`; under-speech → `speech_under_listen_result_recorded` | `run_meta.json` → `sfx_listen_results[]` or `speech_under_listen_results[]` |
| **Auto-refine / regen** (optional) | `sfx_prompt_craft`, `mmaudio_sfx_flow*` | `POST …/sfx-prompts/refine`, `POST …/sfx-prompts/regenerate`, `GET …/sfx-qa` | `sfx_prompts_refined`, `sfx_regen_requested` | updated `sfx_prompts.json`, `sound_design/mmaudio_qa.json` |
| **Generate SFX** blocked when G1.5 required | `mmaudio_sfx_flow1` / `mmaudio_sfx_flow2` | same GET for `can_generate` | `gui_log.jsonl` on block | — |

`SfxPostListenPanel` per asset shows: `verdict`, `theme_fit_score`, `semantic_qa_verdict`, `semantic_similarity`, `recommended_action`, `spectral_bucket_match` (from `mmaudio_qa`). When `post_listen_gate_mode` is `block`, failed listen/QA shows a blocking banner on mix stages.

`SfxPostListenPanel` also attempts under-speech audition via `GET /api/runs/{run_id}/audio/sfx-under-speech?asset_id=...`; record under-speech checks with `POST …/sfx-prompts/listen-result` and `mode=under_speech`. UI falls back to solo asset playback when unavailable.

### QC summary cards (gap-closure)

When `run_meta.qc_summaries` is populated by narrative/EDL/show QC gates:

| Stage panel | Card key | Source |
|-------------|----------|--------|
| `full_master_ranking`, `edl_flow1` | `narrative_qc` | `gates.check_narrative_qc` |
| `edl_narrative_audit`, `edl_flow1` | `edl_narrative_qc` | `gates.check_edl_narrative_qc` |
| `podcast_show_description` | `show_description_qc` | `gates.check_show_description_qc` |
| `mix_flow1`, `mix_flow2`, `master_flow1`, `master_flow2` | `mix_intelligibility` | `run_meta.qc_summaries.mix_intelligibility` (when `mix.intelligibility_qc.enabled`) |

### Source acoustic profile

| User-visible | Stage `id` | API | Notes |
|--------------|------------|-----|-------|
| Recompute profile | `source_acoustic_profile` | `POST …/recompute-acoustic-profile` | Re-runs DSP profile from ingest/transcript |

Set `g1_5_require_prompt_approval: true` in `config/app.defaults.json` (or override) to require approval before MMAudio SFX generation. Post-listen pass/fail does **not** block generation or mix unless product adds a hard gate later. Legacy stage ids `mux_flow1` / `mux_flow2` and v1 `podcast_sfx_brief` / `sfx_brief` remain runnable via `mode: stage` only.

| Shipped |
|---------|
| G1.5 inline panel (edit prompts, `prompt_influence`, approve, SDP warnings) |
| Post-listen panel: Listen → Pass/Fail + optional note; read-only listen history |
| Schema validation on PUT; `can_generate` blocks SFX stages when G1.5 required |
| Log: `sfx_prompts_approved`, edit resets approval; post-listen pass/fail events |

---

## LLM audit trail (not the same as `gui_log`)

| Path | Purpose |
|------|---------|
| `understanding/stage_runs/<stage>/attempt_*.json` | Full envelope, `context_volley`, schema validation errors — for **debugging model I/O**. |
| `understanding/llm_calls/` | **Per API call** labeled JSON + optional `.md` — [llm-call-record-framework.md](../cross-cutting/llm-call-record-framework.md); **GUI:** Pipeline → **Debug** (`LlmCallsPanel`); export via `tools/export_llm_calls.py` |

**Routing fields (BUILD-073):** `model_tier`, `model_id`, `task_kind`, `arbiter_result`, `shard_count`, `truncation_flags` may appear in `attempt_*.json` — [llm-orchestration.md](../cross-cutting/llm-orchestration.md).

Operators rarely need this; engineers and support do.

---

## Related

- [api-reference.md](./api-reference.md)
- [operator-stage-checklists.md](./operator-stage-checklists.md)
- [operator-gates.md](./operator-gates.md)
- [artifact-layout.md](../cross-cutting/artifact-layout.md)
- [transcript-review.md](../pipeline/transcription/transcript-review.md)
