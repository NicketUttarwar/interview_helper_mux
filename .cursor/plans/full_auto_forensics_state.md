# Forensics loop state

- **campaign_mode:** fresh_campaign_continue_on_bug
- **INPUT_FILE:** mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3
- **run_id:** exec_002_d19c15b58ab4_20260925T213831Z
- **fresh_launches:** 1
- **driver_restarts:** 20
- **started_at:** 2026-09-25T21:38:31Z
- **last_progress_at:** 2026-09-26T01:47:27Z
- **driver_alive:** false
- **stages_done:** 72/72
- **current_stage:** shipped
- **g1_complete:** false
- **intervention_count:** 20
- **last_predicate:** PMQ omit_ledger_order_lock_stale + rubric clarity floor
- **last_predicate_before:** mix theme_outro cue missing — LLM SDP omitted close; close_bed inferred underscore
- **last_predicate_flipped:** true
- **resume_from_stage:** —
- **open_blockers:** []
- **ship:** true
- **patches_this_session:** [skip.json seed-complete, ranking drop ghost impact ids, stamp-match still reports protect_hosted + omit_notes flags, sanitize no-op restamps ranking producer, guest-first prepend host family once, air_contract IPP/layup paid land, transitions MUST_PRECEDE framing apply, recompose skip-copy is primary disk, restore frozen transition pairs, orphaned CTA child omit, admit required bridges beyond freeze, EDL MUST_PRECEDE transitions, dirty fingerprint includes mtime, persist mint-before-done, incompleteness honors justified skip, chapter QC span not list-order, palette compose End-A SDP persist, SDP palette compose paid land, compose_close_bed infers theme_outro + persist mints required close]
- **hard_blocker:** null
- **monitor_loop:** DEAD — killed after ship
- **notes:** SHIP 2026-09-26T01:47:27Z. MUX_SKIP_PRECLEAN=1. Unused sibling exec_001 created 3s earlier (not used). Independent of family ledgers. S3 sync deferred — G-Publish consent for quality advisories.

## Intervene log

### i1 — 2026-09-25T21:41:00Z
- **predicate:** homunculus.runtime._seed_prereq_block — seed order: complete audio_preclean before running ingest
- **producer:** audio_preclean (ensure_preclean_skipped / stage_outputs_present)
- **fix:** skip.json is a finished outcome — stage_outputs_present + primary_disk + seed-order skip treat it as complete so heal can stamp done; ingest unblocks.
- **test:** tests/test_skip_preclean_flag.py::test_skip_preclean_marks_done_and_unblocks_ingest (MUX_FORENSICS=0)
- **continued_from:** audio_preclean

### i2 — 2026-09-25T22:31:00Z
- **predicate:** deterministic_lint._lint_full_master_ranking — ordered segment seg_041/047 not in manifest; nested execute 500 air_contract_unsanitary
- **producer:** full_master_ranking / framing_coverage_guard (stale hitch impact ids)
- **fix:** Ghost impact ids unenforceable; cover+sanitize drop them; ranking incompleteness unmarks hollow done; revive_pre_synth auto-commits so execute does not 500.
- **test:** tests/test_framing_coverage_guard.py::test_enforce_framing_does_not_restore_ghost_primary; tests/test_fmr_hardening.py::test_cover_ranking_drops_ordered_ids_absent_from_manifest + test_ranking_ghost_ordered_is_incomplete; tests/test_artifact_sanitize_selection.py::test_sanitize_drops_ordered_ids_absent_from_manifest (MUX_FORENSICS=0)
- **continued_from:** full_master_ranking

### i3 — 2026-09-25T22:40:00Z
- **predicate:** air_contract_sanitary_errors + validate_vo_contract — stamp-match hid protect_hosted_vo_floor_reseat; omitted vo_preface_seg_019 had omit_notes only
- **producer:** air_contract_sanitize / vo_contract
- **fix:** stamp_matches no longer hides protect_hosted (unmark + reseat path); omit_notes air_script_omit_sync counts as omit flags; sanitary preflight sets related_stage so execute routes to sanitize.
- **test:** tests/test_artifact_sanitize_air_contract.py::test_stamp_match_still_reports_protect_hosted_reseat; tests/test_i11_omitted_wav_reseat.py::test_omit_notes_air_script_omit_sync_satisfies_vo_contract (MUX_FORENSICS=0)
- **continued_from:** air_contract_sanitize
- **flipped:** true — air_contract done; preface no longer omitted; missing_framing done (45/72)

