# Full-auto forensics end report — exec_13177

## What happened
INPUT_FILE `mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3` → **§2 ship** (local).
- **run_id:** `exec_13177_d19c15b58ab4_20260923T001031Z`
- **fresh_launches:** 1
- **driver_restarts:** ~18
- **interventions:** i1–i15 (this campaign; i9–i15 dominant late delivery)
- **outcome:** `master/master.wav` (226MiB, ~41.1 min) + local publish package; S3 sync deferred (G-Publish quality-advisory consent at ship time — PMQ itself `publish_allowed=True`)

## Root causes fixed (this run)
| # | Predicate | Producer | Fix |
|---|-----------|----------|-----|
| i9 | opening_orientation_inaudible (required CTA scrap treated as waived) | air_script / omit_ledger / edl | required+not-omitted → not waived; revive clears stale waive; playbook always revives |
| i10 | hosted_vo_floor_unmet under hard freeze | artifact_sanitize.air_script | End-A `reseated_active_hosted_vo_for_wav`; pin `hosted_vo_wav_coverage` → vo_synthesize |
| i11 | omitted+WAV lines lacking omit flags; clamp drift | vo_contract / sanitize clamp | reseat omitted+WAV via End-A; clamp stamps gap omit; persist_frozen gap writes |
| i12 | seated omit purge stripped WAV; undeclared vo_pickup drop | omit_ledger / StageInfo | protect seated_vo_line_ids; declare `vo_pickup/` on vo_synthesize |
| i13 | chatterbox WAV then invalid_json_stdout → bind heal omit-wins | vo_bind_authority / vo_contract | accept stem WAV as bind success; never omit when WAV present; force-clear seated_bind_synth_failed |
| i14 | music_palette bed_coverage_seed off-selection (seg_028) | artifact_repairs.repair_sound_design_plan | pre-seed drop off-selection cues; filter bed_anchor_pool; prune palette segment_ids |
| i15 | mix-seated order_reconcile deny rewound SDP invent | sound_design_stages | skip fail-closed invent when assembly+SDP present; stamp `_meta.producer_stage`; mark SDP done |

## Guardrails added
Cascade pytest `MUX_FORENSICS=0`:
- `tests/test_i9_required_orientation_stale_waive.py`
- `tests/test_i10_hosted_vo_wav_coverage.py`
- `tests/test_i11_omitted_wav_reseat.py`
- `tests/test_i12_seated_omit_purge_protect.py`
- `tests/test_i13_bind_heal_wav_accept.py`
- `tests/test_i14_sdp_bed_off_selection.py`
- `tests/test_i15_mix_seat_sdp_reconcile.py`

## Dead ends
- Did **not** spawn a second exec to verify late-stage fixes.
- Did **not** soft-complete sealed consumers or rely on e2e quality waivers.
- Serve reload required after StageInfo / product patches (i12b) — stale server re-applied omit purge until restart.
- Direct SDP write needed once when ownership/sanitize reverted validated write (i14 live).

## Quality & cleanup
| Gate | Result |
|------|--------|
| verify_master | OK — LUFS −16.00, TP −1.00, 48 kHz, 2465.40s |
| listen delight | `passed=True` overall **0.9725** (authoritative post_master) |
| PMQ | `status=pass` `publish_allowed=True` advisories=[] |
| local publish | `publish/audio.mp3` + `publish/cover.jpg` + `.stage_done/podcast_publish` |
| S3 | blocked on operator G-Publish consent gate at sync (local ship OK) |
| daemon | stopped |
| nudge §3.0a | killed (PIDs 81541, 95203) |

## Later review
Intervene log: `.cursor/plans/full_auto_forensics_state.md` (i9–i15). No End-* / predicate-family ledger mapping during campaign.
