# Ticket specifications — acceptance criteria

Per-ticket **definition of done** for the entire repository. Status lives in [README.md](./README.md); priority in [steps-forward.md](./steps-forward.md).

---

## Wave 0 — Docs and entrypoints

### BUILD-000 — Doc hub + agent guide

- [ ] `docs/INDEX.md` links every major spec
- [ ] `AGENTS.md` read order includes build-out suite
- [ ] `README.md` points to SETUP and docs hub
- [ ] `SETUP.md` covers bootstrap, secrets, first run
- [ ] [repository-map.md](./repository-map.md) reflects current tree

### BUILD-001 — Artifact layout + schemas

- [ ] [artifact-layout.md](../cross-cutting/artifact-layout.md) matches run directory on disk
- [ ] `docs/cross-cutting/json-schemas/` validates stage outputs
- [ ] [json-schema-coverage.md](../cross-cutting/json-schema-coverage.md) lists gaps

### BUILD-002 — Operator gates

- [ ] G0, G1, G2 documented with pass/fail actions
- [ ] Quality offers distinguished from gates

### BUILD-003 — Stage READMEs

- [ ] Each `docs/pipeline/*/README.md` lists stage ids, I/O, BUILD ticket

### BUILD-004 — Build-out index

- [ ] [README.md](./README.md), [steps-forward.md](./steps-forward.md), [implementation-guide.md](./implementation-guide.md), [stage-registry.md](./stage-registry.md), this file

---

## Wave 1 — Shell and core library

### BUILD-010 — Anchor lock

- [x] `requirements.lock` at repo root with full transitive pins
- [x] `bootstrap_venv.sh` installs **only** from lock when present
- [x] `check_prerequisites.sh` runs `pip-audit`; fails on unaccepted HIGH/CRITICAL
- [x] [anchored-requirements.lock](../cross-cutting/anchored-requirements.lock) doc mirror updated
- [x] Accepted advisories table in [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md) if needed

### BUILD-011 — Config loader

- [ ] `config.py` merges `app.defaults.json` + `secrets.env`
- [ ] Model IDs and paths documented in [config-keys.md](../cross-cutting/config-keys.md)

### BUILD-012 — Run workspace

- [x] `RunContext` allocates `exec_NNN_<timestamp>` under `executions_root` (default `ASSETS/executions`)
- [x] `RunContext` resolves paths under execution dir; `run_meta.json` records `input_audio_path` from GUI/API (not config-only)
- [x] `.stage_done/<stage>` idempotency
- [x] `ctx.log()` appends to `gui_log.jsonl`

### BUILD-013 — OpenAI runner + stage envelope

- [ ] `analysis_stage` loads prompts from `docs/prompts/`
- [ ] `prompt_validation` enforces JSON schemas
- [ ] `context_volley` builds selective message history

---

## Wave 1.5 — Web GUI and operator platform

### BUILD-014 — FastAPI server + static UI

- [x] `./scripts/run.sh` serves GUI
- [x] Home screen: **Input audio** from `GET /api/assets` (no operator WAV path in config)
- [x] Home screen: **Previous executions** from `GET /api/runs`; resume via `PUT /api/session/active`
- [x] Run list, stage execute, artifact editor, log panel
- [x] Routes match [api-reference.md](../workflows/api-reference.md) and [assets-and-executions.md](../cross-cutting/assets-and-executions.md)

### BUILD-015 — Background job runner

- [ ] `POST …/execute` writes `gui_job.json` (running → done/error)
- [ ] Job status visible after page refresh

### BUILD-016 — Centralized operator log

- [ ] No operator-facing `print()` without `ctx.log()` mirror
- [ ] `GET …/log` returns tail of `gui_log.jsonl`

### BUILD-017 — Gates G0–G2 (partial for G2)

- [x] G0 blocks analysis after `transcript_review_build` until review complete
- [x] G1 blocks flow until `vo_pickup` satisfied for `delivery: record`
- [x] G2 API accepts `flow3` (flow1 \| flow2 \| flow3)
- [ ] Gate panels match [gui-surface-map.md](../workflows/gui-surface-map.md)

