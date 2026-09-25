# Forensics loop state

- **campaign_mode:** fresh_campaign_continue_on_bug
- **INPUT_FILE:** mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3
- **run_id:** exec_13198_d19c15b58ab4_20260924T214444Z
- **fresh_launches:** 1
- **driver_restarts:** 19
- **started_at:** 2026-09-24T21:44:44Z
- **shipped_at:** 2026-09-25T05:23:38Z
- **last_progress_at:** 2026-09-25T05:23:38Z
- **driver_alive:** false
- **stages_done:** 73
- **current_stage:** podcast_publish (ship_bar_complete)
- **ship:** true
- **nudge_pid:** killed (was 13122)
- **end_report:** .cursor/plans/full_auto_forensics_end_report_exec_13198.md
- **notes:** §2 local ship. Master 256MiB / 2792.50s; verify_master OK; delight 0.9676 pass; PMQ publish_allowed=true; publish package ready; S3 deferred (G-Publish advisory consent).

## Intervene log

### i1 — 2026-09-24T23:05:00Z
- **predicate:** budget.dispatch_cap_refusal — max_invokes on missing_framing + batch_fill
- **producer:** missing_framing
- **fix:** BudgetExemption `missing_framing_batch_fill` when unscored fills remain.
- **test:** tests/test_p15_budget_door.py::test_batch_fill_incompleteness_grants_walk_door_grace (MUX_FORENSICS=0)
- **continued_from:** missing_framing

### i2 — 2026-09-24T23:12:00Z
- **predicate:** _missing_framing_batch_fill_incompleteness — superseded fill duplicates
- **producer:** missing_framing
- **fix:** Last-wins per segment_id in gap evaluations incompleteness.
- **test:** tests/test_hg3_missing_framing_batch.py::test_hg3_superseded_fill_duplicate_does_not_block_done (MUX_FORENSICS=0)
- **continued_from:** missing_framing

### i3 — 2026-09-24T23:25:00Z
- **predicate:** selection_sanitary framing:primary impact + mid_arc_reverse_jump from append restore
- **producer:** selection_order_sanitize / framing_coverage_guard
- **fix:** Sanitize calls apply_selection_constraints; restore inserts by tape start_ms (not append).
- **test:** tests/test_artifact_sanitize_selection.py::test_sanitize_restores_primary_impact_not_selected (MUX_FORENSICS=0)
- **continued_from:** selection_order_sanitize → nugget_layup_compose

### i4 — 2026-09-24T23:35:00Z
- **predicate:** attempt_memo refuse while layup_compose_shards_pending (shard 1/2)
- **producer:** dispatch_delta.memo_skip / nugget_layup_compose
- **fix:** memo_skip yields when incompleteness contains `shards_pending` and resume pins same stage.
- **test:** tests/test_p15_attempt_memo.py::test_memo_skip_yields_when_incompleteness_resumes_same_stage (MUX_FORENSICS=0)
- **continued_from:** nugget_layup_compose

### i5 — 2026-09-24T23:42:00Z
- **predicate:** layup LLM transcript_excerpt on garbled seg_070; heal_on_air release_false restore; authority_undo thrash
- **producer:** media_ip_cta / thrash_hardening
- **fix:** Punch host extras after heal; release_false keeps editorial excludes; authority_undo exempts media_ip_cta.
- **test:** tests/test_media_ip_cta.py::test_execute_cta_omit_keeps_garbled_degraded_scrap_off_air_after_heal (MUX_FORENSICS=0)
- **continued_from:** nugget_layup_compose

### i6 — 2026-09-24T23:48:00Z
- **predicate:** selection_commit_refused + authority_undo hash_oscillation stranding layup
- **producer:** dispatch_delta.resume_after_intervene / thrash_hardening
- **fix:** resume clears selection_commit_refused + authority_undo; thrash exempts nugget_layup after media_ip_cta.
- **test:** tests/test_p15_attempt_memo.py::test_resume_after_intervene_clears_selection_undo_and_refuse (MUX_FORENSICS=0)
- **continued_from:** nugget_layup_compose

### i7 — 2026-09-24T23:55:00Z
- **predicate:** seg_070 re-admitted after release_false cleared never_touch (drop_never_touch_cta not editorial)
- **producer:** media_ip_cta.is_editorial_exclude_reason / release_false_cta_never_touch
- **fix:** drop_never_touch_cta is editorial; late-tape short scraps stay never-touch.
- **test:** tests/test_media_ip_cta.py::test_execute_cta_omit_keeps_garbled_degraded_scrap_off_air_after_heal (extended) (MUX_FORENSICS=0)
- **continued_from:** nugget_layup_compose

