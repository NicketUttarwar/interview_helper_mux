# Phase analysis — understand-b

brain: 0.2.0 | mode: partially_accelerated | code_is_king: true  
label: Segment refinement  
stages: `content_brief_reanchor` · `framing_posture_decide` · `boundary_topic_resplit` · `vernacular_segment_sanitize` · `low_conf_island_scan` · `connector_fuse_pass`

## Level 1 — Stage solo

| Stage | Open routes (HEAD) | Thrash? | Notes |
|-------|--------------------|---------|-------|
| `content_brief_reanchor` | Re-writes shared `understanding/content_brief.json` | Med | HM-2: only pin here when brief is *named* in error; else sonic/palettes self-pin |
| `framing_posture_decide` | → `understanding/framing_posture_decision.json` | Low | Advisory for G-Framing UI; not gate stamp |
| `boundary_topic_resplit` | Topic-aware boundary adjust | Med | Can churn segments vs classify freeze |
| `vernacular_segment_sanitize` | Vernacular cleanup | Low–med | |
| `low_conf_island_scan` | → low_conf island artifacts | Med | `PROTECTED_ISLAND_STAGES` |
| `connector_fuse_pass` | Fuse audit / rounds | Med | Island-protected; pre-ranking cousin later |

## Level 2 — Group

- Internal order / done agreement: Refinement band after classified manifest. Exit = `connector_fuse_pass` seed-complete. Island stages are agenda-protected against casual skip. Framing posture is advisory — operator G-Framing still lives in fill_gaps.
- Candidate SIMPLIFY / CUT: Do not CUT island/fuse under Partial (quality + later ranking feed). Watch reanchor ↔ content_context double-write for SIMPLIFY of ownership prose only if thrash appears.

## Level 3 — Handoffs

| Edge | Ready meaning | Cousin risk |
|------|---------------|-------------|
| understand-a → understand-b | Classified `segments/manifest.json` | Hollow classify; resplit vs locked timeline |
| understand-b → understand-c | Refined segments + posture + fuse complete | Reanchor thrash; wrong heal to `content_brief_reanchor` for sonic holes (HM-2) |
| posture → fill_gaps G-Framing | Advisory `recommended_framing` only | Treating posture as gate stamp (product forbid) |

## Level 4 — Junctions

| Junction id | Fact | Callers | Linked DP |
|-------------|------|---------|-----------|
| (HM-2 related) | Mastering/sonic heal must not steal to reanchor unless brief named | `mastering_heal_resume_stage`, thrash_hardening | — (covered HEAD; no new DP) |

## Decision Packets drafted

- None. HM-2 pin rules verified on HEAD in `stage_completion.mastering_heal_resume_stage`.

## Partial impact

Fully unattended under Partial after G0. Primary Partial risk is heal/resume mis-pin into reanchor (PIN_PREMATURE cousin) or island skip greenwash — protected island set + HM-2 reduce that. No operator must-act in this phase.
