# Mastering integration backlog

Migration backlog from TBIY / scattered master-construction → Unified Mastering Process. Strategy authority: [mastering-process.md](./mastering-process.md).

**Disposition legend:** `migrate` (rewire under mastering) · `rename` (rebrand helpers) · `delete` (remove after cutover) · `keep-hint` (descriptive only) · `docs-done` (specified here; code later).

Code cutover is **not** implied by this doc — implement per stage with fail-open until `mastering_plan` is authoritative.

---

## A. Core TBIY / profile

| # | Touchpoint | Disposition | Notes |
|---|------------|-------------|-------|
| A1 | `production_style` dualism (`documentary_interview` / `tbiy_narrative`) | migrate | Operator hint only; Shape Engine owns structure |
| A2 | [`production_profile.py`](../../src/interview_mux/production_profile.py) `is_tbiy` / `prompt_variant` | migrate | Prefer mastering-aware prompt selection when plan exists |
| A3 | [`tbiy_conformance.py`](../../src/interview_mux/tbiy_conformance.py) | migrate | Fold into Wave-6/3 research signals (descriptive); remove five-act/moat *enforcement* |
| A4 | [`tbiy_mix.py`](../../src/interview_mux/tbiy_mix.py) | rename | → mastering mix helpers; keep pan / duck / speech-wins |
| A5 | [`gates_tbiy.py`](../../src/interview_mux/gates_tbiy.py) G1.5 | rename | Mastering Realization preview gate (not TBIY-branded) |
| A6 | `production_profiles.tbiy_narrative`, `mix.tbiy_narrative` | migrate | → `mastering.*` keys; sync `config/templates/` |

## B. Topology / brief / episode structure

| # | Touchpoint | Disposition | Notes |
|---|------------|-------------|-------|
| B1 | [`source_topology.py`](../../src/interview_mux/source_topology.py) + `flow_adaptation` | migrate | Feed Wave 2; stop seeding TBIY modes as directives |
| B2 | [`delivery_brief.py`](../../src/interview_mux/delivery_brief.py) | keep-hint | Soft hints → Wave 4; plan overrides |
| B3 | [`episode_structure.py`](../../src/interview_mux/episode_structure.py) packs | keep-hint | Candidate catalog for Shape Engine, not authority |
| B4 | Schemas: flow_adaptation, delivery_brief, source_topology, episode_structure | migrate | Add mastering_plan refs; deprecate `tbiy_conformance` as authority |

## C. LLM stages + prompts

| # | Touchpoint | Disposition | Notes |
|---|------------|-------------|-------|
| C1–C13 | 13 `*.tbiy.system.txt` prompts | migrate | Retire “never leave TBIY compass”; follow `mastering_plan` when present |
| C14 | [`llm_interaction_registry.py`](../../src/interview_mux/llm_interaction_registry.py) | migrate | Add research-field + Shape Engine + mint/edit/clarify IDs |
| C15 | `models.tiers` / stage tier map in `app.defaults.json` | migrate | Economy/standard/flagship by Shape Engine role |
| C16 | Clarifying-question API + GUI | migrate | Auto-resolve from artifacts first |

**TBIY prompt files to migrate:**

- `understanding/content-context.tbiy.system.txt`
- `understanding/content-brief-reanchor.tbiy.system.txt`
- `segmentation/segment-classification.tbiy.system.txt`
- `interviewer-gap/missing-framing.tbiy.system.txt`
- `interviewer-gap/optimal-questions.tbiy.system.txt`
- `selection/full-master-ranking.tbiy.system.txt`
- `selection/topic-coverage-audit.tbiy.system.txt`
- `selection/narrative-arc-plan.tbiy.system.txt`
- `selection/edl-narrative-audit.tbiy.system.txt`
- `assembly/transitions.tbiy.system.txt`
- `sound_design/theme-palettes.tbiy.system.txt`
- `sound_design/plan-flow1.tbiy.system.txt`
- `sound_design/sfx-prompt-craft.tbiy.system.txt`

**New prompts (contracts landed):** `docs/prompts/mastering/` — mint, edit, clarify, meta-architect, L1–L5 seeds, capability modules, synthesize, polish.

