# Step 02 — GUI journey (Flow 1 full podcast)

**Input:** `ASSETS/notebooklm_original_interview_2024.wav`  
**Rule:** Driver triggers stages only via GUI primary CTAs — never `POST /api/runs/{id}/execute`.

---

## Phase A — Prepare

| Stage ID | Artifacts | Gates / pauses | Driver event |
|----------|-----------|----------------|--------------|
| `audio_preclean` | optional cleaned WAV | preclean offer | `gate:preclean_dismiss` |
| `ingest` | `ingest/normalized.wav` | write approval, handoff | `gate:write_approval`, `gate:handoff` |
| `transcribe` | `transcript/full.json` | write approval | |
| `transcript_review_build` | `transcript/review_queue.json` | write approval | |
| `disfluency_extract` | `transcript/disfluencies.json` | write approval | |
| `transcript_review` | merged transcript | **G0** | `gate:g0` |
| `disfluency_review` | review markers | **G0.5** | `gate:g0_5` |

## Phase B — Analyze

| Stage ID | Key artifact |
|----------|--------------|
| `source_acoustic_profile` | `understanding/source_acoustic_profile.json` |
| `interview_spine_build` | spine |
| `speaker_roles` | `understanding/speakers.json` |
| `content_context` | `understanding/content_brief.json` |
| `boundary_detection` | `segments/boundaries.json` |
| `segment_classification` | manifest |
| `content_brief_reanchor` | brief |
| `sonic_context_build` | sonic context |
| `sound_design_palettes` | palettes |
| `missing_framing` | `understanding/gap_report.json` |
| `optimal_questions` | interviewer script |
| `analysis_profile` | **Profile gate** — `gate:profile` |

## Phase C — Record & choose

| Gate | Stage | Driver event |
|------|-------|--------------|
| G1 | `g1_vo_pickup` | `gate:g1_upload`, `gate:g1_continue` |
| G2 | `g2_flow_select` | `gate:g2` |

## Phase D — Build

`topic_coverage_audit` → `narrative_arc_plan` → `full_master_ranking` → `transitions` → `sound_design_plan_flow1` → `sound_design_vo_finalize` → `edl_narrative_audit` → `edl_flow1` → `assembly_preview`

## Phase E — Sound

| Stage | Gate | Driver event |
|-------|------|--------------|
| `sfx_prompt_craft` | G1.5 | `gate:g1_5` |
| `mmaudio_sfx_flow1` | post-listen | `gate:sfx_post_listen` |
| `mix_flow1` | | |

## Phase F — Export

`master_flow1` → `flow_1_master/master.wav`

---

## Gate handler priority

1. write approval → 2. handoff → 3. reuse decline → 4. preclean dismiss → 5. G0 → 6. G0.5 → 7. profile → 8. G1 upload → 9. G1 continue → 10. G2 → 11. G1.5 → 12. sfx post-listen → 13. preview listen → 14. LLM gate (blocker) → 15. job running (wait) → 16. modal continue → 17. **active substep** (`data-testid="substep-{id}"` from `journey.active_substep_id`) → 18. primary CTA

### Substep navigation (Steps sidebar)

When the GUI shows hierarchical substeps under each pipeline step, the driver may click:

| Selector | When |
|----------|------|
| `data-testid="substep-{id}"` | `journey.active_substep_id` matches (e.g. `write_approval`, `gate:transcript_review`) |
| `data-testid="pipeline-step-{stageId}"` | Expand a collapsed step row before substep clicks |
| `.pipeline-substep-row.status-todo` | Fallback first actionable substep |

Driver event: `action:substep`

## Log event names

`gate:*`, `action:primary_cta`, `action:substep`, `wait:job_running`, `blocker:llm_gate`, `blocker:stuck_state`
