# GUI surface map — panels, APIs, logs, artifacts

Single reference for **what the operator sees**, which **HTTP API** backs it, and which **artifacts** on disk are read or written. Source: `src/interview_mux/web/server.py`, `web/static/app.js`, `web/stages.py`, `session_log.py`, `web/runner.py`.

**Logging policy (do not duplicate elsewhere):** `.cursor/rules/interview-helper-mux.mdc` → **Centralized operator status and logs** — write operator-visible status only via `RunContext.log()` / `append_log` → `gui_log.jsonl`, and background execute state via `gui_job.json`.

**HTTP companion:** [api-reference.md](./api-reference.md) — method/path/body tables and common status codes. Stack pins: [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md).

**Convention:** `{run_id}` is the execution id (e.g. `exec_001_20260523T120000Z` or legacy `run_001`). Run root = that folder under `executions_root` or `data_root` — see [artifact-layout.md](../cross-cutting/artifact-layout.md).

---

## Log and job files (all runs)

| File | Purpose |
|------|---------|
| `gui_log.jsonl` | Append-only **operator-visible** messages (`ts`, `level`, `message`, optional `stage`, `detail`). Written via `RunContext.log()` and `POST /api/runs/{id}/log`. |
| `gui_job.json` | **Current / last background job** for pipeline execute (`status`, `mode`, `stage`, `message`, `updated_at`). |

**Where the UI shows them:** Run screen **log panel** loads `GET /api/runs/{id}` → `log_tail` and polls `GET /api/runs/{id}/log?tail=…`; **job status** from `GET /api/runs/{id}/job` (same payload nested under `job` on run fetch).

---

## Global (no `run_id`)

| User-visible / area | API | Log file | Artifact |
|----------------------|-----|----------|----------|
| Health | `GET /api/health` | — | — |
| Paths / port for UI | `GET /api/config` | — | reads `config` + repo |
| Active run + tail log | `GET /api/session` | `gui_log.jsonl` of active run | — |
| Set active run / stage focus | `PUT /api/session/active` | — | may touch session store under `.gui` (implementation detail) |
| Browse input audio | `GET /api/assets` | — | scans `ASSETS/` (skips `executions`, `.gui`) |
| List runs | `GET /api/runs` | — | summarizes each `run_meta.json` |
| Create run from asset | `POST /api/runs` | `gui_log.jsonl` (`setup`) | creates `run_meta.json`, dirs |

---

## Per-run core

| User-visible (sidebar / title from `stages.py`) | Stage `id` | Primary APIs | Log file | Primary artifacts (read/write) |
|--------------------------------------------------|------------|--------------|----------|----------------------------------|
| Run overview + stage list + embedded log tail | *(all)* | `GET /api/runs/{id}`, `GET /api/runs/{id}/job` | `gui_log.jsonl`, `gui_job.json` | `run_meta.json`, `.stage_done/*` |
| Append user or script note to log | *(optional)* | `POST /api/runs/{id}/log` | `gui_log.jsonl` | — |
| Timeline (waveform, segments, VO lines) | *(view)* | `GET /api/runs/{id}/timeline` | — | `segments/manifest.json`, `segments/nle_edits.json` (via NLE), `understanding/gap_report.json`, `vo_pickup/*.wav`, `ingest/normalized.wav` |
| NLE editor state | `nle` | `GET/PUT /api/runs/{id}/nle`, `PATCH …/nle/segment`, `POST …/nle/split` | `gui_log.jsonl` (`stage: nle`) | `segments/nle_edits.json` |
| JSON artifact editor | *(per path)* | `GET/PUT /api/runs/{id}/artifact?path=…` | `gui_log.jsonl` | any allowed JSON under run (e.g. `understanding/analysis_state.json`); optional invalidation |
| Play clip / source audio | *(audio)* | `GET /api/runs/{id}/audio?path=…`, `GET …/source-audio` | — | WAV under run or source path from `run_meta.json` |
| Run pipeline / stage | *(execute)* | `POST /api/runs/{id}/execute` body: `mode` = `stage` \| `analysis` \| `flow1` \| `flow2` (`flow3` planned — BUILD-080), `stage`, `from_stage` | `gui_log.jsonl`, `gui_job.json` | markers + stage outputs per `pipeline.py` orders |
| Reset / invalidate | *(danger)* | `POST /api/runs/{id}/reset` | `gui_log.jsonl` | clears markers or re-inits run meta |

---

## Gates and dedicated flows

