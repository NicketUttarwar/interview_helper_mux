# Implementation guide — full repository build-out

How to take **interview_helper_mux** from a fresh clone to a production-ready operator app: every wave, every deliverable, and which doc to read before writing code.

**Start here if you are building code.** Operators should use [operator-stage-checklists.md](../workflows/operator-stage-checklists.md) instead.

---

## Document map (build-out folder)

| Doc | Use when |
|-----|----------|
| [remaining-build-commands.md](./remaining-build-commands.md) | **What to do next** — current Agent command queue |
| [steps-forward.md](./steps-forward.md) | Historical backlog + archived step prompts |
| [README.md](./README.md) | Ticket index by wave + status |
| [ticket-specs.md](./ticket-specs.md) | **Acceptance criteria** per BUILD ticket |
| [stage-registry.md](./stage-registry.md) | Every stage id, module, artifact, prompt |
| [full-application-flow.md](./full-application-flow.md) | End-to-end operator + system journey |
| [repository-map.md](./repository-map.md) | Path ↔ module ↔ ticket |
| [testing-and-verification.md](./testing-and-verification.md) | How to verify each wave ships correctly |
| [doc-maintenance.md](./doc-maintenance.md) | Docs to update in the same PR as code |

**North star (product quality):** [podcast-quality-roadmap.md](../cross-cutting/podcast-quality-roadmap.md)

---

## Read order (agents)

1. `.cursor/rules/interview-helper-mux.mdc` — **always-on** constraints (Context7, gates, logging, build-out workflow)
2. [AGENTS.md](../../AGENTS.md) — doc navigation index
3. [remaining-build-commands.md](./remaining-build-commands.md) — pick the current Agent command (or [steps-forward.md](./steps-forward.md) for history)
4. [ticket-specs.md](./ticket-specs.md) — acceptance for your BUILD id(s)
5. [stage-registry.md](./stage-registry.md) — stage you touch
6. Stage README under `docs/pipeline/<area>/README.md`
7. Prompt under `docs/prompts/` if LLM stage
8. [doc-maintenance.md](./doc-maintenance.md) — checklist before opening PR

---

## Phases — build the whole app

