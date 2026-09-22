# Full-auto forensics end report — exec_13167

## What happened
INPUT_FILE `mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3` → **§2 ship** (local).
- **run_id:** `exec_13167_d19c15b58ab4_20260921T044550Z`
- **fresh_launches:** 1
- **driver_restarts:** 23
- **interventions:** 15 (i1–i11h)
- **outcome:** `master/master.wav` + local publish package; S3 sync deferred (quality-advisory G-Publish consent)

## Root causes fixed (this run)
| # | Predicate | Producer | Fix |
|---|-----------|----------|-----|
| i11 | hollow mark_done:mix (EDL newer than assembly) | sound_design.mix | seat mtime before mark_done |
| i11b–c | assembly_stale pin→junction thrash | resolve_assembly_stale / path_to_master | always pin mix |
| i11d | ledger sha ≠ final assembly | write_render_ledger / mix_outputs_seated | fingerprint final_path |
| i11e | remaster under junction pending | remaster_mix_only | nested mix staging; never block mix on assembly_stale |
| i11f | pre_mix incomplete_cut ← assembly_not_rendered | publishability_boundary / heal_routing | remaster-only seam reasons ≠ incomplete_cut |
| i11g | premature_complete:mix_seat after seated mix | delivery_resume_stage / safe_mix_resume | advance to junction when seated |
| i11h | hollow mark_done:master_finalize (PMQ missing) | run_post_master_quality / run_wrapped_stage | persist PMQ despite delight loud-fail; flush pending on exception |

Earlier i1–i10 (VO floor, SDP cue_slots, hollow vo_line, intro schema, gendered pronoun, budget epoch, ESR pin, narrative_plan ALLOW, mid-sentence repair) also continued this same run_id.

## Guardrails added
Cascade pytest under `MUX_FORENSICS=0`: `tests/test_i11_*.py`, `test_i11_premix_commitment_diverge_not_incomplete_cut.py`, `test_i11_advance_past_seated_mix.py`, `test_i11_pmq_persists_when_delight_fails.py`.

## Dead ends
- Did **not** spawn a second exec to verify late-stage fixes.
- Sticky job `error` fields often lagged live progress (ignore for diagnosis).

## Quality & cleanup
| Gate | Result |
|------|--------|
| verify_master | see tools output below |
| listen delight | `passed=True` overall **0.9654** |
| PMQ | `status=pass` `publish_allowed=True` failed=[] |
| local publish | `publish/audio.mp3` + `.stage_done/podcast_publish` |
| S3 | blocked on quality-advisory operator consent (local ship OK) |
| daemon | stopped |
| nudge §3.0a | killed |

## Later review
Intervene log: `.cursor/plans/full_auto_forensics_state.md` (i1–i11h). No End-* ledger mapping during campaign.