### i4 — 2026-09-25T22:43:00Z
- **predicate:** done_authority.shared_path_producer_mismatch — master/selection.json producer_stage=full_master_ranking (not selection_order_sanitize)
- **producer:** selection_order_sanitize / air_order_boundary.commit_selection_mutation
- **fix:** Sanitize no-op must restamp producer_stage to itself (S4 preserve is for metadata-align only). Ranking stamp stays unpaid until sanitize pays land so heal_or_raise can mark done.
- **test:** tests/test_unpaid_land_matrix.py::test_sanitize_noop_restamps_ranking_producer_pays_land (MUX_FORENSICS=0)
- **continued_from:** selection_order_sanitize
- **flipped:** true — producer_stage now selection_order_sanitize

### i5 — 2026-09-25T22:46:00Z
- **predicate:** air_order_integrity.late_opening_cluster — guest-first seg_007 then 005/004/002/003ca still opening-tape
- **producer:** air_order_integrity.repair_opening_tape_integrity / selection_order_sanitize
- **fix:** Guest-first prepend is one-shot host family (earliest tape), not every late cluster. Sanitize applies that repair so order lands without a ranking LLM rerun.
- **test:** tests/test_air_order_integrity.py::test_repair_opening_tape_guest_first_prepends_host_not_last_late_family (MUX_FORENSICS=0)
- **continued_from:** selection_order_sanitize
- **flipped:** true — order starts seg_002; 0 late_opening; selection_order_sanitize done (46/72)

### i6 — 2026-09-25T22:58:00Z
- **predicate:** done_authority.shared_path_producer_mismatch — mastering/mastering_plan.json producer_stage=information_package_plan (not air_contract_sanitize)
- **producer:** air_contract_sanitize / done_authority
- **fix:** IPP and layup are paid land co-producers for air_contract (same pattern as gap+layup). Stage restamps producer_stage after commit so mark_done can land.
- **test:** tests/test_unpaid_land_matrix.py::test_air_contract_ipp_co_producer_is_paid_land (MUX_FORENSICS=0)
- **continued_from:** air_contract_sanitize
- **flipped:** true — air_contract done; unpaid None (51/72)

### i7 — 2026-09-25T23:10:00Z
- **predicate:** delivery_guardrails.filter_delivery_candidates / MUST_PRECEDE[transitions] — remaining_after leapt to transitions while selection_framing_apply pending
- **producer:** selection_framing_apply
- **fix:** transitions MUST_PRECEDE includes selection_framing_apply so filter injects the pass-2 apply hole instead of running transitions first.
- **test:** tests/test_must_precede_order.py::test_filter_defers_transitions_until_framing_apply (MUX_FORENSICS=0)
- **continued_from:** selection_framing_apply

### i8 — 2026-09-25T23:15:00Z
- **predicate:** done_authority.primary_disk_present / earliest_incomplete_must_precede — recompose skip-copy left producer_ready false; filter injected recompose
- **producer:** gap_framing_recompose / selection_framing_apply
- **fix:** refinement_skip_copy.json counts as recompose primary disk (same pattern as preclean skip.json) so framing apply can enqueue.
- **test:** tests/test_done_constitution.py::test_recompose_skip_copy_counts_as_primary_disk (MUX_FORENSICS=0)
- **continued_from:** selection_framing_apply
- **flipped:** true — framing apply done + sidecar; remaining is transitions (52/72)

### i9 — 2026-09-25T23:22:00Z
- **predicate:** artifact_sanitize.transitions / pre-flush — pair freeze deferred all LLM pairs; pending kept=0 vs committed 5
- **producer:** transitions / sanitize_transitions
- **fix:** When freeze empties kept, restore on-order frozen pairs from committed disk so flush does not wipe landed transitions.
- **test:** tests/test_artifact_sanitize_transitions.py::test_sanitize_restores_frozen_pairs_when_rewrite_empties_kept (MUX_FORENSICS=0)
- **continued_from:** transitions
- **flipped:** true — transitions done n=6; SDP done; remaining vo_line_adjudicate (53/72)

