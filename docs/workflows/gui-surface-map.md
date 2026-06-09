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
| Header | Compact status bar | Execution, job status (including **Reuse or run fresh**, **Review before save**), source file, **audio hash** chip (click-to-copy), updated |
| Header | **Command bar** | All tabs: running / blocked / handoff / next CTA from `journey` |
| Below command bar | **Execution status banner** | Running / API consent / blocked / last job error — complements command bar |
| Header | **Action** badge | Opens operator action modal when checkpoints/handoffs pending |
| Header | **Mute** / **Menu** | Mute attention sounds; overflow: revoke API, API chip status, **Clear session** |
| Tabs | **Start \| Executions \| Pipeline \| Logs** | Tab switch does **not** stop polling or clear `runId` |
| **Start** | Input audio list | Pick source WAV, start new execution → switches to Pipeline |
| **Executions** | Previous runs list | Resume any `exec_*`; active run highlighted; **Same audio** pill when hash matches active session; hash badge per run; refresh on tab focus |
| **Pipeline** | Stage rail + sub-tabs | **Stage \| Story \| Timeline \| Profile (JSON) \| Files \| Engineering** — primary operator flow |
| **Pipeline** | **Phase guidance banner** | `journey.phase_guidance[phase]` — goal, progress, top orange actions |
| **Pipeline** | **Stage guidance panel** | `stages[].guidance` — prerequisites, actions, unlocks on every stage detail |
| **Logs** | Full log viewer | Filters (level, stage, search), tail size, detail expand, auto-scroll |
| Footer | Mini log strip | 2–3 latest lines; click → Logs tab; polls every 2s while run active |
| Modals | Operator action | Gates, checkpoints, handoffs, pre-clean offers, **Previous execution reuse**, **Review outputs before saving** — auto-open on `action_required`, `needs_stage_reuse`, or `awaiting_write_approval`; **always** selects blocking stage (including on Logs tab) via `findPendingFocusStage` |
| Modals | API consent / Confirm | Existing API consent; shared confirm dialog replaces `window.confirm` |

**Attention sound:** Short browser ping on new `level=action` log lines, job `gate` / `needs_operator`, and new `action_required` stages (unless muted).

**API consent:** Before `POST …/execute`, GUI prompts once per provider per browser session; optional persist to `ASSETS/.gui/api_consent.json`. Backend `runner.start` rejects execute when required providers are not granted (`job.status: needs_operator`).

**Clear session:** Header menu — stops job poll, clears UI state, and clears server active run (`DELETE /api/session/active` or `PUT` with `run_id: null`). **Resume server session** appears on empty Pipeline when server still has an active `exec_*`.

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

| Sub-tab | Content | When visible |
|---------|---------|--------------|
| **Stage** | Title, description, **Previous execution reuse** (`StageReuseSection`), **Review outputs before saving** (`WriteApprovalPanel` when staged), **artifact checklist** (`artifacts_status`: pending / partial / complete; **Fill gaps** on partial), inline audio for `audio_outputs_present`, handoff panel, LLM routing summary, checkpoint CTA | Always when `run_id` set |
| **Story** | Story Board — themes, investigations, **Lock story for podcast edit** | When analysis workspace exists |
| **Timeline** | Mouse-first NLE: smart actions, review queue, filters, undo history, transport, transcript trim, assembly A/B preview | After segment classification (empty state otherwise) |
| **Profile** | Analysis profile form | When `profile_ready_for_review` or profile verified; **locked** with waiting message until understanding analysis completes |
| **Files** | JSON / text artifact editor (Zod pre-save for registered paths) | When stage has editable artifacts |
| **Engineering** | LLM call record index and editor | Power-user audit path |

Gate/checkpoint panels render in the **operator action modal**, not inline on Stage.

### G0 transcript review panel (action modal)

| Component | File | APIs | Operator actions |
|-----------|------|------|------------------|
| Chunk navigator + clip audio + bulk textarea | `TranscriptReviewPanel` | `GET/PUT …/transcript-review`, `POST …/complete` | Previous/Next clip, **Save chunk**, **Complete transcript review** |
| Synced word-level dock | `TranscriptDockViewer` | `GET …/transcript`, `PATCH …/transcript/words` | Click seek, double-click edit, debounced save |
| Fuzzy similar-word panel | `FuzzyReplacePopover` | *(client)* → batch `PATCH …/transcript/words` | Match strictness 80–100%, jump to match, **Replace N words** |

