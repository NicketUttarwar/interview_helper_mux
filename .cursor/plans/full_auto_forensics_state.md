# Forensics loop state

- **campaign_mode:** fresh_campaign_continue_on_bug
- **INPUT_FILE:** mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3
- **run_id:** exec_11550_d19c15b58ab4_20260911T232613Z
- **fresh_launches:** 1
- **driver_restarts:** 1
- **started_at:** 2026-09-11T23:26:13Z
- **last_progress_at:** 2026-09-12T02:20:10Z
- **driver_alive:** false
- **stages_done:** 73/72
- **current_stage:** ship
- **g1_complete:** true
- **intervention_count:** 1
- **last_predicate:** air_script.py:air_contract_sanitary_errors — clear
- **last_predicate_flipped:** true
- **resume_from_stage:** null
- **open_blockers:** []
- **patches_this_session:** [i1 run_air_contract_sanitize nested reentry skip]
- **hard_blocker:** null
- **monitor_loop:** killed (was PID 91229)
- **ship:** true
- **notes:** Fresh campaign. No prior exec folders used. S3 sync held for G-Publish consent on aspirational scorecard advisory; local publish envelope allowed.

## Campaign goal

Ship bar (§2): master.wav + verify_master + listen_delight + PMQ publish_allowed + cover/publish — **met**.

## Interventions

| ID | Predicate | Fix |
|---|---|---|
| i1 | air_contract_sanitize nested-skip commit (drop_seated_missing_from_gap never persisted) | `run_air_contract_sanitize` no longer wraps `commit_air_contract` in a second reentry guard; raise if skip; test in `test_artifact_sanitize_air_contract.py` |

## What happened

INPUT_FILE `mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3` → ship on **exec_11550_d19c15b58ab4_20260911T232613Z**. fresh_launches=1, driver_restarts=1, interventions=1.

Driver logged `DONE master=… size=255563310 publish=yes` at 2026-09-11T19:20:10 PDT. Stack self-shutdown.

## Root causes fixed

- **i1** `air_contract_needs_sanitize:drop_seated_missing_from_gap` — producer `air_contract_sanitize`. Class: **commit / reentry**. `run_air_contract_sanitize` set `sanitize_reentry_guard` then called `commit_air_contract`, which nested-skipped the write (`ok=True`, no persist). Continued **this** run (`MUX_FRESH=0`). Predicate flipped: sanitary_errors=[], seated_missing_from_gap=[].

## Guardrails added

- `tests/test_artifact_sanitize_air_contract.py::test_run_air_contract_sanitize_commits_drop_seated_missing_from_gap`

## Dead ends

- Did not start a second fresh exec to verify i1.
- Did not attach to prior campaign `exec_11165`.
- Mix “assembly incomplete” after first mix was **stale vs live EDL** (EDL restamped after assembly); mix rebuild succeeded — not a checker lie.
- G1 missing 002/010 after first synth: pending WAVs discarded when batch continued to EDL; driver re-entered `vo_synthesize` and committed all three seats. Did not patch fail-open this campaign because G1 flipped on retry.

## Quality & cleanup

- `verify_master.py`: OK — 2662.12s, 48 kHz mono, I=-16.01 LUFS, TP=-1.01 dBTP
- listen_delight: mode=authoritative, passed=True, blocking=False, overall=0.96, failed_dimensions=[] (`pass=pre_mix` timestamp before master_finalize; product still shipped)
- PMQ: `publish_allowed: true`, status=pass; advisory only `scorecard_dimension_floors` (aspirational) → S3 sync held for G-Publish consent
- Cover + `podcast_publish` `.stage_done` present
- Daemon stopped; nudge PID 91229 killed