Each phase lists tickets, primary code paths, and verification. Dependencies match [README.md](./README.md#dependency-order).

### Phase 0 — Documentation and entrypoints (BUILD-000–004)

**Goal:** Navigable docs hub; agents and operators know where specs live.

| Ticket | Deliverable |
|--------|-------------|
| BUILD-000 | `INDEX.md`, `AGENTS.md`, `README.md`, `SETUP.md`, this build-out set |
| BUILD-001 | `artifact-layout.md`, `json-schemas/` |
| BUILD-002 | `operator-gates.md` |
| BUILD-003 | `docs/pipeline/*/README.md` per stage area |
| BUILD-004 | `build-out/README.md`, `steps-forward.md`, `stage-registry.md`, `ticket-specs.md` |

**Verify:** New contributor can follow [SETUP.md](../../SETUP.md) without asking where specs are.

---

### Phase 1 — Shell and core library (BUILD-010–013)

**Goal:** Reproducible Python env, run workspace, LLM stage envelope.

| Ticket | Module / path | Spec |
|--------|---------------|------|
| BUILD-010 | `pyproject.toml`, `requirements.lock`, `scripts/bootstrap_venv.sh`, `tools/check_prerequisites.sh` | [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md) |
| BUILD-011 | `config.py`, `config/app.defaults.json` | [config-keys.md](../cross-cutting/config-keys.md) |
| BUILD-012 | `run_context.py`, `file_store.py` | [artifact-layout.md](../cross-cutting/artifact-layout.md) |
| BUILD-013 | `llm_runner.py`, `analysis_stage.py`, `context_volley.py`, `prompt_validation.py` | [context-padding.md](../cross-cutting/context-padding.md) |

**Verify:** `./tools/check_prerequisites.sh` passes; `python -c "import interview_mux"` from `.venv`.

**Context7:** Query FastAPI/OpenAI/jsonschema at pinned versions before editing deps.

---

### Phase 1.5 — Web GUI and operator platform (BUILD-014–018, 056–057)

**Goal:** Operator runs pipeline from browser; gates G0–G2; centralized logs. **No config-file WAV path** for normal use — source audio is discovered under `ASSETS/` and executions persist under `ASSETS/executions/` for resume after `./scripts/run.sh` ([assets-and-executions.md](../cross-cutting/assets-and-executions.md)).

| Ticket | Module | Workflow doc |
|--------|--------|----------------|
| BUILD-014 | `web/server.py`, `web/static/*`, `scripts/run.sh` | [gui-surface-map.md](../workflows/gui-surface-map.md) · [assets-and-executions.md](../cross-cutting/assets-and-executions.md) |
| BUILD-015 | `web/runner.py` → `gui_job.json` | [api-reference.md](../workflows/api-reference.md) |
| BUILD-016 | `session_log.py`, `RunContext.log()` | `.cursor/rules/interview-helper-mux.mdc` |
| BUILD-017 | `gates.py`, gate panels | [operator-gates.md](../workflows/operator-gates.md) |
| BUILD-018 | `transcript_review.py`, `analysis_memory.py`, `analysis_orchestrator.py` | [analysis-memory.md](../cross-cutting/analysis-memory.md) |
| BUILD-056 | `nle_state.py` | [audio_editing/README.md](../pipeline/audio_editing/README.md) |
| BUILD-057 | `gui_session.py` | [api-reference.md](../workflows/api-reference.md) |

**Verify:** `./scripts/run.sh` → home screen lists WAVs under `ASSETS/` → start execution from picker → execute analysis → G0 panel → log panel shows `gui_log.jsonl` lines → stop server → relaunch → **Previous executions** resumes same `exec_*` folder.

---

### Phase 2 — Shared analysis (BUILD-019–028)

**Goal:** One interview → transcript, understanding, segments, gap report; G1 VO pickup.

| Order | Stage ids | Module | Ticket |
|-------|-----------|--------|--------|
| optional | `audio_preclean` | `audio_preclean.py` | BUILD-019 |
| 1 | `ingest` | `ingest.py` | BUILD-020 |
| 2 | `transcribe` | `transcribe_aws.py` | BUILD-021 |
| 3 | `transcript_review_build`, `transcript_review` | `transcript_review.py` | BUILD-018 |
| 4–5 | `speaker_roles`, `content_context` | `understanding.py` | BUILD-022–023 |
| 6–7 | `boundary_detection`, `segment_classification` | `segmentation.py` | BUILD-024 |
| 8–9 | `missing_framing`, `optimal_questions` | `gaps.py` | BUILD-025–026 |
| — | `vo_ingest` | `gaps.py` | BUILD-027 |
| CLI | `run_analysis` | `pipeline.py`, `tools/run_analysis.py` | BUILD-028 |

**Gate G1** after `optimal_questions` when `delivery: record` lines lack WAV in `vo_pickup/`.

**Verify:** [smoke-test.md](../workflows/smoke-test.md) analysis section; `analysis_complete.json` exists.

---

### Phase 3a — Flow 1 full master (BUILD-029–036)

**Goal:** Ranked full episode → `flow_1_master/master.wav` via `mix_flow1` (BUILD-065–066; legacy `mux_flow1` alias for single-stage rerun).

| Stage | Ticket | Prompt |
|-------|--------|--------|
| `topic_coverage_audit`, `narrative_arc_plan` | BUILD-029–030 | `selection/topic-coverage-audit`, `narrative-arc-plan` |
| `full_master_ranking`, `transitions`, `podcast_sfx_brief` | BUILD-031–033 | `selection/*`, `assembly/*` |
| `elevenlabs_sfx_flow1` | BUILD-034 | ElevenLabs REST |
| `edl_flow1`, `mux_flow1`, `master_flow1` | BUILD-035–036 | — |

**Requires:** G1 clear, `selected_flow: flow1` (G2). **Profile gate (BUILD-081):** `meta.operator_verified: true` in `analysis_state.json` before `topic_coverage_audit` — [operator-gates.md](../workflows/operator-gates.md#profile-gate--flow-1-extended-build-081).

**Verify:** `python tools/run_flow.py --flow flow1` + `verify_master.py` on `master.wav`.

---

### Phase 3b — Flow 2 highlights (BUILD-040–044)

**Goal:** ≤5 clips → `flow_2_highlights/master.wav`.

| Stage | Ticket |
|-------|--------|
| `highlight_selection`, `sfx_brief`, `elevenlabs_sfx_flow2`, `mux_flow2`, `master_flow2` | BUILD-040–044 |

**Verify:** smoke-test Flow 2 section.

---

### Phase 3c — Flow 3 publishing (BUILD-045–046, 080) — **shipped**

**Goal:** Third-person show description JSON + markdown export; no audio.

| Stage | Ticket |
|-------|--------|
| `podcast_show_description` | BUILD-045 |
| `export_show_description` | BUILD-046 |
| Pipeline/CLI/GUI wire-up | BUILD-080 |

**Spec:** [publishing/README.md](../pipeline/publishing/README.md)

**Verify:** `run_flow.py --flow flow3`; `flow_3_description/show_description.json` + `.md`; no `master.wav`.

---

### Phase 4 — QA tooling (BUILD-050–055)

**Goal:** CLI wrappers, ffprobe smoke, pytest on prompts and transcript review.

**Verify:** `pytest`; [testing-and-verification.md](./testing-and-verification.md).

---

### Phase 5 — Coherent sound design (BUILD-060–066) — **done**

**Goal:** Sound Design Plan, reusable assets, real mix replacing v1 brief + speech concat.

**Spec:** [sound-design.md](../cross-cutting/sound-design.md) · **Prompts:** [prompts/sound_design/](../prompts/sound_design/)

**Shipped:** `sound_design_palettes`, flow plans, `elevenlabs_prompt_craft`, `mix_flow1`/`mix_flow2` in `pipeline.py` + GUI; G1.5 prompt review panel.

**Verify:** `master.wav` contains beds + stingers + VO; one WAV per `asset_id`; ducking applied.

---

### Phase 6 — Podcast quality wiring (BUILD-067–072) — **done**

**Goal:** Honest EDL (gaps + VO), NLE overrides, assembly preview, LUFS QA, pre-clean offers.

**Spec:** [podcast-quality-roadmap.md](../cross-cutting/podcast-quality-roadmap.md)

**Shipped:** `edl_flow1` with VO/gap placements; NLE overrides; `assembly_preview.wav`; `verify_master` LUFS/peak; pickup-scoped pre-clean GUI offers (BUILD-072).

**Verify:** Gap placements in EDL; `assembly_preview.wav` before SFX spend; `verify_master` LUFS/peak.

---

### Phase 7 — Intelligence and guardrails (BUILD-073, 082) — done

| Ticket | Deliverable | Status |
|--------|-------------|--------|
| BUILD-073 | Smart LLM routing — [llm-orchestration-implementation-handoff.md](../cross-cutting/llm-orchestration-implementation-handoff.md) | done |
| BUILD-081 | Profile gate before Flow 1 extended stages | done — [operator-gates.md](../workflows/operator-gates.md#profile-gate--flow-1-extended-build-081) |
| BUILD-082 | `source_acoustic_profile` stage | done |

**Optional R&D:** [value-analysis/](../pipeline/value-analysis/) — not on default path.

---

## Implementation workflow (per ticket)

**Cursor Agent:** Open commands live in [remaining-build-commands.md](./remaining-build-commands.md) (**current queue**). Historical step prompts (#0–#20) remain in [steps-forward.md](./steps-forward.md#cursor-agent--how-to-use-this-page). Use **one command per agent chat**.

1. Pick the next command from [remaining-build-commands.md](./remaining-build-commands.md).
2. Read acceptance in [ticket-specs.md](./ticket-specs.md).
3. Read stage row in [stage-registry.md](./stage-registry.md).
4. Use **Context7** for any third-party API you call.
5. Implement; mirror operator messages via `ctx.log()` only.
6. Update docs per [doc-maintenance.md](./doc-maintenance.md).
7. Run verification from [testing-and-verification.md](./testing-and-verification.md).
8. Mark ticket **done** / **partial** in [README.md](./README.md); clear gap row in [repository-map.md](./repository-map.md).

---

## Definition of done (entire app)

Repository-wide checklist (also in [steps-forward.md](./steps-forward.md)):

- [x] ASSETS-first operator path: WAV in `ASSETS/`, GUI picker, full state under `ASSETS/executions/exec_*`, resume after `./scripts/run.sh` ([assets-and-executions.md](../cross-cutting/assets-and-executions.md); GUI: `src/interview_mux/web/server.py`, `gui_session.py`)
- [ ] Fresh clone: SETUP → bootstrap → check_prerequisites → smoke-test for **flow1, flow2, and flow3** — manual: [definition-of-done-signoff.md](./definition-of-done-signoff.md)
- [x] All three flows selectable at G2 and runnable via CLI + GUI (`flow1` \| `flow2` \| `flow3` in `gates.py`, `cli.py`, `server.py`, `web/runner.py`)
- [x] `master.wav` for flow1/2 includes VO + SFX mix per north star (`mix_flow1`/`mix_flow2` in `pipeline.py` → `assembly_flow1.py` / `assembly_flow2.py` / `sound_design.py`, BUILD-065–066)
- [x] `verify_master` enforces LUFS/true peak per [evaluation-metrics.md](../cross-cutting/evaluation-metrics.md) (`tools/verify_master.py`, `src/interview_mux/master_qc.py`)
- [x] Pre-clean offered at documented checkpoints; never auto-enabled (`stages/audio_preclean.py`, `POST …/preclean-offer` in `web/server.py`; BUILD-019 + BUILD-072)
- [x] [stage-registry.md](./stage-registry.md) matches `pipeline.py` and `web/stages.py` (`EXECUTABLE_ORDER` parity — see signoff §5)
- [x] No stale rows in [repository-map.md](./repository-map.md) gap table (shipped items cleared Command 9)
- [x] Smart LLM routing shipped (BUILD-073); optional follow-ups in [remaining-build-commands.md](./remaining-build-commands.md)

---

## Related

- [full-application-flow.md](./full-application-flow.md) — operator journey diagram
- [pipeline.md](../pipeline.md) — three flows overview
- [logic-tree.md](../logic-tree.md) — gap detection decisions
