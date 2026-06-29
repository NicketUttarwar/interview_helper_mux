# LLM guidance program — quality-first index

**Objective:** Maximum quality of every LLM artifact and audio integration step. Token budget is not a constraint for prompt depth.

**Living scorecard:** [stage-quality-scorecard.md](./stage-quality-scorecard.md)

**Architecture:** [LLM-ANALYSIS-ARCHITECTURE.md](../../LLM-ANALYSIS-ARCHITECTURE.md) §18 Flow hardening, §19 Guidance program, §20 Loop policy

---

## Criticality tiers

| Tier | Stages | Why |
|------|--------|-----|
| **P0** | `speaker_roles`, `content_context`, `boundary_detection`, `segment_classification`, `content_brief_reanchor` | Errors poison all downstream work |
| **P1** | `missing_framing`, `optimal_questions`, `topic_coverage_audit`, `narrative_arc_plan`, `full_master_ranking`, `edl_narrative_audit` | Listener comprehension |
| **P2** | `sound_design_palettes`, `sound_design_plan_flow1/2`, `sfx_prompt_craft`, `mmaudio_sfx_flow*`, `mix_flow*` | API spend + master quality |
| **P3** | `transitions`, `highlight_selection`, `podcast_show_description` | Polish; operator-recoverable |
| **P4** | G0, `source_acoustic_profile`, `disfluency_extract`, `sound_design_vo_finalize`, `assembly_preview` | Upstream non-LLM gates |

---

## Quality layers (every LLM stage)

| Layer | Module / doc | Purpose |
|-------|----------------|---------|
| System prompt | `docs/prompts/**/*.system.txt` | Task rules + schema |
| Preamble | `analysis-preamble.system.txt` | Envelope, memory, sonic constitution |
| Examples | `_shared/examples/*.md` | Good/bad patterns |
| Scenario atlas | `interview-scenario-atlas.md` | Diverse English interview formats |
| Preflight | `llm_preflight.py` | Block API call when upstream missing |
| Schema | `prompt_validation.py` | JSON shape |
| Deterministic lint | `deterministic_lint.py` | Code checks before merge |
| Arbiter rubric | `arbiter-rubrics/*.json` | Editorial accept/reject |
| Arbiter | `llm_arbiter.py` | Economy-tier routing |
| Cross-validate | `artifact_cross_validate.py`, `sdp_cross_validate.py` | ID-set consistency |
| Attempt budget | `attempt_budget.py` | Loop circuit-breaker |
| Flow hardening | `llm_flow_hardening.py` | Critical vs soft stages |
| Local volley framer | `local_volley_framer.py` | On-device volley framing before OpenAI (`prepare_volley_for_llm`) |
| Required response format | `required_response_format.py` | Dual-inject envelope/artifact skeleton + null rules (system + final volley turn) |
| Null field policy | `null_field_policy.py` | JSON `null` acknowledgment, volley exclusion, critical-field hard stops |
| Stage guidance | `stage_guidance.py` | GUI journey phase copy and gate CTAs (`stages[].guidance`) |
| Placement QA | `placement_qa.py` | Post-SFX hints; `apply_placement_adjustments` at mix |

---

## Per-stage scorecard template

For each stage row in [stage-quality-scorecard.md](./stage-quality-scorecard.md):

| Column | Values |
|--------|--------|
| Prompt | `shipped` \| `needs_expand` |
| Arbiter rubric | `shipped` \| `missing` |
| Deterministic lint | `shipped` \| `missing` |
| Cross-validate | checkpoint id or `—` |
| Preflight | `shipped` \| `partial` \| `missing` |
| Runtime examples | `full` \| `compact` \| `doc_only` |
| Loop budget | `shipped` \| `partial` |

---

## PR delivery map

| PR | Workstreams |
|----|-------------|
| PR1 | Program index, scorecard, scenario atlas, preamble |
| PR2 | Loop prevention (`attempt_budget.py`) |
| PR3 | P0 deep prompts + arbiter rubrics + lint |
| PR4 | P1 narrative stages |
| PR5 | P2 sound cross-validate + spend gates |
| PR6 | P3 polish + specialists + full example injection |
| PR7 | Upstream contracts, placement QA, framer, legacy deprecation |
| PR8 | Verification + operator docs |

---

## Ticket index (GUIDE-001–080)

Grouped in [ticket-specs.md](../build-out/ticket-specs.md) under **Wave — LLM guidance**.

| Range | Workstream |
|-------|------------|
| GUIDE-001–010 | Program foundation, preamble, scenario atlas |
| GUIDE-011–020 | Loop prevention, attempt budget |
| GUIDE-021–040 | Arbiter rubrics + deterministic lint |
| GUIDE-041–060 | Per-stage prompt expansion (P0–P3) |
| GUIDE-061–070 | Cross-validate, preflight, spend gates |
| GUIDE-071–080 | Placement QA, monitoring, verification |

---

## Related

- [analysis-stage-matrix.md](../prompts/analysis-stage-matrix.md)
- [arbiter-stage-rubrics.md](../prompts/_shared/arbiter-stage-rubrics.md)
- [guardrails-and-edge-cases.md](../prompts/sound_design/guardrails-and-edge-cases.md)
- [post-generation-placement.md](./post-generation-placement.md)
