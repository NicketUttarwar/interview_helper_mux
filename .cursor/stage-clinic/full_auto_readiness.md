# Full-auto readiness rollup (Wave 3)

last_scored: 2026-09-17  
verdict: `not_ready`

Campaign end-state: unattended Full-auto on shipped defaults, brain 0.2.0.  
Evidence: Wave 1 maps (72/72 complete) + Wave 2 patches below + defaults_inventory.md.  
No `exec_*` used.

## Wave 2 patches landed this campaign

- `operator_gates.should_stamp_needs_operator` — 0.2.0 unattended uses classified allowlist (CSP-03)
- `stages/low_conf_fuse_stages.run_low_conf_island_scan` — disabled path writes + heals (CSP-01)
- `stage_completion.stage_artifact_incompleteness(audio_preclean)` — skip.json is complete (CSP-06)
- Tests: `test_remediation_framework` 0.2.0 cases; `test_stage_clinic_wave2_remediation.py`

## §0.2 scorecard

| # | Check | Score | Evidence (map/target paths) | Notes |
|---|-------|-------|-------------------------------|-------|
| 1 | Progression | partial | maps for mix, junction, low_conf, fuse, ranking | Wave 2 fixed low_conf stall; mix⇄junction thrash (CSP-04) still open |
| 2 | Honesty | partial | audio_preclean map+patch; vo_synthesize done-without-wav map; hollow OpenAI maps | Preclean skip honesty fixed; VO/OpenAI hollow paths remain |
| 3 | Stalls | partial | operator_gates.py + defaults_inventory | Classified 0.2.0 stamp fixed; G0 driver / G1.5 / g_listen=block / publish consent still landmines |
| 4 | OpenAI variance | partial | maps: content_context, ranking, layup, transitions, cover | Pattern CSP-05 open — not systematically patched |
| 5 | Defaults | partial | defaults_inventory.md | Inventory filled from HEAD; several stage-local landmines remain |
| 6 | Ship bar | partial | listen_delight_audit, master_finalize, podcast_publish maps | Authoritative delight + g_listen/S3 advisory risks documented, not all fixed |
| 7 | Cross-stage | partial | cross_stage_patterns.md | CSP-01/03/06 ruled; CSP-02/04/05 open |

## Aggregation

- `ready_for_unattended_full_auto_attempt` requires 1–6 pass/justified partial without open FULL_AUTO_REGRESSION_RISK on ship-critical path and no unlabeled repeats in #7.
- **Verdict `not_ready`:** ship-critical thrash (mix/junction), VO host honesty, G1.5/g_listen/publish landmines, and OpenAI hollow pattern still open after this Wave 2 slice.

## Blockers (next remediation slices)

1. mix ⇄ junction incomplete_cut / remaster oscillation (CSP-04)
2. vo_synthesize done-without-wav / G1 unattended host honesty
3. sfx_prompt_craft G1.5 approval under Full-auto defaults
4. master_finalize + g_listen_mode=block + delight remutate termination
5. podcast_publish skip-hollow / S3 advisory consent
6. Contract hard/soft fleet alignment (CSP-02) via `contract_dependency_data` (not hand-edited YAML)

## Residual needs_you (from Wave 1 targets)

- Full-auto G1.5 auto-approve policy
- g_listen auto-clear after remaster under defaults
- S3 advisory consent under Full-auto
- Whether empty transitions (`min_rows:0`) is ship-legal
- air_script `enable=false` unmarked (same family as CSP-01)

## Cross-stage patterns open

- CSP-02, CSP-04, CSP-05 (see cross_stage_patterns.md)

## Optional outside confirmation

Live Full-auto run is **outside** this campaign; not required to close Wave 3. Re-score after next remediation slice.