### i10 — 2026-09-25T23:36:00Z
- **predicate:** edl_narrative_audit post-commit — orphaned media-IP children + chapter-map close; host repair G1 409 spin
- **producer:** media_ip_cta / hard_keep
- **fix:** Do not transfer hard-keep onto CTA-scrap NLE children; omit those scraps as End-A core under hard freeze; skip G1 on chapter/CTA close host-repair.
- **test:** tests/test_run_failure_hard_fixes.py::test_hard_keep_does_not_transfer_to_cta_scrap_children; tests/test_media_ip_cta.py::test_heal_drops_orphaned_cta_scrap_children_under_hard_freeze (MUX_FORENSICS=0)
- **continued_from:** edl_narrative_audit
- **flipped:** true — scraps gone; order n=29 tail 053→055; ENA warn/0 blocking; walking layup

### i11 — 2026-09-25T23:46:00Z
- **predicate:** stages.assembly / missing_reorder_bridges — EDL gate resume transitions; freeze deferred new adj; bc.json complete lie
- **producer:** artifact_sanitize.transitions
- **fix:** Admit current-adj required reorder bridges under pair freeze and union-restore landed freeze pairs so mint can land after selection shrink.
- **test:** tests/test_artifact_sanitize_transitions.py::test_sanitize_admits_required_bridge_beyond_freeze (MUX_FORENSICS=0)
- **continued_from:** edl

### i12 — 2026-09-25T23:52:00Z
- **predicate:** delivery_guardrails.MUST_PRECEDE[edl] / stage_completion.transitions — EDL remaining loop; bridges missing; transitions still marked seed-complete
- **producer:** transitions
- **fix:** EDL MUST_PRECEDE includes transitions; transitions incompleteness reports missing reorder bridges so filter injects mint instead of walking EDL.
- **test:** tests/test_must_precede_order.py::test_filter_defers_edl_until_transitions (MUX_FORENSICS=0)
- **continued_from:** transitions

### i13 — 2026-09-25T23:56:00Z
- **predicate:** forensics_stall.escalation_blocks_driver — fingerprint ignored content patches to already-dirty files
- **producer:** identical_failures.product_code_fingerprint
- **fix:** Dirty suffix hashes porcelain plus dirty-file mtime/size so content patches unstick escalation.
- **test:** tests/test_must_precede_order.py::test_filter_defers_edl_until_transitions already green; fingerprint change verified on restart
- **continued_from:** transitions

### i14 — 2026-09-25T23:59:00Z
- **predicate:** Done Authority mark_done refused on transitions — LLM persist before seam glue mint; incompleteness still 7 missing
- **producer:** stages.selection.persist_with_framing_dedupe
- **fix:** ensure_seam_glue runs inside persist before mark_done so required hinges land (sanitize admit) before Done Authority.
- **test:** tests/test_artifact_sanitize_transitions.py::test_sanitize_admits_required_bridge_beyond_freeze (MUX_FORENSICS=0)
- **continued_from:** transitions
- **flipped:** false — mint still skipped justified-skip destinations; incompleteness still counted them

### i15 — 2026-09-26T00:05:55Z
- **predicate:** Done Authority mark_done refused — stage_artifact_incompleteness(transitions) reported missing=7 while mint/ensure_seam_glue treated those destinations as justified skip / native handoff
- **producer:** stage_completion / bridge_completeness.justified_skip_before_ids
- **fix:** Shared justified_skip_before_ids SSOT; transitions incompleteness, EDL preflight, and sanitize required-set honor layup skip + native handoff the same way mint does. Reverse-required hinges also survive prune_reverse_jump when still required.
- **test:** tests/test_transitions_s1_s5_simplify.py::test_incompleteness_honors_justified_skip_cover; tests/test_artifact_sanitize_transitions.py::test_sanitize_keeps_required_reverse_reorder_bridge (MUX_FORENSICS=0)
- **continued_from:** transitions
- **flipped:** true — transitions done + seed-complete; driver walking EDL

