# Phase scorecard — Partial Zero

brain: 0.2.0 | mode_focus: partially_accelerated | code_is_king: true  
source phases: `src/interview_mux/v2/phases.py`

| Phase id | Label | Stages | Priority | L1 | L2 | L3 | L4 | Verdict | Dominant families | Linked DPs |
|----------|-------|-------:|----------|----|----|----|----|---------|-------------------|------------|
| start | Start | 0 | low | n/a | n/a | n/a | n/a | PARTIAL_MUST_ACT_OK (UI) | — | — |
| prepare | Prepare | 5 | medium | done | done | done | done | KEEP (Partial-until-G0) | HOLLOW_DONE (review_build); local-ML ✅ | — |
| fix_transcript | Fix transcript | gate | must-act | checklist | n/a | G0 | HP-4 | PARTIAL_MUST_ACT_OK | G0 human | — |
| understand-a | Transcript→segments | 10 | medium | done | done | done | done | KEEP | HOLLOW_DONE (manifest) | — |
| understand-b | Segment refinement | 6 | medium | done | done | done | done | KEEP | PIN_PREMATURE (HM-2); island | — |
| understand-c | Sonic + Shape | 8 | medium | done | done | done | done | KEEP | PIN_PREMATURE (shape-core) | — |
| fill_gaps | Fill gaps | 6+G1 | high | done | done | done | done | BLOCKED_ON_DP | VO_LADDER_PARTIAL · nested mint | DP-VO1, DP-NESTED-SYNTH |
| plan_rank | Plan & rank | 17 | high | done | done | done | done | BLOCKED_ON_DP | layup/adjudicate order · VO_LADDER · nested | DP-LAYUP-ADJ, DP-VO1, DP-NESTED-SYNTH |
| edit | Edit / NLE | 0 | skip proof | n/a | n/a | n/a | n/a | KEEP (optional GUI) | — | — |
| sound | Sound | 2 | critical | done | done | done | done | PARTIAL_BLOCKED (SDP_CUE_SLOTS) | SDP_CUE_SLOTS; VO residual | [DP-SOUND-SDP-CUE](packets/DP-SOUND-SDP-CUE.md) · [analysis](analysis/phase_sound.md) |
| build | Build | 11 | critical | done | done | done | done | PARTIAL_BLOCKED (tentative) | MIX_JUNCTION_SEAT · assembly freshness · VO cousins; HOLLOW_DONE ✅ · LOCAL_ML ✅ | [DP-BUILD-ASSEMBLY-FRESHNESS](packets/DP-BUILD-ASSEMBLY-FRESHNESS.md) · DP-VO1 · [analysis](analysis/phase_build.md) |
| ship | Ship | 7+G-Pub | critical | done | done | done | done | PARTIAL_OK_IF_FINALIZE_HONEST (HOLLOW ✅); G-Pub MUST_ACT_OK | SHIP_BAR_VOCAB; ESR_POST_MASTER | DP-C5 · [analysis](analysis/phase_ship.md) |

Deep analysis order: build → sound → ship → plan_rank → fill_gaps → medium.  
**sound+ship four-level:** landed 2026-09-21 — packets awaiting_operator; no product patches.  
**plan_rank+fill_gaps four-level:** landed 2026-09-21 — DP-VO1 · DP-LAYUP-ADJ · DP-NESTED-SYNTH awaiting_operator; no product patches.
