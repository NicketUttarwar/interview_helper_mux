# Forensics loop state

- **campaign_mode:** fresh_campaign_continue_on_bug
- **INPUT_FILE:** mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3
- **run_id:** exec_13159_d19c15b58ab4_20260918T235157Z
- **fresh_launches:** 1
- **driver_restarts:** 14
- **started_at:** 2026-09-18T23:51:57Z
- **last_progress_at:** 2026-09-19T03:15:52Z
- **ship:** true
- **shipped_at:** 2026-09-19T03:15:52Z
- **driver_alive:** false
- **stages_done:** 72/72
- **current_stage:** (complete)
- **g1_complete:** true
- **intervention_count:** 11
- **last_predicate:** PMQ ship-bar + missing music_cue_coverage after junction remaster
- **last_predicate_flipped:** true
- **resume_from_stage:** —
- **open_blockers:** []
- **patches_this_session:** [i1–i9; i9 mix QC promote + defect reconcile]
- **hard_blocker:** null
- **monitor_loop:** stopped (was PID 34728)
- **notes:** Independent of family ledgers. Local ship complete; S3 sync deferred (quality advisories / G-Publish consent). Rubric advisories remain: scorecard_dimension_floors, planned_music_preserved, episode_close_outro_present (coverage still missing — remaster blocked by live on_a_roll seg_057).

### i9 — junction remaster drops mix QC; stale ship-bar defects (2026-09-19T03:15Z)
- **failure:** remaster staged `music_cue_coverage` under junction → flush dropped; stale ship-bar defects on done stages (incl. listen_delight_audit) blocked PMQ structurally.
- **patch:** promote mix QC side-effects; mix owns coverage; mark_done + PMQ reconcile open ship-bar stages that are done.
- **cascade:** `tests/test_i9_junction_remaster_promotes_mix_qc.py` — passed.
- **continue:** publish_allowed=true → encode/cover/publish; ship complete.