Also mounted on **Transcribe** / **Transcript review** stage detail (`StageDetail`) without the chunk navigator.

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
| Paths / port for UI | `GET /api/config` | — | reads `config` + repo; includes `llm_routing_stage_ids` from `web/stages.py` |
| Active run + tail log | `GET /api/session` | `gui_log.jsonl` of active run | — |
| Set active run / stage focus | `PUT /api/session/active` `{ run_id?, selected_stage_id? }` | — | `ASSETS/.gui/active_execution.json`; null `run_id` clears |
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
| Run pipeline / stage | *(execute)* | `POST /api/runs/{id}/execute` body: `mode` = `stage` \| `analysis` \| `flow1` \| `flow2` \| `flow3` \| `nle_apply`, `stage`, `from_stage`, `nle_full_refresh`, `nle_apply_mode` | `gui_log.jsonl`, `gui_job.json` | markers + stage outputs per `pipeline.py` orders |
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
| **Interview profile** | `analysis_profile` | `GET/PUT …/analysis-profile`, `POST …/analysis-profile/verify` | `gui_log.jsonl` (`analysis_profile`) | `understanding/analysis_state.json`, `understanding/investigation_queue.json`; stage status `locked` until `optimal_questions` done; run payload includes `profile_ready_for_review` |
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
| Speaker roles | `speaker_roles` | `understanding/speakers.json` |
| Content understanding | `content_context` | `understanding/content_brief.json` |
| Segment boundaries | `boundary_detection` | `segments/boundaries.json` |
| Segment classification | `segment_classification` | `segments/manifest.json` |
| Gap evaluation | `missing_framing` | `understanding/gap_evaluations.json` |
| Interviewer script | `optimal_questions` | `understanding/gap_report.json`, `understanding/interviewer_script.txt` |

---

## Flow 1 / Flow 2 / Flow 3 stages (after G2)

Shown only when `run_meta.selected_flow` matches. Same execute endpoint: `mode: "flow1"` \| `"flow2"` \| `"flow3"` runs the full selected flow (or pass `from_stage`), or use `mode: "stage"` with a single stage id.

**Flow 3** is text-only publishing copy (`flow_3_description/show_description.json` + `.md`); no audio mux or `master.wav`.

| Flow | Title | `id` | Main artifacts |
|------|-------|------|------------------|
| 1 | Topic coverage | `topic_coverage_audit` | `flow_1_master/coverage_audit.json` |
| 1 | Narrative arc | `narrative_arc_plan` | `flow_1_master/narrative_plan.json` |
| 1 | Segment ordering | `full_master_ranking` | `flow_1_master/selection.json` |
| 1 | Transitions | `transitions` | `flow_1_master/transitions.json` |
| 1 | Sound design plan | `sound_design_plan_flow1` | `understanding/sound_design_plan.json` |
| 1 | VO finalize | `sound_design_vo_finalize` | Updates SDP cues with `measured_duration_ms` from `vo_pickup/` |
| 1 | EDL | `edl_flow1` | `flow_1_master/edl.json` |
| 1 | Assembly preview | `assembly_preview` | `flow_1_master/assembly_preview.wav` (speech + VO only; listen before SFX spend) |
| 1 | Craft ElevenLabs prompts | `elevenlabs_prompt_craft` | `sound_design/elevenlabs_prompts.json` |
| 1 | Generate SFX | `elevenlabs_sfx_flow1` | `sound_design/assets/{asset_id}.wav` (+ mirror `flow_1_master/sfx/`) |
| 1 | Mix assembly | `mix_flow1` | `flow_1_master/assembly.wav` |
| 1 | Master export | `master_flow1` | `flow_1_master/master.wav` |
| 2 | Highlight selection | `highlight_selection` | `flow_2_highlights/selection.json` |
| 2 | Sound design plan | `sound_design_plan_flow2` | `understanding/sound_design_plan.json` |
| 2 | Craft ElevenLabs prompts | `elevenlabs_prompt_craft` | `sound_design/elevenlabs_prompts.json` |
| 2 | Generate SFX | `elevenlabs_sfx_flow2` | `sound_design/assets/{asset_id}.wav` (+ mirror `flow_2_highlights/sfx/`) |
| 2 | Mix assembly | `mix_flow2` | `flow_2_highlights/assembly.wav` |
| 2 | Master export | `master_flow2` | `flow_2_highlights/master.wav` |
| 1 / 2 | Master QA (post-flow, automatic) | `verify_master` | `gui_log.jsonl` (`stage: verify_master`); validates `flow_*_*/master.wav` LUFS + true peak |
| 3 | Show description | `podcast_show_description` | `flow_3_description/show_description.json` |
| 3 | Export blurb | `export_show_description` | `flow_3_description/show_description.md` |