### BUILD-018 — Transcript review + analysis memory

- [ ] Confidence-ranked review queue
- [ ] `analysis_state.json` profile + investigation queue
- [ ] Orchestrator drains queue after LLM stages

### BUILD-056 — NLE editor state

- [ ] `segments/nle_edits.json` read/write via API
- [x] Consumed by BUILD-068

### BUILD-057 — GUI session / active run

- [x] `GET /api/session` returns active run id
- [x] Active run persisted under `ASSETS/.gui/active_execution.json`; survives `./scripts/run.sh` restart when execution folder intact

---

## Wave 2 — Shared analysis

### BUILD-019 — Audio pre-clean

- [x] `stages/audio_preclean.py` calls ElevenLabs isolation REST
- [x] Writes `preclean/isolated.wav` + `lineage.json` (full source); `vo_pickup/clean/` + lineage for pickup scope
- [x] Invalidates downstream from ingest (or vo_ingest for pickup-only) on operator accept
- [x] GUI offers at checkpoints in [audio_preclean/README.md](../pipeline/audio_preclean/README.md) — **BUILD-072**
- [x] Never auto-runs

### BUILD-020 — Ingest

- [x] Normalized WAV + checksums
- [x] Optional input from preclean path when BUILD-019 used

### BUILD-021 — AWS Transcribe

- [x] `aws` CLI subprocess only (no boto3)
- [x] Word-level transcript + speaker labels

### BUILD-022–023 — Speaker roles + content context

- [x] `speakers.json`, `content_brief.json`
- [x] Memory sync into `analysis_state.json`

### BUILD-024 — Segmentation

- [x] `boundaries.json`, `manifest.json`

### BUILD-025–026 — Missing framing + optimal questions

- [x] `gap_evaluations.json`, `gap_report.json`, `interviewer_script.txt`

### BUILD-027 — VO ingest

- [x] Ingests `vo_pickup/*.wav` after operator records

### BUILD-028 — Analysis CLI + pipeline

- [x] `tools/run_analysis.py` → `run_analysis()`
- [x] `--from-stage` clears markers correctly

---

## Wave 3a — Flow 1

### BUILD-029–030 — Topic coverage + narrative arc

- [x] JSON artifacts under `flow_1_master/`
- [x] BUILD-081: warn/block if `operator_verified` false

### BUILD-031–032 — Ranking + transitions

- [x] `selection.json`, `transitions.json`
- [x] NLE overrides applied (BUILD-068)

### BUILD-033 — Podcast SFX brief (v1)

- [x] `podcast_sfx_brief.json` generated
- [x] Superseded by SDP flow plan (BUILD-062) on default Flow 1 path

### BUILD-034 — ElevenLabs SFX flow1

- [x] WAV per brief line via REST
- [x] One WAV per `asset_id` (BUILD-064)

### BUILD-035 — Mux assembly (v1)

- [x] `edl.json`, `assembly.wav` (mix via BUILD-065; EDL includes VO placements per BUILD-067)
- [x] EDL includes gap VO placements (BUILD-067)

### BUILD-036 — Master export flow1

- [x] `master.wav` at −16 LUFS target (measurement BUILD-071)

---

## Wave 3b — Flow 2

### BUILD-040–041 — Highlight + SFX brief

- [x] `selection.json`, `sfx_brief.json`

### BUILD-042 — ElevenLabs SFX flow2

- [x] Montage profile generation

### BUILD-043 — Micro-assembly

- [x] `assembly.wav` (SDP `between_clips` + cold open via BUILD-065)

### BUILD-044 — Master export flow2

- [x] `master.wav` at −14 LUFS target

---

## Wave 3c — Flow 3

### BUILD-045 — Podcast show description

- [x] `publishing_flow3.py` runs `podcast_show_description` stage
- [x] Output validates against show description schema
- [x] Third person; 150–250 words; grounded in content brief
- [x] Prompt: [podcast-show-description.system.txt](../prompts/publishing/podcast-show-description.system.txt)