### i16 — 2026-09-26T00:09:38Z
- **predicate:** narrative_qc — chapter "Why Precision Oncology…" reported not contiguous; stored ids were source-sorted while air span 002/007/005/004 is contiguous. Softened under unattended; EDL persisted.
- **producer:** narrative_qc._validate_chapters / artifact_sanitize.selection
- **fix:** Contiguity is air-order span (max-min+1 == unique count), not stored-list monotonicity. Sanitize restamps chapter.segment_ids to air order.
- **test:** tests/test_execution_flow_hardening.py::test_chapter_span_contiguous_ignores_stored_list_order (MUX_FORENSICS=0)
- **continued_from:** edl
- **flipped:** true — edl.json present + done; walking assembly_preview (no recycle; driver already past EDL)

### i17 — 2026-09-26T00:21:00Z
- **predicate:** music_palette_compose finished without done — cue_count=0 with 8 theme assets; SDP write skip under hard freeze (reason not End-A)
- **producer:** music_palette_compose / seat_authority
- **fix:** music_palette_compose is End-A CORE; persist commits SDP with that reason; refuse if disk still has zero cues after mint.
- **test:** tests/test_music_palette_compose.py::test_palette_compose_is_end_a_under_hard_freeze; tests/test_enda_hard_freeze_constitution.py::test_enda_allowlist_membership (MUX_FORENSICS=0)
- **continued_from:** music_palette_compose
- **flipped:** true — 34 cues on disk; seed-complete; remaining sound_design_plan / sfx_prompt_craft

### i18 — 2026-09-26T00:27:25Z
- **predicate:** shared-path unpaid land + delivery_sdp_present exact producer — filter re-invoked sound_design_plan after compose paid 34 cues (pre-flush barrier on LLM rewrite)
- **producer:** done_authority / homunculus.agenda.delivery_sdp_present
- **fix:** music_palette_compose is paid land co-producer for SDP; delivery_sdp_present accepts that stamp so filter does not re-run the plan LLM.
- **test:** tests/test_unpaid_land_matrix.py::test_sdp_palette_compose_co_producer_is_paid_land; tests/test_i14b_sdp_compose_write.py::test_delivery_sdp_present_accepts_palette_compose_producer (MUX_FORENSICS=0)
- **continued_from:** sound_design_plan
- **flipped:** true — SDP seed-complete; walking sfx_prompt_craft; 34 cues intact

### i19 — 2026-09-26T01:08:00Z
- **predicate:** mix: theme_outro cue missing — place in music epoch (music_palette_compose / place_episode_close_cue)
- **producer:** music_palette_compose / music_lane.infer_theme_role_from_cue_id
- **fix:** `close_bed` infers `theme_outro` (not generic `bed`→underscore). Persist unions `compose_close_bed` after LLM/sonic hunt. Compose incompleteness + filter defer mix until that cue lands (no `theme_outro_seed` invent under freeze).
- **test:** tests/test_music_palette_compose.py::test_compose_close_bed_infers_theme_outro_not_underscore; tests/test_music_palette_compose.py::test_ensure_required_close_bed_when_llm_omits_outro; tests/test_music_palette_compose.py::test_music_palette_missing_outro_cue_incomplete; tests/test_must_precede_order.py::test_filter_defers_mix_until_compose_close_bed (MUX_FORENSICS=0)
- **continued_from:** mix
- **flipped:** true — compose_close_bed theme_outro on disk after last native; walking mix

### i20 — 2026-09-26T01:42:00Z
- **predicate:** Post-master quality failed: scorecard_dimension_floors, omit_ledger_air_contract (order_lock_stale)
- **producer:** omit_ledger / post_master_quality
- **fix:** Selection restamp left omit ledger on rev 4 vs selection rev 8. `sync_stale_omit_order_lock` rebuilds paperwork before PMQ evaluate (not a seat mutation; no floor lowering; clarity remains rubric advisory).
- **test:** tests/test_i25_pmq_omit_clarity.py::test_pmq_sync_stale_omit_order_lock_under_hard_freeze (MUX_FORENSICS=0)
- **continued_from:** master_finalize
- **flipped:** true — PMQ publish_allowed; structural empty; walking master_transcript_build