### ElevenLabs operator journey (SFX + G1.5)

**G1.5 (shipped):** Optional pre-spend prompt review when `g1_5_require_prompt_approval: true` in merged config.

Step-by-step: which panel, artifacts, and `gui_log.jsonl` events — [elevenlabs-integration-guide.md § GUI operator journey](../cross-cutting/elevenlabs-integration-guide.md#gui-operator-journey).

| User-visible | Stage `id` | API | Log file | Artifacts |
|--------------|------------|-----|----------|-----------|
| **G1.5 prompt review** (optional) | `elevenlabs_prompt_craft` | `GET/PUT …/elevenlabs-prompts`, `POST …/elevenlabs-prompts/approve` | `gui_log.jsonl` (`elevenlabs_prompt_craft`) | `sound_design/elevenlabs_prompts.json`, `run_meta.json` → `elevenlabs_prompt_review` |
| **Post-listen QA** (advisory) | `elevenlabs_prompt_craft`, `elevenlabs_sfx_flow1`, `elevenlabs_sfx_flow2` | `POST …/elevenlabs-prompts/listen-result`; `GET …/runs/{id}` → `elevenlabs_generated_assets` | `elevenlabs_post_listen_pass` / `elevenlabs_post_listen_fail` | `run_meta.json` → `elevenlabs_listen_results[]` |
| **Generate SFX** blocked when G1.5 required | `elevenlabs_sfx_flow1` / `elevenlabs_sfx_flow2` | same GET for `can_generate` | `gui_log.jsonl` on block | — |

### QC summary cards (gap-closure)

When `run_meta.qc_summaries` is populated by narrative/EDL/show QC gates:

| Stage panel | Card key | Source |
|-------------|----------|--------|
| `full_master_ranking`, `edl_flow1` | `narrative_qc` | `gates.check_narrative_qc` |
| `edl_narrative_audit`, `edl_flow1` | `edl_narrative_qc` | `gates.check_edl_narrative_qc` |
| `podcast_show_description` | `show_description_qc` | `gates.check_show_description_qc` |

### Source acoustic profile

| User-visible | Stage `id` | API | Notes |
|--------------|------------|-----|-------|
| Recompute profile | `source_acoustic_profile` | `POST …/recompute-acoustic-profile` | Re-runs DSP profile from ingest/transcript |

Set `g1_5_require_prompt_approval: true` in `config/app.defaults.json` (or override) to require approval before ElevenLabs spend. Post-listen pass/fail does **not** block generation or mix unless product adds a hard gate later. Legacy stage ids `mux_flow1` / `mux_flow2` and v1 `podcast_sfx_brief` / `sfx_brief` remain runnable via `mode: stage` only.

| Shipped |
|---------|
| G1.5 inline panel (edit prompts, `prompt_influence`, approve, SDP warnings) |
| Post-listen panel: Listen → Pass/Fail + optional note; read-only listen history |
| Schema validation on PUT; `can_generate` blocks SFX stages when G1.5 required |
| Log: `elevenlabs_prompts_approved`, edit resets approval; post-listen pass/fail events |

---

## LLM audit trail (not the same as `gui_log`)

| Path | Purpose |
|------|---------|
| `understanding/stage_runs/<stage>/attempt_*.json` | Full envelope, `context_volley`, schema validation errors — for **debugging model I/O**. |
| `understanding/llm_calls/` | **Per API call** labeled JSON + optional `.md` — [llm-call-record-framework.md](../cross-cutting/llm-call-record-framework.md); **GUI:** Pipeline → **LLM calls** tab; export via `tools/export_llm_calls.py` |

**Routing fields (BUILD-073):** `model_tier`, `model_id`, `task_kind`, `arbiter_result`, `shard_count`, `truncation_flags` may appear in `attempt_*.json` — [llm-orchestration.md](../cross-cutting/llm-orchestration.md).

Operators rarely need this; engineers and support do.

---

## Related

- [api-reference.md](./api-reference.md)
- [operator-stage-checklists.md](./operator-stage-checklists.md)
- [operator-gates.md](./operator-gates.md)
- [artifact-layout.md](../cross-cutting/artifact-layout.md)
- [transcript-review.md](../pipeline/transcription/transcript-review.md)