### BUILD-046 — Show description export

- [x] `export_show_description` writes `show_description.md` from JSON (no LLM)
- [x] Plain text suitable for podcast directories

### BUILD-080 — Flow 3 wire-up

- [x] `FLOW3_ORDER` in `pipeline.py`; `run_flow3()`; `run_single_stage` branch
- [x] `tools/run_flow.py --flow flow3`
- [x] `cli.flow_cmd` accepts flow3
- [x] `web/runner.py` execute `mode: flow3`
- [x] `server.py` `FlowBody` regex includes flow3
- [x] `web/stages.py` `FLOW3_STAGES` + `all_stages_for_run` branch
- [x] G2 GUI copy lists all three flows
- [x] [smoke-test.md](../workflows/smoke-test.md) Flow 3 section runnable

---

## Wave 4 — QA tooling

### BUILD-050 — Mastering module

- [x] Shared `mastering.py` for flow1 and flow2

### BUILD-051 — Flow CLI

- [x] `run_flow.py` for flow1 \| flow2
- [x] flow3 when BUILD-080 done

### BUILD-052 — verify_master

- [x] ffprobe format check
- [x] LUFS + true peak (BUILD-070)

### BUILD-053 — Smoke test doc

- [x] Documented checklist exists
- [ ] All three flows pass on fixture when implemented

### BUILD-054–055 — Tests

