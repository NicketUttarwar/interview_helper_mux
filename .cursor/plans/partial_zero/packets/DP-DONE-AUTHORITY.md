# DP-DONE-AUTHORITY — Done / mark_done / wait-clear SSOT (HOLLOW_DONE family root)

- status: done
- created: 2026-09-21T18:06:27Z
- decided: 2026-09-21T18:06:27Z
- landed: 2026-09-21T18:30:00Z
- blocks: HOLLOW_DONE; B4/B5; BUILD-HOLLOW-MIX; SHIP-HOLLOW-FINALIZE; hollow ESR / premature feed
- resume_hook: /partial-zero-implement DP=DONE-AUTHORITY
- folds: DP-B4 custom · DP-B5 · DP-BUILD-HOLLOW-MIX · DP-SHIP-HOLLOW-FINALIZE

## Operator picks (logged)
1. Full umbrella now (Done Authority + mix gate + ESR seed-complete + finalize master+PMQ+integrity)
2. Wait clears only on honest seed-complete (real completion accepted; hollow `is_done` rejected)
3. Finalize complete = master.wav + PMQ + integrity always

## Law
Module `done_authority.py` owns:
- `is_seed_complete` / `may_clear_wait` (never bare `is_done` for ESR)
- `try_mark_done` (raise/`AuthorityDenied` → False; never silent success)
- `finalize_outputs_complete` (master + PMQ + integrity)
- Mix must not call `mark_done` unless `mix_outputs_seated`

## Landed
- `src/interview_mux/done_authority.py`
- mix: `require_seated_before_mix_mark` + `try_mark_done` (`sound_design.py`)
- ESR: `should_wait_incomplete_after_conductor` uses `may_clear_wait` only
- finalize: incompleteness via `finalize_incompleteness`; stamp after PMQ persist (`post_master_quality.py`); no early stamp in `master_wav`
- LLM: `try_mark_done` in `llm_flow_hardening` / `llm_simple`
- tests: `tests/test_done_authority.py` + execution_status / mastering / i11 source checks
