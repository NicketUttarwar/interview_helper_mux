# Build-out index

Numbered tickets and **full-repository build-out specs** for agent implementation.

## Start here

| Doc | Purpose |
|-----|---------|
| [implementation-guide.md](./implementation-guide.md) | **Master build plan** — all phases, waves, verification |
| [steps-forward.md](./steps-forward.md) | Prioritized backlog + **Cursor Agent copy-paste prompts** per step |
| [full-application-flow.md](./full-application-flow.md) | End-to-end operator + system journey |
| [stage-registry.md](./stage-registry.md) | Every stage id, module, artifact, status |
| [ticket-specs.md](./ticket-specs.md) | Acceptance criteria per BUILD ticket |
| [repository-map.md](./repository-map.md) | Repo layout ↔ code ↔ docs |
| [../cross-cutting/assets-and-executions.md](../cross-cutting/assets-and-executions.md) | ASSETS input picker, executions, resume |
| [testing-and-verification.md](./testing-and-verification.md) | How to verify each wave |
| [doc-maintenance.md](./doc-maintenance.md) | Docs to update in the same PR as code |

North star for mix quality: [podcast-quality-roadmap.md](../cross-cutting/podcast-quality-roadmap.md).

## Legend

| Status | Meaning |
|--------|---------|
| **done** | Shipped in repo |
| **partial** | Some acceptance criteria met; see notes |
| **planned** | Spec in docs; not in code |
| **gate** | Operator checkpoint (may have GUI + code) |

---

## Wave 0 — Docs and entrypoints

| Ticket | Title | Deliverable | Status |
|--------|-------|-------------|--------|
| BUILD-000 | Doc hub + agent guide | `docs/INDEX.md`, `AGENTS.md`, `README.md`, `SETUP.md`, [repository-map.md](./repository-map.md) | done |
| BUILD-001 | Artifact layout + schemas | `docs/cross-cutting/*`, `json-schemas/` | done |
| BUILD-002 | Operator gates | `docs/workflows/operator-gates.md` | done |
| BUILD-003 | Stage READMEs | `docs/pipeline/*/README.md` | done |
| BUILD-004 | Build-out index | this file, [steps-forward.md](./steps-forward.md), [implementation-guide.md](./implementation-guide.md), [stage-registry.md](./stage-registry.md), [ticket-specs.md](./ticket-specs.md), [full-application-flow.md](./full-application-flow.md), [testing-and-verification.md](./testing-and-verification.md), [doc-maintenance.md](./doc-maintenance.md) | done |

---

## Wave 1 — Shell and core library

| Ticket | Title | Module / path | Status |
|--------|-------|---------------|--------|
| BUILD-010 | pyproject + venv + **anchor lock** | `pyproject.toml`, `requirements.txt`, `requirements.lock`, `scripts/bootstrap_venv.sh`, `pip-audit` in `check_prerequisites.sh` — [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md) | done |
| BUILD-011 | Config loader | `src/interview_mux/config.py`, `config/` | done |
| BUILD-012 | Run workspace | `run_context.py`, `file_store.py` | done |
| BUILD-013 | OpenAI runner + stage envelope | `stages/llm_runner.py`, `analysis_stage.py`, `context_volley.py`, `prompt_validation.py` | done |

---

## Wave 1.5 — Web GUI and operator platform (shipped)

| Ticket | Title | Module | Status |
|--------|-------|--------|--------|
| BUILD-014 | FastAPI server + static UI | `web/server.py`, `web/static/*`, `scripts/run.sh` | done |
| BUILD-015 | Background job runner | `web/runner.py` → `gui_job.json` | done |
| BUILD-016 | Centralized operator log | `session_log.py`, `RunContext.log()` | done |
| BUILD-017 | Gates G0–G2 | `gates.py`, GUI gate panels | done (G2: flow1 \| flow2 \| flow3) |
| BUILD-081 | Profile gate (Flow 1 extended) | `gates.py`, GUI stage lock + gate hints | done |
| BUILD-018 | Transcript review + analysis memory | `transcript_review.py`, `analysis_memory.py`, `analysis_orchestrator.py` | done |
| BUILD-056 | NLE editor state | `nle_state.py`, `/api/runs/.../nle` | done (feeds BUILD-068) |
| BUILD-057 | GUI session / active run | `gui_session.py`, `/api/session` | done |

**Docs:** [gui-surface-map.md](../workflows/gui-surface-map.md) · [api-reference.md](../workflows/api-reference.md)

---

## Wave 2 — Shared analysis

