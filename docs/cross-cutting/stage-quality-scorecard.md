# Stage quality scorecard

Living tracker for the [LLM guidance program](./llm-guidance-program.md). Each row records whether a stage has the full quality stack: prompt depth, arbiter rubric, deterministic lint, cross-artifact validation, preflight, and runtime examples.

**Target after GUIDE program:** every LLM stage and every P4 upstream gate row shows `shipped` in the **Status** column.

**Legend**

| Column | Values |
|--------|--------|
| **Tier** | P0–P4 criticality ([llm-guidance-program.md](./llm-guidance-program.md)) |
| **Prompt** | `shipped` \| `needs_expand` |
| **Arbiter** | `shipped` \| `missing` \| `—` (non-LLM) |
| **Lint** | `shipped` \| `missing` \| `—` |
| **Crossval** | checkpoint id or `—` |
| **Preflight** | `shipped` \| `partial` \| `missing` \| `—` |
| **Examples** | `full` \| `compact` \| `doc_only` \| `missing` |
| **Status** | `shipped` (target) \| `in_progress` \| `blocked` |

---

## P0 — Foundation (errors poison downstream)

| Stage | Tier | Prompt | Arbiter | Lint | Crossval | Preflight | Examples | Status |
|-------|------|--------|---------|------|----------|-----------|----------|--------|
| `speaker_roles` | P0 | shipped | shipped | shipped | — | shipped | full | shipped |
| `content_context` | P0 | shipped | shipped | shipped | — | shipped | full | shipped |
| `boundary_detection` | P0 | shipped | shipped | shipped | — | shipped | full | shipped |
| `segment_classification` | P0 | shipped | shipped | shipped | `post_segmentation` | shipped | full | shipped |
| `content_brief_reanchor` | P0 | shipped | shipped | shipped | `post_reanchor` | shipped | full | shipped |

---

## P1 — Narrative comprehension

| Stage | Tier | Prompt | Arbiter | Lint | Crossval | Preflight | Examples | Status |
|-------|------|--------|---------|------|----------|-----------|----------|--------|
| `missing_framing` | P1 | shipped | shipped | shipped | `post_gaps` | shipped | full | shipped |
| `optimal_questions` | P1 | shipped | shipped | shipped | — | shipped | full | shipped |
| `topic_coverage_audit` | P1 | shipped | shipped | shipped | `pre_flow1` | shipped | full | shipped |
| `narrative_arc_plan` | P1 | shipped | shipped | shipped | — | shipped | full | shipped |
| `full_master_ranking` | P1 | shipped | shipped | shipped | `post_ranking` | shipped | full | shipped |
| `edl_narrative_audit` | P1 | shipped | shipped | shipped | `post_edl_audit` | shipped | full | shipped |

---

## P2 — Sound design + API spend

| Stage | Tier | Prompt | Arbiter | Lint | Crossval | Preflight | Examples | Status |
|-------|------|--------|---------|------|----------|-----------|----------|--------|
| `sound_design_palettes` | P2 | shipped | shipped | shipped | `post_sound_palettes` | shipped | full | shipped |
| `sound_design_plan_flow1` | P2 | shipped | shipped | shipped | `post_sound_plan_flow1` | shipped | full | shipped |
| `sound_design_plan_flow2` | P2 | shipped | shipped | shipped | `post_sound_plan_flow2` | shipped | full | shipped |
| `elevenlabs_prompt_craft` | P2 | shipped | shipped | shipped | `pre_elevenlabs_spend` | shipped | compact | shipped |
| `elevenlabs_sfx_flow1` | P2 | — | — | — | `pre_mix_flow1` | partial | doc_only | shipped |
| `elevenlabs_sfx_flow2` | P2 | — | — | — | `pre_mix_flow2` | partial | doc_only | shipped |
| `mix_flow1` | P2 | — | — | placement_apply | `pre_mix_flow1` | — | doc_only | shipped |
| `mix_flow2` | P2 | — | — | placement_apply | `pre_mix_flow2` | — | doc_only | shipped |
| `podcast_sfx_brief` | P2 (legacy) | shipped | shipped | shipped | — | shipped | compact | shipped |
| `sfx_brief` | P2 (legacy) | shipped | shipped | shipped | — | shipped | compact | shipped |

