# Forensics loop state

- **ship:** false
- **campaign_mode:** stopped_awaiting_user_fresh_run
- **INPUT_FILE:** mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3
- **run_id:** exec_11136_d19c15b58ab4_20260910T212232Z
- **fresh_launches:** 1
- **driver_restarts:** 7
- **stages_done:** ~54
- **current_stage:** (stopped) was vo_synthesize
- **intervention_count:** 7
- **last_predicate:** addendum A8–C15 + footgun harden landed; driver stopped per operator
- **notes:** Remaining plan code built (halt write ESR, selection cascade freeze, fail-closed reopen gates, one-shot seat token, lease expand, Phase A dual-lock). Light pytest 23 passed. e2 awaits user MUX_FRESH=1.



## Campaign goal

Confirm success bar from thrash_spine_endgame plan: no false sticky HARD while producers active; seat freeze caps held; gated reopens only; local ship.

## Interventions

| ID | Predicate | Fix |
|---|---|---|
| i1 | `true_waste_sticky:orphan_artifact` during early analysis with active producer | `record_wasted_work` HARD stamp gated by ESR `may_hard_halt`; clear false sticky on exec_11136 |
| i1b | same sticky recurred (old driver PID) | Restart driver `MUX_FRESH=0` to load patched code; continue same run |
| i2 | empty `compose_restart` → hollow gap + open high-salience / spoken_copy loop | Stop PLAN wipe; refuse hollow gap publish; park unhealable high-salience on orientation |
| i3 | `layup_skip_stuffed_needs_recompose` despite QC ok (justified sparse skips) | Sanitize only flags stuffed when unjustified skips dominate |
| i4 | Missing WAV VO contract blocked layup; premature G1 resume → layup thrash | Filter missing WAV from layup/seams preflight; G1-missing always `vo_synthesize` |
| i5 | EDL stale orientation WAV → gap_framing rewrite under freeze wiped WAVs | `gap_framing_compose` no-op under layup authority / seat freeze; heal selection/gap floor; resume `vo_synthesize` |
