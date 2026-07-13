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
| `source_topology_build` | `understanding/source_topology.json`, `flow_adaptation.json` | **TBIY:** topology confirm on Story Board |
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
| G1.5 (TBIY) | post-preview pickup | `gate:g1_5_preview_pickup` (after `gate:preview_listen`) |
| G2 | `REMOVED_g2_flow_select` | `gate:g2` |

## Phase D — Build

`topic_coverage_audit` → `narrative_arc_plan` → `full_master_ranking` → `transitions` → `sound_design_plan` → `sound_design_vo_finalize` → `edl_narrative_audit` → `edl` → `assembly_preview`

## Phase E — Sound

| Stage | Gate | Driver event |
|-------|------|--------------|
| `sfx_prompt_craft` | G1.5 | `gate:g1_5` |
| `mmaudio_sfx` | post-listen | `gate:sfx_post_listen` |
| `mix` | | |

## Phase F — Export

`master_finalize` → `master/master.wav`

---

## Gate handler priority

1. write approval → 2. handoff → 3. reuse decline → 4. preclean dismiss → 5. G0 → 6. G0.5 → 7. profile → 8. G1 upload → 9. G1 continue → 10. G2 → 11. G1.5 → 12. sfx post-listen → 13. preview listen → 14. LLM gate (blocker) → 15. job running (wait) → 16. modal continue → 17. **active substep** (`data-testid="substep-{id}"` from `journey.active_substep_id`) → 18. **primary CTA** (`step-action-primary` → `checkpoint-continue` → `write-approval-save-continue` → sidebar substep)

### Session banner (refresh / restart)

| Selector | When |
|----------|------|
| `data-testid="session-banner"` | After boot or refresh — shows `run_id`, execution #, working directory |
| `data-testid="live-status-bar"` | Operator headline + workflow chips stay in sync with journey phase |

Assert **no** collapsible **Audio quality (optional)** and **no** `GET /api/runs/*/audio-quality` in network log on Pipeline tab.

Write approval panel title must include **Save to working directory**.

### Primary CTA priority (Pipeline tab)

| Selector | When |
|----------|------|
| `data-testid="step-action-primary"` | **`StepActionHeader`** — opens modal or runs step (preferred) |
| `data-testid="checkpoint-continue"` | Modal footer when generic Continue is shown |
| `data-testid="write-approval-save-continue"` | Write approval panel Save button |
| `data-testid="live-status-primary"` | Live status bar on non-Pipeline tabs |

### Substep navigation (Steps sidebar)

When the GUI shows hierarchical substeps under each pipeline step, the driver may click:

| Selector | When |
|----------|------|
| `data-testid="substep-{id}"` | `journey.active_substep_id` matches (e.g. `write_approval:ingest`, `stage_reuse:transcribe`, `gate:transcript_review`) |
| `data-testid="operator-action-modal"` | Wait for checkpoint modal after primary CTA |
| `data-testid="pipeline-step-{stageId}"` | Expand a collapsed step row before substep clicks |
| `.pipeline-substep-row.status-todo` | Fallback first actionable substep |

Driver event: `action:substep`

## Tab hardening regression steps (post-audit)

Scripted checks for middle-panel tools and Activity stream policy. Run manually or extend `gui_driver.py`.

| ID | Flow | Steps | Expected |
|----|------|-------|----------|
| P3 | Flow 1 early | Open Pipeline before `content_context` done → click **Story** 5× | Tab stays locked / toast; Activity **All** has no coherence error spam |
| P5 | Flow 1 | Refresh with saved `pipeline_sub_tab: story` while locked | Restores to **Stage** |
| P10 | Any | Job starts while Activity on **All** | Pin clears; tab switches to **Live** |
| P14 | Flow 1 post-classify | **Timeline** → Assembly before EDL | Assembly button disabled |
| P19 | Flow 1 | Activity **All** with duplicate errors in `gui_log.jsonl` | Scroll list dedupes consecutive identical lines |
| F2-1 | Flow 2 | Same as P3/P5 on `REMOVED_selected_flow: flow_2` run | Timeline locked until segments; Story per `story_board_ready` |
| F3-1 | Flow 3 | Same as P3/P5 on `REMOVED_selected_flow: flow_3` run | Same gating; narrative arc stages differ, sub-tab rules unchanged |

Selectors: `data-testid="pipeline-tool-story"`, `pipeline-tool-timeline`, `pipeline-tool-profile`, Activity tabs `activity-log-all|activity-log-live|activity-log-step`.

## Log event names

`gate:*`, `action:primary_cta`, `action:substep`, `wait:job_running`, `blocker:llm_gate`, `blocker:stuck_state`