## D. Selection / EDL / mix realization

| # | Touchpoint | Disposition | Notes |
|---|------------|-------------|-------|
| D1 | [`stages/selection.py`](../../src/interview_mux/stages/selection.py) + creative_delivery | migrate | Bind include/exclude to plan; don’t force min-exclude against plan |
| D2 | [`stages/analysis_extended.py`](../../src/interview_mux/stages/analysis_extended.py) narrative arc | migrate | Candidate only / Shape Engine consumer |
| D3 | [`edl_narrative_qc.py`](../../src/interview_mux/edl_narrative_qc.py), [`deterministic_lint.py`](../../src/interview_mux/deterministic_lint.py) | migrate | Validate against plan; drop hard five-act/moat unless plan chose them |
| D4 | [`sound_design.py`](../../src/interview_mux/sound_design.py) + SDP stages | migrate | Component inclusion from plan |
| D5 | [`stages/mastering.py`](../../src/interview_mux/stages/mastering.py) / assembly | migrate | Phase Realization + polish audit hook; cold_open as leading EDL |

## E. Gates / GUI / journey

| # | Touchpoint | Disposition | Notes |
|---|------------|-------------|-------|
| E1 | PickupSpeaker + VoPickup | keep-hint | Keep pickup invariant; rebrand TBIY copy |
| E2 | PreviewPickup / G1.5 | rename | Realization preview gate |
| E3 | FlowAdaptationCard / DeliveryBriefCard / profileForm | migrate | Mount Mastering Research / Plan / clarify UI (or replace) |
| E4 | journey_state, stage_steps, web/server, web/stages | migrate | Stage ids + APIs for mastering artifacts + clarify Q&A |
| E5 | Operator docs (gates, gui-surface-map, checklists, smoke-test) | migrate | Point at Mastering Process |

## F. Tests / fixtures / docs sweep

| # | Touchpoint | Disposition | Notes |
|---|------------|-------------|-------|
| F1 | `tests/fixtures/tbiy/*`, `test_tbiy_*` | migrate | → mastering fixtures / excellence-filter cases |
| F2 | stage-volley-matrix, delivery-quality matrix, config-keys, speech-to-speech VO | migrate | Add mastering rows; note TBIY heritage |
| F3 | artifact_root_cause / lifecycle `tbiy_affected` | rename | → `mastering_affected` |
| F4 | [tbiy-production-profile.md](./tbiy-production-profile.md) | docs-done | Historical; points here |
| F5 | INDEX / AGENTS / NORTH_STAR / episode-architecture-spine | docs-done | Link Mastering Process |

## G. Quality Hardening layer

Adds reliability gates on top of A–F. Canon: [mastering-quality-hardening.md](./mastering-quality-hardening.md). Every gate ships `advisory` (fail-open) and flips to `authoritative` only after corpus evidence.

### G-a. Deterministic compilers (no new LLM required)

| # | Touchpoint | Disposition | Notes |
|---|------------|-------------|-------|
| G1 | [`mastering_research_router.py`](../../src/interview_mux/mastering_research_router.py) | landed | Field routing decisions + wave budgets → `mastering/research/routing.json` |
| G2 | [`mastering_context_compiler.py`](../../src/interview_mux/mastering_context_compiler.py) | landed | Evidence packets with provenance + token budget + truncation policy |
| G3 | [`mastering_diversity.py`](../../src/interview_mux/mastering_diversity.py) | landed | Pairwise candidate distance; remint below threshold |
| G4 | [`mastering_feasibility.py`](../../src/interview_mux/mastering_feasibility.py) | landed | Hard gate before auditions/synthesize ([spec](./mastering-feasibility.md)) |
| G5 | [`mastering_semantic_integrity.py`](../../src/interview_mux/mastering_semantic_integrity.py) | landed | Deterministic scans + LLM confirm hook ([spec](./mastering-semantic-integrity.md)) |
| G6 | [`mastering_pareto.py`](../../src/interview_mux/mastering_pareto.py) | landed | Frontier instead of single aggregate score |

### G-b. Policy and consent

