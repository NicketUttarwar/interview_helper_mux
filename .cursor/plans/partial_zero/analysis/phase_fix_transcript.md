# Phase analysis — fix_transcript (G0)

brain: 0.2.0 | mode: partially_accelerated | code_is_king: true  
stages: [] (gate-only) · gate: `transcript_review`  
verdict target: **PARTIAL_MUST_ACT_OK**

## Level 1 — Checklist (G0 must-act)

| Check | HEAD fact | Partial OK? |
|-------|-----------|-------------|
| Gate is mandatory human | `PARTIAL_MUST_ACT_GATES` includes `transcript_review`; driver `wait_for_operator_g0` | Yes — intentional |
| Unattended does not auto-complete G0 | Partial never auto-accepts G0 (operator-gates / automation_run) | Yes |
| Heal pin when queue exists | `g0_heal_resume_stage` → `transcript_review` (HP-4) | Yes |
| Heal pin when queue missing/hollow | → `transcript_review_build` (HP-2) | Yes |
| Walk stops while G0 open | agenda `_truncate_analysis_while_g0_open`; remainder does not run analysis past build | Yes |
| Stage runner does not fake-run gate | `pipeline` g0_pending: driver owns `complete_g0` / `wait_for_operator_g0` | Yes |
| Done meaning | Queue + `corrections.json` + `full.json` + sign-off / `.stage_done` | Yes |
| Preclean timing | Partial prepare-until-G0 defers `audio_preclean` until after review | Yes — docs + `PARTIAL_AUTO_PREPARE_UNTIL_G0` |

## Level 2 — Group

- Internal order / done agreement: Not a stage band — single operator gate between prepare and understand-a.
- Candidate SIMPLIFY / CUT: **KEEP** — idea-transmission hard gate. Never CUT for Partial zero.

## Level 3 — Handoffs

| Edge | Ready meaning | Cousin risk |
|------|---------------|-------------|
| prepare → G0 | Non-hollow `transcript/review_queue.json` | Hollow build; HP-4 wrong pin to rebuild |
| G0 → understand-a | Gate cleared / signed | Premature analysis while pending; G0_LOCKED rewind after close |

## Level 4 — Junctions

| Junction id | Fact | Callers | Linked DP |
|-------------|------|---------|-----------|
| HP-4 G0 pin | Open G0 resumes gate, not rebuild | `g0_heal_resume_stage`, heal_routing, agenda truncate | — |

## Decision Packets drafted

- None. G0 is product must-act under Partial by design (covered / P0-4 in cross-surface catalog).

## Partial impact

**PARTIAL_MUST_ACT_OK:** Partial ironclad requires the human to finish transcript review; automation correctly waits and does not stamp G0. Failure mode to watch in soak: GUI focus / overlay miss — product, not a code gap for this checklist.