### i8 — 2026-09-24T23:58:00Z
- **predicate:** apply_selection_constraints restored CTA primary seg_070; layup re-asked empty-text excerpt after omit
- **producer:** framing_coverage_guard / media_ip_cta fragmentary tokens / llm_simple demote
- **fix:** Framing restore skips never_touch + editorial CTA; expand fragmentary tokens; demote CTA needs even when already omitted.
- **test:** tests/test_framing_coverage_guard.py::test_enforce_framing_does_not_restore_media_ip_cta_primary; tests/test_media_ip_cta.py::test_empty_text_temporary_omission_is_cta_omit_need (MUX_FORENSICS=0)
- **continued_from:** nugget_layup_compose (driver restart #9)

### i9 — 2026-09-25T00:47:28Z
- **predicate:** high_gap_unframed seg_014 with layup hollow-done; gap_report unpaid under layup producer_stage
- **producer:** stage_completion._high_gap_unframed_incompleteness / done_authority.shared_path_producer_mismatch
- **fix:** high_gap incompleteness includes nugget_layup_compose; gap_report land accepts ownership co-producers (layup/framing).
- **test:** tests/test_i3_omit_demote_high_gap.py::test_high_gap_unframed_also_blocks_layup_done; tests/test_unpaid_land_matrix.py::test_gap_report_layup_co_producer_is_paid_land (MUX_FORENSICS=0)
- **continued_from:** nugget_layup_compose (serve+driver restart #11)

### i10 — 2026-09-25T01:27:00Z
- **predicate:** edl_narrative_audit thrash — chapter orphans seg_012/028; repair blank-dropped hard_keep seg_028 → sanitize hard_keep_missing
- **producer:** artifact_repairs.repair_master_selection blank_drop
- **fix:** Never blank-drop hard-keep segment ids; committed chapter fill for orphans.
- **test:** tests/test_media_ip_cta.py::test_repair_master_selection_keeps_hard_keep_short_blankish (MUX_FORENSICS=0)
- **continued_from:** edl_narrative_audit (serve+driver restart #12)

### i11 — 2026-09-25T01:41:00Z
- **predicate:** edl_narrative stale chapter_continuity_broken + blank_segment hard_keep; selection unpaid land (producer=edl_narrative_audit); authority_undo thrash sanitize↔edl_narrative_metadata_align
- **producer:** artifact_repairs._edl_issue_contradicted_by_disk / done_authority co-producers / thrash_hardening
- **fix:** Demote chapter blockers when membership filled; demote blank_segment when on-air hard-keep; selection_order_sanitize accepts edl_narrative_* land stamps; exempt selection metadata co-write oscillation.
- **test:** tests/test_artifact_repairs_p1.py::test_repair_edl_audit_demotes_filled_chapter_and_hard_keep_blank; tests/test_unpaid_land_matrix.py::test_selection_edl_narrative_co_producer_is_paid_land; tests/test_sanitize_authority_thrash.py::test_selection_metadata_align_sanitize_oscillation_not_halt (MUX_FORENSICS=0)
- **continued_from:** edl (serve+driver restart #13)

### i12 — 2026-09-25T01:55:00Z
- **predicate:** edl_narrative_qc strict — repair_edl_narrative_selection blank-dropped hard_keep seg_028 → sanitize hard_keep_missing; EDL omit blank → speech/order mismatch
- **producer:** artifact_repairs.repair_edl_narrative_selection / stages.assembly._prepare_locked_selection / air_order_boundary._drop_blank_segments_under_freeze
- **fix:** Exempt hard-keep ids from blank-drop in narrative repair, EDL prepare, and freeze blank-drop; build_flow1_edl keeps hard-keeps even when speech_dur < 400ms (raw span / 400ms floor).
- **test:** tests/test_media_ip_cta.py::test_repair_edl_narrative_selection_keeps_hard_keep_blank; test_prepare_locked_selection_keeps_hard_keep_blank; test_build_flow1_edl_keeps_hard_keep_short_speech (MUX_FORENSICS=0)
- **continued_from:** edl (serve+driver restart #15)

### i13 — 2026-09-25T02:12:00Z
- **predicate:** after EDL seal, selection_order_sanitize unpaid land — producer_stage='selection'
- **producer:** done_authority._SHARED_PATH_LAND_CO_PRODUCERS
- **fix:** Accept alias stamps `selection` and `artifact_sanitize.selection` as paid land for selection_order_sanitize.
- **test:** tests/test_unpaid_land_matrix.py::test_selection_alias_producer_stage_is_paid_land (MUX_FORENSICS=0)
- **continued_from:** assembly_preview (serve+driver restart #16)

### i14 — 2026-09-25T04:14:53Z
- **predicate:** remaining_stages / unpaid_land(mix) burns ~12–23s in pure-Python VO DFT (vo_speech_qa._tonal_peak_ratio) on every incomplete heal
- **producer:** vo_speech_qa.analyze_vo_wav / _tonal_peak_ratio
- **fix:** numpy rFFT for tonal peak; path+mtime+size+cfg analyze cache (max 256)
- **test:** tests/test_vo_speech_qa.py::test_analyze_vo_wav_caches_by_mtime + test_tonal_peak_numpy_rejects_pure_tone (MUX_FORENSICS=0)
- **continued_from:** mmaudio_sfx (serve+driver restart #19)
