# DP-MIX-JUNCTION-SEAT-AUTHORITY — Mix–Junction Seat Authority (family root)

- status: implemented
- created: 2026-09-21T17:42:41Z
- decided: 2026-09-21T17:42:41Z
- implemented: 2026-09-21T17:55:00Z
- blocks: MIX_JUNCTION_SEAT family (A1, BUILD-MIX, A5, ASSEMBLY-FRESHNESS, hollow-mix surface)
- resume_hook: (done — next DP-B4)
- folds: DP-A1 custom · DP-BUILD-MIX-JUNCTION · DP-A5 · DP-BUILD-ASSEMBLY-FRESHNESS (Partial music admit)

## Operator picks (logged)
1. Phase 0+1 authority module + Phase 2 policies selected below
2. Explicit `remaster_owner` (not bare `not is_done("mix")`)
3. Partial: music admits only on seated `assembly.wav`; preview delight-only; speech-first mix when music deferred

## Law (landed)
Module `src/interview_mux/mix_junction_seat.py` owns:
- `who_runs_next` / `junction_precedes_mix` (live \| stale final \| remaster_owner)
- `may_admit_music` (Partial: seated only)
- `must_verify_commitment` (A5)
- `begin_remaster` / `clear_remaster` / `remaster_in_flight`
- `allow_speech_first_mix` → `mix_epoch_block(stage="mix")`

Tests: `tests/test_mix_junction_seat.py`, matrix + i25 cascade under `MUX_FORENSICS=0`.
