# Full-auto forensics end report — exec_13170

## What happened
INPUT_FILE `mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3` → **§2 ship** (local).
- **run_id:** `exec_13170_d19c15b58ab4_20260922T004948Z`
- **fresh_launches:** 1
- **driver_restarts:** 18
- **interventions:** 16 (i1–i8; i7 speech-first chain)
- **outcome:** `master/master.wav` (163MiB, ~29.6 min) + local publish package; S3 sync deferred (G-Publish quality-advisory consent)

## Root causes fixed (this run)
| # | Predicate | Producer | Fix |
|---|-----------|----------|-----|
| i6 | premature_cap hard-fail idle spin | delivery_guardrails / full_auto_driver | automation rewrite + pinned_to |
| i7–i7j | music thrash / hollow Finished before mix | HAU speech-first chain | MUST_PRECEDE skip beds; premature_cap/safe_mix; seed_prereq/seed-front; theme/SFX gates; soft SFX completeness |
| i8 | SDP duration repair noop under hard VO freeze (emphasis 2.2s vs 5–12) | `_repair_sdp_asset_durations` + `END_A_CORE_ACTIONS` | End-A `sdp_duration_band_repair` + `commit_sound_design_plan_doc`; persist verify |

## Guardrails added
Cascade pytest `MUX_FORENSICS=0`:
- `tests/test_i7_hau_speech_first_music.py` (incl. `test_sdp_duration_repair_*`)
- related HAU / mix-lease coverage from i7 chain

## Dead ends
- Did **not** spawn a second exec to verify late-stage fixes.
- Bare `stage_key` SDP writes under hard freeze silently skip-write (looked “changed” but file stuck) — fixed via End-A reason, not hot-admit ownership alone.

## Quality & cleanup
| Gate | Result |
|------|--------|
| verify_master | OK — LUFS −16.01, TP −1.00, 48 kHz, 1776.33s |
| listen delight | `passed=True` overall **0.9502** (authoritative post_master) |
| PMQ | `status=pass` `publish_allowed=True` advisories=[] |
| local publish | `publish/audio.mp3` + cover + `.stage_done/podcast_publish` |
| S3 | blocked on quality-advisory operator consent (local ship OK) |
| daemon | stopped |
| nudge §3.0a | killed |

## Later review
Intervene log: `.cursor/plans/full_auto_forensics_state.md` (i6–i8). No End-* ledger mapping during campaign.
