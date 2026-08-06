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
| **Preflight** | `shipped` \| `partial` \| `missing` \| `shipped (G0 gate)` \| `—` |
| **Examples** | `full` \| `compact` \| `doc_only` \| `missing` |
| **Loop budget** | `shipped` \| `partial` \| `—` (max 2 attempts in `llm_simple.py`; LLM stages only) |
| **ITR** | `shipped` \| `partial` \| `—` (artifact issue triage auto-repair + clarification; [`analysis.artifact_issue_triage`](./config-keys.md#analysisartifact_issue_triage)) |
| **Status** | `shipped` (target) \| `in_progress` \| `blocked` |

**Lint column note:** `placement_apply` marks non-LLM mix stages where `apply_placement_adjustments` in `placement_qa.py` applies post-SFX hints — not arbiter lint.

**Preflight note:** G0 is enforced before first LLM stages via `check_transcript_review_pending` in `llm_preflight.py` (`speaker_roles`, `content_context`, …) — not a separate OpenAI preflight on `transcript_review` itself.

**Upstream/ship framing:** `transcript_review` (G0) is the idea-transmission checkpoint every later row in this scorecard implicitly depends on — a wrong word there cannot be caught by any downstream lint/arbiter. `listen_delight_audit` (P4 row below) is the mirror at the other end: Ship is blocked on **hard delight** (authoritative floors) regardless of how clean every upstream stage's individual scorecard status is. See [operator-gates.md](../workflows/operator-gates.md).

---

## P0 — Foundation (errors poison downstream)

| Stage | Tier | Prompt | Arbiter | Lint | Crossval | Preflight | Examples | Loop budget | ITR | Status |
|-------|------|--------|---------|------|----------|-----------|----------|-------------|-----|--------|
| `speaker_roles` | P0 | shipped | shipped | shipped | — | shipped | full | shipped | shipped | shipped |
| `content_context` | P0 | shipped | shipped | shipped | — | shipped | full | shipped | shipped | shipped |
| `boundary_detection` | P0 | shipped | shipped | shipped | — | shipped | full | shipped | shipped | shipped |
| `segment_classification` | P0 | shipped | shipped | shipped | `post_segmentation` | shipped | full | shipped | shipped | shipped |
| `content_brief_reanchor` | P0 | shipped | shipped | shipped | `post_reanchor` | shipped | full | shipped | shipped | shipped |

---

## P1 — Narrative comprehension

| Stage | Tier | Prompt | Arbiter | Lint | Crossval | Preflight | Examples | Loop budget | Status |
|-------|------|--------|---------|------|----------|-----------|----------|-------------|--------|
| `missing_framing` | P1 | shipped | shipped | shipped | `post_gaps` | shipped | full | shipped | shipped |
| `optimal_questions` | P1 | shipped | shipped | shipped | — | shipped | full | shipped | shipped |
| `gap_framing_compose` | P1 | shipped | shipped | shipped | — | shipped | full | shipped | shipped |
| `topic_coverage_audit` | P1 | shipped | shipped | shipped | `post_ranking` | shipped | full | shipped | shipped |
| `narrative_arc_plan` | P1 | shipped | shipped | shipped | — | shipped | full | shipped | shipped |
| `full_master_ranking` | P1 | shipped | shipped | shipped | `post_ranking` | shipped | full | shipped | shipped |
| `edl_narrative_audit` | P1 | shipped | shipped | shipped | `post_edl_audit` | shipped | full | shipped | shipped |

---

## P2 — Sound design + API spend

| Stage | Tier | Prompt | Arbiter | Lint | Crossval | Preflight | Examples | Loop budget | Status |
|-------|------|--------|---------|------|----------|-----------|----------|-------------|--------|
| `sound_design_palettes` | P2 | shipped | shipped | shipped | `post_sound_palettes` | shipped | full | shipped | shipped |
| `sound_design_plan` | P2 | shipped | shipped | shipped | `post_sound_plan_flow1` | shipped | full | shipped | shipped |
| `soundscape_policy_build` | P2 | — | — | shipped | — | shipped | doc_only | — | shipped |
| `mmaudio_sfx` | P2 | — | — | — | `pre_mix` | partial | doc_only | — | shipped |
| `REMOVED_sdp_flow2` | P2 | shipped | shipped | shipped | `post_sound_plan_flow2` | shipped | full | shipped | shipped |
| `sfx_prompt_craft` | P2 | shipped | shipped | shipped | `pre_sfx_generation` | shipped | compact | shipped | shipped |
| `mmaudio_sfx` | P2 | — | — | — | `pre_mix` | partial | doc_only | — | shipped |
| `REMOVED_mmaudio_flow2` | P2 | — | — | — | `pre_REMOVED_mix_flow2` | partial | doc_only | — | shipped |
| `mix` | P2 | — | — | placement_apply | `pre_mix` | — | doc_only | — | shipped |
| `REMOVED_mix_flow2` | P2 | — | — | placement_apply | `pre_REMOVED_mix_flow2` | — | doc_only | — | shipped |
| `podcast_sfx_brief` | P2 (legacy) | shipped | shipped | shipped | — | shipped | compact | shipped | shipped |
| `sfx_brief` | P2 (legacy) | shipped | shipped | shipped | — | shipped | compact | shipped | shipped |

---

## P3 — Polish (operator-recoverable)

| Stage | Tier | Prompt | Arbiter | Lint | Crossval | Preflight | Examples | Loop budget | Status |
|-------|------|--------|---------|------|----------|-----------|----------|-------------|--------|
| `transitions` | P3 | shipped | shipped | shipped | `post_transitions` | shipped | full | shipped | shipped |
| `REMOVED_highlight_selection` | P3 | shipped | shipped | shipped | — | shipped | full | shipped | shipped |
| `REMOVED_podcast_show_description` | P3 | shipped | shipped | shipped | — | shipped (flow3-aware)[^flow3-preflight] | full | shipped | shipped |

[^flow3-preflight]: When `REMOVED_selected_flow: flow3`, preflight checks `understanding/content_brief.json`, `understanding/speakers.json`, `segments/manifest.json` (analysis-only — no Flow 1 `selection.json`). Flow 1 path still requires `master/selection.json`.

---

## P4 — Upstream non-LLM gates

| Stage | Tier | Prompt | Arbiter | Lint | Crossval | Preflight | Examples | Loop budget | Status |
|-------|------|--------|---------|------|----------|-----------|----------|-------------|--------|
| `transcript_review_build` | P4 | — | — | — | — | — | doc_only | — | shipped |
| `transcript_review` (G0) | P4 | — | — | — | — | shipped (G0 gate) | doc_only | — | shipped |
| `source_acoustic_profile` | P4 | — | — | — | — | — | doc_only | — | shipped |
| `sound_design_vo_finalize` | P4 | — | — | — | — | partial | doc_only | — | shipped |
| `assembly_preview` | P4 | — | — | — | — | — | doc_only | — | shipped |
| `listen_delight_audit` | P4 | — | — | — | — | — | doc_only | — | shipped |

---

## Meta + specialists

| Stage | Tier | Prompt | Arbiter | Lint | Crossval | Preflight | Examples | Loop budget | Status |
|-------|------|--------|---------|------|----------|-----------|----------|-------------|--------|
| `_arbiter` | meta | shipped | — | — | — | — | doc_only | — | shipped |
| `comprehension_risk_blind` | P1 specialist | shipped | — | — | — | — | full | — | shipped |
| `theme_coverage_pass` | P0 specialist | shipped | — | — | — | — | full | — | shipped |
| `emphasis_coverage_pass` | P1 specialist | shipped | — | — | — | — | full | — | shipped |

---

## Module map

| Layer | Code / doc |
|-------|------------|
| Preflight | `src/interview_mux/llm_preflight.py` |
| Deterministic lint | `src/interview_mux/deterministic_lint.py` — generic keys fully implemented in `_lint_generic()` (coverage ratio, cross-refs, min rows, truncation/decompose) |
| Arbiter rubrics | `docs/prompts/_shared/arbiter-rubrics/*.json` · [arbiter-stage-rubrics.md](../prompts/_shared/arbiter-stage-rubrics.md) |
| Cross-validate | `src/interview_mux/artifact_cross_validate.py`, `sdp_cross_validate.py` |
| Attempt cap (2) | `src/interview_mux/llm_simple.py` |
| Local volley framer | `src/interview_mux/local_volley_framer.py` — `prepare_volley_for_llm` |
| Stage guidance | `src/interview_mux/stage_guidance.py` — GUI journey copy + gate CTAs |
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
6. Update [analysis-stage-matrix.md](../prompts/analysis-stage-matrix.md) and [stage-contracts/00-INDEX.md](./stage-contracts/00-INDEX.md).