- [x] `test_prompt_validation.py`, `test_transcript_review.py`
- [x] Gates + pipeline smoke fixtures (steps-forward #18) — `test_gates.py`, `test_pipeline.py`, `run_fixtures.py`

---

## Wave 5 — Coherent sound design

### BUILD-060 — SDP schema + empty plan init

- [x] `sound_design_plan.schema.json` in json-schemas
- [x] Initialize `understanding/sound_design_plan.json` in `ensure_analysis_workspace` (first LLM analysis stage / profile edit)
- [x] Schema validation via `prompt_validation.validate_sound_design_plan` (init + Wave 5 SDP persists)

### BUILD-061 — Theme palettes stage

- [x] `sound_design_palettes` after `segment_classification`
- [x] Writes `palettes` + `coherence` to SDP

### BUILD-062 — Flow 1 sound design plan

- [x] `sound_design_plan_flow1` in `FLOW1_ORDER` after `transitions` (post G2 flow1 selection inputs)
- [x] Requires `run_meta.selected_flow` = `flow1`
- [x] LLM artifacts merge `assets[]` and `flow_plans.flow1` into `understanding/sound_design_plan.json`
- [x] Persist validates full SDP schema; cues must reference known `asset_id` values
- [x] Prompt: [plan-flow1.system.txt](../prompts/sound_design/plan-flow1.system.txt)

### BUILD-063 — Flow 2 sound design plan

- [x] `sound_design_plan_flow2` in `FLOW2_ORDER` after `highlight_selection` (post G2 flow2 selection inputs)
- [x] Requires `run_meta.selected_flow` = `flow2`
- [x] LLM artifacts merge `assets[]` and `flow_plans.flow2` into `understanding/sound_design_plan.json`
- [x] Persist validates full SDP schema; cues must reference known `asset_id` values
- [x] Prompt: [plan-flow2.system.txt](../prompts/sound_design/plan-flow2.system.txt)

### BUILD-064 — ElevenLabs prompt craft + generate

- [x] OpenAI craft stage → `elevenlabs_prompts.json`
- [x] One REST call per unique `asset_id`
- [x] Respects `duration_seconds` from plan

### BUILD-065 — Mix engine

- [x] `mix_flow1` / `mix_flow2` replace v1 speech-only mux (`sound_design.py` + canonical pipeline ids — BUILD-066)
- [x] VO + beds + stingers + ducking per [sound-design.md](../cross-cutting/sound-design.md)
- [x] `master.wav` audibly includes SFX (via `assembly.wav` → `master_flow*`)

### BUILD-066 — Pipeline + GUI wire-up

- [x] Stage order updated in `pipeline.py` and `web/stages.py` (`mix_flow1` / `mix_flow2` canonical; `mux_flow*` legacy aliases)
- [x] Optional G1.5 SFX prompt review panel (`elevenlabs_prompt_craft` + `/api/runs/{id}/elevenlabs-prompts*`; `g1_5_require_prompt_approval`)
- [x] v1 brief stages aliased or removed from default path (`podcast_sfx_brief` / `sfx_brief` single-stage only)

---

## Wave 6 — Podcast quality wiring

### BUILD-067 — Gap report → EDL

- [x] `edl_flow1` includes `vo_pickup` placements and gap-driven ordering
- [x] Transitions and ranking respect gap report (ranking/transitions LLM inputs; EDL weaves `transitions.json` + `gap_report` placements)

### BUILD-068 — NLE → selection/EDL

- [x] `nle_edits.json` applied before `full_master_ranking` or at EDL build
- [x] Exclude/split/reorder reflected in `selection.json` or EDL

### BUILD-069 — Assembly preview

- [x] `assembly_preview.wav` — speech + VO, no ElevenLabs
- [x] GUI listen action before SFX spend

### BUILD-070 — verify_master LUFS/peak

- [x] Integrated loudness and true peak per [evaluation-metrics.md](../cross-cutting/evaluation-metrics.md)
- [x] CLI exit non-zero on fail; GUI surfaces result (`gui_log.jsonl`, `stage: verify_master` after flow execute)

### BUILD-071 — Mastering measurement

- [x] `pyloudnorm` integrated LUFS on `assembly.wav` before final limiter (`mastering_bus.py`)
- [x] Targets and true-peak ceiling from BUILD-070 `TARGETS`; gain offset drives ffmpeg `loudnorm` pass
- [x] `gui_log.jsonl` records assembly-bus measurement on `master_flow1` / `master_flow2`

### BUILD-072 — Pre-clean quality offers

- [x] GUI prompts at all checkpoints in quality roadmap
- [x] Pickup-only scope flag in `run_meta.json` (`audio_preclean.scope: vo_pickup`)
- [x] `ctx.log()` for offer / accept / dismiss (`POST /api/runs/{id}/preclean-offer`)
- [x] Never auto-run pre-clean (stage skips until operator accepts)

---

## Wave 7 — Intelligence and guardrails

### BUILD-073 — Smart LLM routing

- [x] `model_registry`, `llm_arbiter` per [llm-orchestration-implementation-handoff.md](../cross-cutting/llm-orchestration-implementation-handoff.md)
- [x] Shard/collate for long interviews (`missing_framing`, `segment_classification`)
- [x] `stage_runs/*/attempt_*.json` records arbiter verdict (`arbiter_result`, `shard_count`, `model_tier`, `truncation_flags`)

### BUILD-081 — Profile gate for Flow 1 extended

- [x] Block or warn before `topic_coverage_audit` when `operator_verified` false
- [x] `ctx.log()` explains required profile action
- [x] Documented in [operator-gates.md](../workflows/operator-gates.md)

### BUILD-082 — Source acoustic profile stage

- [x] `understanding/source_acoustic_profile.json` per [source-derived-sonic-mix-profile.md](../cross-cutting/source-derived-sonic-mix-profile.md)
- [x] Consumed by BUILD-061 palettes and BUILD-064 craft

---

## Verification matrix

| After shipping | Run |
|----------------|-----|
| Any stage | [operator-stage-checklists.md](../workflows/operator-stage-checklists.md) rows |
| Wave 1 | `./tools/check_prerequisites.sh` |
| Wave 2 | `python tools/run_analysis.py` |
| Wave 3a/b | `python tools/run_flow.py --flow flow1\|flow2` |
| Wave 3c | `python tools/run_flow.py --flow flow3` |
| Wave 4+ audio | `python tools/verify_master.py <master.wav>` |
| Full repo | [smoke-test.md](../workflows/smoke-test.md) + [testing-and-verification.md](./testing-and-verification.md) |

---

## Related

- [README.md](./README.md) — ticket status table
- [stage-registry.md](./stage-registry.md) — stage ↔ module map