| Ticket | Title | Module | Status |
|--------|-------|--------|--------|
| BUILD-019 | Audio pre-clean (optional) | `stages/audio_preclean.py` | done (GUI offers: BUILD-072) |
| BUILD-020 | Ingest | `stages/ingest.py` | done |
| BUILD-021 | AWS Transcribe | `stages/transcribe_aws.py` | done |
| BUILD-022 | Speaker roles | `understanding.py` | done |
| BUILD-023 | Content context | `understanding.py` | done |
| BUILD-024 | Segmentation | `segmentation.py` | done |
| BUILD-025 | Missing framing | `gaps.py` | done |
| BUILD-026 | Optimal questions + gap report | `gaps.py` | done |
| BUILD-027 | VO ingest | `gaps.ingest_vo_pickup` | done |
| BUILD-028 | Analysis CLI + pipeline | `tools/run_analysis.py`, `pipeline.run_analysis` | done |
| BUILD-082 | Source acoustic profile | `understanding.py` → `understanding/source_acoustic_profile.json` | done |

**Smart LLM routing:** [llm-orchestration.md](../cross-cutting/llm-orchestration.md), [llm-stage-model-matrix.md](../cross-cutting/llm-stage-model-matrix.md) — **BUILD-073** done (`model_registry`, `llm_arbiter`, `llm_subtasks`)

**Gate G1** after BUILD-028 — [operator-gates.md](../workflows/operator-gates.md)

---

## Wave 3a — Flow 1 (full master podcast)

| Ticket | Title | Module | Status |
|--------|-------|--------|--------|
| BUILD-029 | Topic coverage | `analysis_flow1_extended.py` | done |
| BUILD-030 | Narrative arc | `analysis_flow1_extended.py` | done |
| BUILD-031 | Full master ranking | `selection_flow1.py` | done |
| BUILD-032 | Transitions | `selection_flow1.py` | done |
| BUILD-033 | Podcast SFX brief | `selection_flow1.py` | done (v1 brief; superseded by BUILD-060+) |
| BUILD-034 | ElevenLabs SFX | `sfx_elevenlabs.py`, `elevenlabs_rest.py` | done (v1 per-cue REST) |
| BUILD-035 | Mux assembly | `assembly_flow1.py` | done (**v1 speech-only** concat) |
| BUILD-036 | Master export | `mastering.py` | done |

---

## Wave 3b — Flow 2 (highlight reel)

| Ticket | Title | Module | Status |
|--------|-------|--------|--------|
| BUILD-040 | Highlight selection | `selection_flow2.py` | done |
| BUILD-041 | SFX brief | `selection_flow2.py` | done (v1 brief) |
| BUILD-042 | ElevenLabs SFX | `sfx_elevenlabs.py` | done |
| BUILD-043 | Micro-assembly | `assembly_flow2.py` | done |
| BUILD-044 | Master export | `mastering.py` | done |

**Gate G2** before Wave 3 — `selected_flow` in `run_meta.json` (`flow1` \| `flow2` \| `flow3`)

---

## Wave 3c — Flow 3 (publishing copy)

| Ticket | Title | Module | Status |
|--------|-------|-------------|--------|
| BUILD-045 | Podcast show description | `publishing_flow3.py` | done |
| BUILD-046 | Show description export | JSON → `show_description.md` | done |
| BUILD-080 | Flow 3 wire-up | `pipeline.py`, `cli.py`, `web/runner.py`, `web/server.py`, `web/stages.py` | done |

**Spec:** [pipeline/publishing/README.md](../pipeline/publishing/README.md) · **Prompt:** [podcast-show-description.system.txt](../prompts/publishing/podcast-show-description.system.txt)

---

## Wave 4 — QA tooling

| Ticket | Title | Module | Status |
|--------|-------|--------|--------|
| BUILD-050 | Mastering module | `mastering.py` | done |
| BUILD-051 | Flow CLI | `tools/run_flow.py`, `cli.flow_cmd` | done (flow1 \| flow2 \| flow3) |
| BUILD-052 | verify_master | `tools/verify_master.py`, `master_qc.py` | done |
| BUILD-053 | Smoke test doc | `docs/workflows/smoke-test.md` | done |
| BUILD-054 | Prompt validation tests | `tests/test_prompt_validation.py` | done |
| BUILD-055 | Transcript review tests | `tests/test_transcript_review.py` | done |

---

## Wave 5 — Coherent sound design (planned)

**Spec:** [sound-design.md](../cross-cutting/sound-design.md) · **Prompts:** [prompts/sound_design/README.md](../prompts/sound_design/README.md)

