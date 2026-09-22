# Phase analysis — understand-a

brain: 0.2.0 | mode: partially_accelerated | code_is_king: true  
label: Transcript → segments  
stages: `source_acoustic_profile` · `interview_spine_build` · `speaker_roles` · `source_topology_build` · `content_context` · `talking_points_compose` · `ideal_cuts_propose` · `ideal_cuts_materialize` · `boundary_detection` · `segment_classification`

## Level 1 — Stage solo

| Stage | Open routes (HEAD) | Thrash? | Notes |
|-------|--------------------|---------|-------|
| `source_acoustic_profile` | → `understanding/source_acoustic_profile.json` | Low | Early acoustic fingerprint |
| `interview_spine_build` | Spine / structure seed | Low–med LLM | Feeds later Shape |
| `speaker_roles` | → `understanding/speakers.json` | Low | Pickup eligibility upstream of G-Framing |
| `source_topology_build` | Topology + least-spoken / pickup-eligible | Low | G-Framing defaults consume this |
| `content_context` | → `understanding/content_brief.json` (shared path) | Med | Ownership shared with reanchor (understand-b) |
| `talking_points_compose` | Talking-point cuts | Med LLM | Delivery-locked timeline after classify |
| `ideal_cuts_propose` | Propose keep windows | Med LLM | |
| `ideal_cuts_materialize` | Materialize cut assets | Low–med | |
| `boundary_detection` | Segment boundaries | Med | Resplit cousin in understand-b |
| `segment_classification` | → `segments/manifest.json` | Med | Phase exit artifact; hollow class = bad handoff |

## Level 2 — Group

- Internal order / done agreement: Contiguous seed slice after G0. Exit = `segment_classification` seed-complete with non-empty `segments/manifest.json`. `DELIVERY_LOCKED_TIMELINE_STAGES` includes this band — delivery must not rewind classified timeline.
- Candidate SIMPLIFY / CUT: No Partial CUT. LLM volley thrash is bounded by stage max attempts (product law). Content_brief dual-writer with understand-b is the main SIMPLIFY watch (handoff honesty, not stage delete).

## Level 3 — Handoffs

| Edge | Ready meaning | Cousin risk |
|------|---------------|-------------|
| fix_transcript → understand-a | G0 closed (`transcript_review` done + corrections/full) | Premature advance past open G0 (driver / agenda truncate) |
| understand-a → understand-b | `segments/manifest.json` + classification seed-complete | HOLLOW_DONE / empty manifest; reanchor fights shared brief |
| topology → (later) fill_gaps | Topology + speakers for framing defaults | VO_LADDER_PARTIAL if defaults wrong (later phase) |

## Level 4 — Junctions

| Junction id | Fact | Callers | Linked DP |
|-------------|------|---------|-----------|
| (none named) | Artifact seam at manifest; no seat/mix junction | agenda `stage_outputs_present`, stage_completion | — |

## Decision Packets drafted

- None for understand-a alone. Shared-brief thrash with understand-b monitored; escalate to DP only if HEAD shows wrong producer pin (HM-2 naming).

## Partial impact

Unattended walk runs this band after operator G0. No must-act gate inside the phase. Risk is hollow classification or early delivery rewind — HEAD locks timeline stages; Partial zero needs seed-complete manifest before understand-b.
