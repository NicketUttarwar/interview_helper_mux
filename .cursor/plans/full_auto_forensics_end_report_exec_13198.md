# Full-auto forensics end report — exec_13198

## What happened
INPUT_FILE `mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3` → **§2 ship** (local).
- **run_id:** `exec_13198_d19c15b58ab4_20260924T214444Z`
- **fresh_launches:** 1
- **driver_restarts:** 19
- **interventions:** i1–i14 (continued same run_id after each patch)
- **outcome:** `master/master.wav` (256MiB / 268079886 bytes, 2792.50s) + local publish package; S3 sync deferred (G-Publish quality-advisory consent — PMQ `publish_allowed=True`)

## Root causes fixed (this run)
| # | Predicate | Producer | Fix |
|---|-----------|----------|-----|
| i1 | budget.dispatch_cap_refusal on missing_framing + batch_fill | missing_framing | BudgetExemption `missing_framing_batch_fill` when unscored fills remain |
| i2 | superseded fill duplicates block missing_framing done | missing_framing | Last-wins per segment_id in gap evaluations incompleteness |
| i3 | framing:primary impact + mid_arc_reverse_jump from append restore | selection_order_sanitize / framing_coverage_guard | apply_selection_constraints; restore by tape start_ms |
| i4 | attempt_memo refuse while layup_compose_shards_pending | dispatch_delta / nugget_layup_compose | memo_skip yields when incompleteness has shards_pending |
| i5 | layup LLM garbled seg_070; heal release_false; authority_undo thrash | media_ip_cta / thrash_hardening | Punch host extras; release_false keeps editorial excludes; undo exempt media_ip_cta |
| i6 | selection_commit_refused + authority_undo stranding layup | dispatch_delta / thrash_hardening | resume clears refuse+undo; thrash exempts layup after media_ip_cta |
| i7 | seg_070 re-admitted after release_false cleared never_touch | media_ip_cta | drop_never_touch_cta is editorial; late scraps stay never-touch |
| i8 | framing restore CTA primary; empty-text excerpt re-ask | framing_coverage_guard / media_ip_cta / llm_simple | Skip never_touch+CTA restore; expand fragmentary tokens; demote CTA needs |
| i9 | high_gap_unframed under layup hollow-done; gap_report unpaid | stage_completion / done_authority | high_gap blocks layup; gap_report accepts layup/framing co-producers |
| i10 | edl_narrative thrash — blank-dropped hard_keep seg_028 | artifact_repairs.repair_master_selection | Never blank-drop hard-keep ids; committed chapter fill |
| i11 | stale chapter/blank audit; selection unpaid; sanitize↔edl thrash | artifact_repairs / done_authority / thrash_hardening | Demote contradicted blockers; edl_narrative_* land stamps; exempt metadata oscillation |
| i12 | edl_narrative_qc blank-drop hard_keep → sanitize hard_keep_missing | artifact_repairs / assembly / air_order_boundary / flow1 EDL | Exempt hard-keeps from blank-drop; keep short-speech hard-keeps |
| i13 | selection_order_sanitize unpaid after EDL — producer_stage='selection' | done_authority | Alias stamps `selection` / `artifact_sanitize.selection` paid land |
| i14 | remaining_stages / unpaid_land(mix) ~12–23s pure-Python VO DFT | vo_speech_qa | numpy rFFT + path+mtime analyze cache |

## Guardrails added
Cascade pytest (`MUX_FORENSICS=0`):
- `tests/test_p15_budget_door.py::test_batch_fill_incompleteness_grants_walk_door_grace`
- `tests/test_hg3_missing_framing_batch.py::test_hg3_superseded_fill_duplicate_does_not_block_done`
- `tests/test_artifact_sanitize_selection.py::test_sanitize_restores_primary_impact_not_selected`
- `tests/test_p15_attempt_memo.py` (memo_skip shards; resume_after_intervene)
- `tests/test_media_ip_cta.py` (CTA omit / hard_keep blank / EDL prepare / flow1)
- `tests/test_framing_coverage_guard.py::test_enforce_framing_does_not_restore_media_ip_cta_primary`
- `tests/test_i3_omit_demote_high_gap.py::test_high_gap_unframed_also_blocks_layup_done`
- `tests/test_unpaid_land_matrix.py` (gap_report / selection co-producers / aliases)
- `tests/test_artifact_repairs_p1.py::test_repair_edl_audit_demotes_filled_chapter_and_hard_keep_blank`
- `tests/test_sanitize_authority_thrash.py::test_selection_metadata_align_sanitize_oscillation_not_halt`
- `tests/test_vo_speech_qa.py` (analyze cache + numpy tonal peak)

## Dead ends
- Did **not** spawn a second exec to verify late-stage fixes.
- Did **not** soft-complete sealed consumers (`edl` / `mix` / `master_finalize`) or use e2e quality waivers.
- Did **not** map bugs to predicate-family / End-* ledgers mid-run.
- Premature “Finished: Mix assembly” ignored → resume `master_finalize` (product path, not soft-complete).

## Quality & cleanup
| Gate | Result |
|------|--------|
| verify_master | OK — LUFS −16.00, TP −1.00, 48 kHz, 2792.50s |
| listen delight | `passed=True` overall **0.9676** (authoritative post_master; failed_dimensions=[]) |
| PMQ | `status=pass` `publish_allowed=True` failed_checks=[] |
| local publish | `publish/audio.mp3` + `publish/cover.jpg` + `.stage_done/podcast_publish` |
| S3 | blocked on operator G-Publish consent (quality advisories); local ship OK (`publish=yes`) |
| daemon | stopped |
| nudge §3.0a | killed (PID 13122) |

## Later review
Intervene log: `.cursor/plans/full_auto_forensics_state.md` (i1–i14). No End-* / predicate-family ledger mapping during campaign.