| Ticket | Title | Deliverable |
|--------|-------|-------------|
| BUILD-060 | SDP schema + empty plan init | done — `sound_design_plan.schema.json`, init in `ensure_analysis_workspace` |
| BUILD-061 | Theme palettes stage | done — `sound_design_palettes` after `segment_classification` |
| BUILD-062 | Flow 1 plan stage | done — `sound_design_plan_flow1` after `transitions`; merges `assets` + `flow_plans.flow1` into SDP; cue `asset_id` link validation |
| BUILD-063 | Flow 2 plan stage | done — `sound_design_plan_flow2` after `highlight_selection`; merges `assets` + `flow_plans.flow2` into SDP; cue `asset_id` link validation |
| BUILD-064 | ElevenLabs prompt craft + generate | done — craft → `elevenlabs_prompts.json`; REST one WAV per `asset_id` in `sound_design/assets/` |
| BUILD-065 | Mix engine | **done** — `sound_design.py`; `mix_flow1` / `mix_flow2`; VO + beds + stingers + ducking |
| BUILD-066 | Pipeline + GUI wire-up | **done** — `mix_flow1`/`mix_flow2` in pipeline + GUI; v1 briefs legacy-only; G1.5 prompt review panel |

Acceptance details: see historical BUILD-060–066 notes in git history or [sound-design.md](../cross-cutting/sound-design.md).

---

## Wave 6 — Podcast quality wiring (planned)

**Spec:** [podcast-quality-roadmap.md](../cross-cutting/podcast-quality-roadmap.md)

| Ticket | Title | Deliverable |
|--------|-------|-------------|
| BUILD-067 | Gap report → EDL | **done** — `edl_flow1` includes `vo_pickup` + gap placements |
| BUILD-068 | NLE → selection/EDL | **done** — `nle_edits.json` applied in `full_master_ranking` + `edl_flow1` (`selection.json`, EDL bounds) |
| BUILD-069 | Assembly preview | **done** — `flow_1_master/assembly_preview.wav` (speech + VO) + GUI listen action before ElevenLabs |
| BUILD-070 | verify_master LUFS/peak | **done** — `master_qc.py`; ffmpeg loudnorm measurement; CLI + post-flow GUI log |
| BUILD-071 | Mastering measurement | **done** — `mastering_bus.py` pyloudnorm on assembly; ffmpeg limiter uses BUILD-070 targets |
| BUILD-072 | Pre-clean quality offers | **done** — GUI prompts at roadmap checkpoints; `run_meta.json` scope + `gui_log.jsonl` |

---

## Wave 7 — Intelligence and guardrails (planned / optional)

| Ticket | Title | Deliverable |
|--------|-------|-------------|
| BUILD-073 | Smart LLM routing | done — `model_registry.py`, `llm_arbiter.py`, `llm_subtasks.py`; wired in `analysis_stage.py` |

**Optional R&D:** [pipeline/value-analysis/](../pipeline/value-analysis/) — not on the default delivery path; see [future-proofing.md](../roadmap/future-proofing.md).

---

## Dependency order

```
000 → 001 → 002 → 003 → 004
010 → 011 → 012 → 013
014 → 015 → 016 → 017 → 018 → 056 → 057   (platform; can parallelize after 012)
019 (optional) → 020 → 021 → 022…028 → [G1] → [G2]
029…036 (flow1) OR 040…044 (flow2) OR 045…046 + 080 (flow3)
050 → 051 → 052 → 053
054 → 055 (tests; ongoing)
060 → 061 → 062 & 063 → 064 → 065 → 066
067 → 068 → 069 (parallel with 065 where possible)
070 → 071
019 + 072 (pre-clean + offers)
073, 081, 082 (parallel after 013 / 028 when staffed)
```

Wave 5 can start after BUILD-013 and BUILD-028; flow tickets 062–063 require G2 flow selection. Wave 6 assembly tickets should land before or with BUILD-065 for honest `master.wav`.

---

## How to use this index

1. **Agents (building code):** `AGENTS.md` → [implementation-guide.md](./implementation-guide.md) → [steps-forward.md](./steps-forward.md) (**paste Agent prompt for your step #**) → [ticket-specs.md](./ticket-specs.md) for your BUILD id → [stage-registry.md](./stage-registry.md) + pipeline stage README.
2. **Agents (understanding the app):** [full-application-flow.md](./full-application-flow.md) → [pipeline.md](../pipeline.md) → [logic-tree.md](../logic-tree.md).
3. **Operators:** [operator-stage-checklists.md](../workflows/operator-stage-checklists.md) — not ticket IDs.
4. **When shipping a ticket:** [doc-maintenance.md](./doc-maintenance.md) checklist; update status here, [ticket-specs.md](./ticket-specs.md) checkboxes, [repository-map.md](./repository-map.md) gap table.
5. **Verify:** [testing-and-verification.md](./testing-and-verification.md) + [smoke-test.md](../workflows/smoke-test.md).