| # | Touchpoint | Disposition | Notes |
|---|------------|-------------|-------|
| G7 | [`mastering_voice_clone.py`](../../src/interview_mux/mastering_voice_clone.py) | landed | Consent record, scopes, disclosure, audit trail |
| G8 | [`gap_vo_gates.py`](../../src/interview_mux/gap_vo_gates.py) | extended | `clone_consent_*` helpers + payload fields; guest clone always blocked |
| G9 | GUI G-VoiceRef consent surface | migrate | Scope checkboxes + disclosure + revoke on the existing voice-reference card |

### G-c. LLM surfaces

| # | Touchpoint | Disposition | Notes |
|---|------------|-------------|-------|
| G10 | `docs/prompts/mastering/critics/` (6 roles + arbiter) | landed | [multi-critic spec](./mastering-multi-critic.md) |
| G11 | `research-router.system.txt`, `eval-rubric-mint.system.txt`, `semantic-integrity.system.txt` | landed | Router / rubric / integrity confirm |
| G12 | [`polish-audit.system.txt`](../../docs/prompts/mastering/polish-audit.system.txt) | extended | Audio-grounded scoring + bounded remux directives |
| G13 | [`llm_interaction_registry.py`](../../src/interview_mux/llm_interaction_registry.py) | extended | `OH-*` ids for router, rubric, critics, arbiter, integrity, audio polish |

### G-d. Runtime wiring (lands with Shape Engine runtime)

| # | Touchpoint | Disposition | Notes |
|---|------------|-------------|-------|
| G14 | L0 emits `shape/eval_rubric.json` beside the agenda | pending-runtime | Every critic + polish scores against it |
| G15 | Diversity enforcement after L2 | pending-runtime | Remint loop bounded by agenda budget |
| G16 | Feasibility gate before auditions + synthesize | pending-runtime | `eligible_candidate_ids` is the allow-list |
| G17 | Micro-render audition pipeline | pending-runtime | Reuse `assembly.run_preview`; never full master per candidate |
| G18 | Parallel critics + flagship arbiter merge | pending-runtime | Extends `shape/cross_critique.json` |
| G19 | Pareto-filtered synthesize inputs | pending-runtime | Tradeoff named in `bespoke_rationale` |
| G20 | Audio-grounded polish + bounded remux near [`stages/mastering.py`](../../src/interview_mux/stages/mastering.py) | pending-runtime | `max_remux_rounds` default 2 |
| G21 | Prompt-edit promotion gate | landed (policy) | Run-local default; global promotion needs corpus + approval |

### G-e. Config, corpus, cutover

| # | Touchpoint | Disposition | Notes |
|---|------------|-------------|-------|
| G22 | `mastering.quality_hardening.*` in [`config/app.defaults.json`](../../config/app.defaults.json) | landed | Per-gate `mode` + budgets |
| G23 | [config-keys.md](./config-keys.md) | extended | Documents every hardening key |
| G24 | `tests/fixtures/mastering_quality/` | landed | Seven-axis taxonomy ([spec](./mastering-eval-corpus.md)) |
| G25 | `tests/test_mastering_quality_*.py` | landed | Compilers, voice policy, critic contracts, audition smoke |
| G26 | stage-volley-matrix + delivery-quality matrix rows | extended | Hardening stages listed |
| G27 | [smoke-test.md](../workflows/smoke-test.md) + operator checklists | extended | Consent, audition, polish loop steps |

---

## Cutover sequence (when coding)

1. Land schemas + prompt contracts (this workstream) — **done when linked from INDEX**
2. Soft-gate stages: research → shape → synthesize; fail-open if plan missing
3. Bind ranking/EDL/mix to plan
4. Flip lint/QC to plan-conditional
5. Retire TBIY enforcement modes and unused `.tbiy` forks after parity tests

### Hardening cutover waves (section G)

1. Docs + schemas + prompts
2. Deterministic compilers (G1–G6)
3. Voice-clone policy + gates (G7–G9)
4. Multi-critic L4 + per-run rubric (G10, G14, G18)
5. Micro-render auditions (G17)
6. Closed-loop polish remux (G12, G20)
7. Corpus + promotion gate (G21, G24, G25)
8. Flip each gate `advisory → authoritative` one at a time