| User-visible | Stage `id` | API | Log file | Artifacts |
|--------------|------------|-----|----------|-----------|
| **Transcript review** (G0) | `transcript_review` | `GET …/transcript-review`, `PUT …/transcript-review/{chunk_id}`, `POST …/transcript-review/complete` | `gui_log.jsonl` | `transcript/review_queue.json`, `transcript/review_clips/*`, `transcript/corrections.json`, `.stage_done/transcript_review` |
| **Interview profile** | `analysis_profile` | `GET/PUT …/analysis-profile`, `POST …/analysis-profile/verify` | `gui_log.jsonl` (`analysis_profile`) | `understanding/analysis_state.json`, `understanding/investigation_queue.json`, editable JSON paths in response |
| **VO pickup (G1)** | `g1_vo_pickup` | `POST …/vo/{line_id}` (multipart WAV) | `gui_log.jsonl` (`g1_vo_pickup`) | `vo_pickup/{line_id}.wav`, `understanding/gap_report.json` |
| **Choose output (G2)** | `g2_flow_select` | `POST …/flow` body `{ "flow": "flow1" \| "flow2" }` (`flow3` when BUILD-080 ships) | `gui_log.jsonl` (`g2_flow_select`) | `run_meta.json` (`selected_flow`) |

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

Shown only when `run_meta.selected_flow` matches. Same execute endpoint; `mode: "flow1"` \| `"flow2"` runs full flow or use `from_stage`. **Flow 3** stages below are spec/UI placeholders until **BUILD-045** / **BUILD-080** wire `publishing_flow3.py` and runner support.

| Flow | Title | `id` | Main artifacts |
|------|-------|------|------------------|
| 1 | Topic coverage | `topic_coverage_audit` | `flow_1_master/coverage_audit.json` |
| 1 | Narrative arc | `narrative_arc_plan` | `flow_1_master/narrative_plan.json` |
| 1 | Segment ordering | `full_master_ranking` | `flow_1_master/selection.json` |
| 1 | Transitions | `transitions` | `flow_1_master/transitions.json` |
| 1 | SFX brief | `podcast_sfx_brief` | `flow_1_master/podcast_sfx_brief.json` |
| 1 | Generate SFX | `elevenlabs_sfx_flow1` | `flow_1_master/sfx/*.wav` |
| 1 | EDL | `edl_flow1` | `flow_1_master/edl.json` |
| 1 | Assembly | `mux_flow1` | `flow_1_master/assembly.wav` |
| 1 | Master export | `master_flow1` | `flow_1_master/master.wav` |
| 2 | Highlight selection | `highlight_selection` | `flow_2_highlights/selection.json` |
| 2 | Montage SFX brief | `sfx_brief` | `flow_2_highlights/sfx_brief.json` |
| 2 | Generate SFX | `elevenlabs_sfx_flow2` | `flow_2_highlights/sfx/*.wav` |
| 2 | Micro-assembly | `mux_flow2` | `flow_2_highlights/assembly.wav` |
| 2 | Master export | `master_flow2` | `flow_2_highlights/master.wav` |
| 3 | Show description | `podcast_show_description` | `flow_3_description/show_description.json` |
| 3 | Export blurb | `export_show_description` | `flow_3_description/show_description.md` |

### ElevenLabs operator journey (SFX + G1.5)

Step-by-step: which panel, artifacts, and `gui_log.jsonl` events — [elevenlabs-integration-guide.md § GUI operator journey](../cross-cutting/elevenlabs-integration-guide.md#gui-operator-journey).

| v1 today | Target (planned) |
|----------|------------------|
| JSON editor on `podcast_sfx_brief.json` / `sfx_brief.json` | + `sound_design/elevenlabs_prompts.json` |
| Sidebar **Generate SFX** → REST `/v1/sound-generation` | G1.5 **Prompt review** panel before generate |
| Log: `ElevenLabs SFX generated …` `detail.api: rest` | + `elevenlabs_post_listen_pass` / `fail` |

---

## LLM audit trail (not the same as `gui_log`)

| Path | Purpose |
|------|---------|
| `understanding/stage_runs/<stage>/attempt_*.json` | Full envelope, `context_volley`, schema validation errors — for **debugging model I/O**. |

**Target fields (spec only, not yet in v1 JSON):** `model_tier`, `model_id`, `task_kind`, `arbiter_result`, `shard_count`, `truncation_flags` — [llm-orchestration.md](../cross-cutting/llm-orchestration.md).

Operators rarely need this; engineers and support do.

---

## Related

- [api-reference.md](./api-reference.md)
- [operator-stage-checklists.md](./operator-stage-checklists.md)
- [operator-gates.md](./operator-gates.md)
- [artifact-layout.md](../cross-cutting/artifact-layout.md)
- [transcript-review.md](../pipeline/transcription/transcript-review.md)