---

## P3 — Polish (operator-recoverable)

| Stage | Tier | Prompt | Arbiter | Lint | Crossval | Preflight | Examples | Status |
|-------|------|--------|---------|------|----------|-----------|----------|--------|
| `transitions` | P3 | shipped | shipped | shipped | `post_transitions` | shipped | full | shipped |
| `highlight_selection` | P3 | shipped | shipped | shipped | — | shipped | full | shipped |
| `podcast_show_description` | P3 | shipped | shipped | shipped | — | shipped | full | shipped |

---

## P4 — Upstream non-LLM gates

| Stage | Tier | Prompt | Arbiter | Lint | Crossval | Preflight | Examples | Status |
|-------|------|--------|---------|------|----------|-----------|----------|--------|
| `transcript_review_build` | P4 | — | — | — | — | — | doc_only | shipped |
| `transcript_review` (G0) | P4 | — | — | — | — | shipped | doc_only | shipped |
| `disfluency_extract` | P4 | — | — | — | — | — | doc_only | shipped |
| `disfluency_review` (G0.5) | P4 | — | — | — | — | — | doc_only | shipped |
| `source_acoustic_profile` | P4 | — | — | — | — | — | doc_only | shipped |
| `sound_design_vo_finalize` | P4 | — | — | — | — | partial | doc_only | shipped |
| `assembly_preview` | P4 | — | — | — | — | — | doc_only | shipped |

---

## Meta + specialists

| Stage | Tier | Prompt | Arbiter | Lint | Crossval | Preflight | Examples | Status |
|-------|------|--------|---------|------|----------|-----------|----------|--------|
| `_arbiter` | meta | shipped | — | — | — | — | doc_only | shipped |
| `comprehension_risk_blind` | P1 specialist | shipped | — | — | — | — | full | shipped |
| `theme_coverage_pass` | P0 specialist | shipped | — | — | — | — | full | shipped |
| `emphasis_coverage_pass` | P1 specialist | shipped | — | — | — | — | full | shipped |

---

## Module map

| Layer | Code / doc |
|-------|------------|
| Preflight | `src/interview_mux/llm_preflight.py` |
| Deterministic lint | `src/interview_mux/deterministic_lint.py` — generic keys fully implemented in `_lint_generic()` (coverage ratio, cross-refs, min rows, truncation/decompose) |
| Arbiter rubrics | `docs/prompts/_shared/arbiter-rubrics/*.json` · [arbiter-stage-rubrics.md](../prompts/_shared/arbiter-stage-rubrics.md) |
| Cross-validate | `src/interview_mux/artifact_cross_validate.py`, `sdp_cross_validate.py` |
| Attempt budget | `src/interview_mux/attempt_budget.py` |
| Flow hardening | `src/interview_mux/llm_flow_hardening.py` |
| Examples | `docs/prompts/_shared/examples/` |
| Scenario atlas | [interview-scenario-atlas.md](../prompts/_shared/interview-scenario-atlas.md) |
| Transcript quality | [transcript-quality-rubric.md](../prompts/_shared/transcript-quality-rubric.md) |
| Placement QA | [post-generation-placement.md](./post-generation-placement.md) |
| Placement apply (`placement_apply`) | `apply_placement_adjustments` in `placement_qa.py` at mix |

---

## Maintenance

When adding a stage to `STAGE_ARTIFACT_SCHEMAS`:

1. Add a row to the appropriate tier table above.
2. Add `docs/prompts/_shared/arbiter-rubrics/<stage_key>.json` and link from [arbiter-stage-rubrics.md](../prompts/_shared/arbiter-stage-rubrics.md).
3. Register lint in `deterministic_lint.py` if not schema-only.
4. Register preflight in `llm_preflight.py` and crossval checkpoint in `artifact_cross_validate.py` when applicable.
5. Add or extend `docs/prompts/_shared/examples/<stage>.examples.md`.
6. Update [analysis-stage-matrix.md](../prompts/analysis-stage-matrix.md) and [stage-registry.md](../build-out/stage-registry.md).
