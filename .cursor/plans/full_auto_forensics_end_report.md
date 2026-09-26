# Full-auto forensics end report

Current campaign: **`exec_002_d19c15b58ab4_20260925T213831Z`** (2026-09-25/26) — [full write-up](full_auto_forensics_end_report_exec_002.md). Prior campaigns archived below.

---

## What happened

INPUT `mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3` → **ship** (local episode package) on run_id
`exec_002_d19c15b58ab4_20260925T213831Z`.

- `fresh_launches = 1` (one `MUX_FRESH=1` kickoff; every fix continued this same run_id)
- **20 interventions** (i1–i20); 20 driver restarts on the same run_id
- `MUX_SKIP_PRECLEAN=1`; master `master/master.wav` 242,577,102 B (~42:07); `publish/audio.mp3` + cover
- Window: 2026-09-25T21:38:31Z → 2026-09-26T01:47:27Z
- Per-intervene log: [full_auto_forensics_state.md](full_auto_forensics_state.md)

## Ship verification (§2)

| Gate | Result |
|------|--------|
| `master/master.wav` | yes (242577102 B) |
| `tools/verify_master.py` | **OK** LUFS −16.00 / TP −1.00 / 48 kHz |
| listen delight | overall **0.969**, failed_dims=[] |
| PMQ `publish_allowed` | **true** (structural=[]) |
| Local package | `publish/package_ready.json`, `audio.mp3`, `cover.jpg` |
| S3 upload | deferred — quality advisories need G-Publish consent |

## Daemon / nudge

Stopped after ship (`full_auto_daemon_launch stop` + killed §3.0a nudge PID 60040).

---

## Archived: exec_13159 (2026-09-18/19)

---

## What happened

INPUT `mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3` → **ship** (local episode package) on run_id
`exec_13159_d19c15b58ab4_20260918T235157Z`.

- `fresh_launches = 1` (one `MUX_FRESH=1` kickoff; every fix continued this same run_id)
- **11 interventions** (i1–i9 family; see state file); driver relaunched on the same run_id after patches
- Homunculus `0.2.0`
- Master `master/master.wav` 161,181,774 B (~28:00); `publish/audio.mp3` 40,297,160 B; cover + `package_ready.json`
- Window: 2026-09-18T23:51:57Z → 2026-09-19T03:15:52Z
- Per-intervene log: [full_auto_forensics_state.md](full_auto_forensics_state.md)

## Ship verification (§2)

| Gate | Result |
|------|--------|
| `master/master.wav` | yes (161181774 B) |
| `tools/verify_master.py` | **OK** LUFS −16.03 / TP −1.00 / 48 kHz |
| listen delight | overall **0.9547**, failed_dims=[] |
| PMQ `publish_allowed` | **true** (structural=[]) |
| Local package | `publish/package_ready.json`, `audio.mp3`, `cover.jpg` |
| S3 upload | deferred — quality advisories need G-Publish consent |

## Root causes fixed (this campaign)

| # | Predicate (short) | Producer / root cause | Cascade |
|---|-------------------|-----------------------|---------|
| i1–i4 | MSA $ref; layup wordcap; boundaries; CAP | prior session patches | (see state) |
| i5/i5b | hollow EDL without audit; matrix mismatch | delivery gate + forensics restamp | delivery audit / matrix tests |
| i6–i6d | sealed layup adopt wrong stage_key; freeze-sticky rewind | assembly/driver/seed_policy | layup owner + sealed shard tests |
| i7 | critical remaster mislabeled budget exhaust | junction remaster path | `test_jsq_critical_remaster_path` |
| i8 | mix⇄junction assembly.wav deadlock | `junction_recut_precedes_mix` | precedes-when-assembly-missing |
| i9 | junction remaster drops mix QC; stale ship-bar defects | `promote_staged_side_effects` + defect reconcile | `test_i9_junction_remaster_promotes_mix_qc.py` |

## Open advisories (aspirational — did not block local ship)

- `scorecard_dimension_floors` (clarity 0.7946 < 0.80 — low synthetic share)
- `planned_music_preserved` / `episode_close_outro_present` — `music_cue_coverage.json` still absent on disk because post-ship remaster is refused by live `on_a_roll` on `seg_057` (junction `critical_count=0`). i9 promote path is in code for the next remaster.

## Daemon / nudge

Stopped after ship (`full_auto_daemon_launch` stack shutdown + killed §3.0a nudge PID 34728).

---

## Prior campaign archive

### Archived: previous current campaign

## What happened

INPUT `mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3` → **ship** (local episode package) on run_id
`exec_11871_d19c15b58ab4_20260916T002245Z`.

- `fresh_launches = 1` (one `MUX_FRESH=1` kickoff; every fix continued this same run_id)
- **54 interventions** (i1–i54); driver relaunched on the same run_id after each patch
- Homunculus `0.1.0`; final `artifact_ownership_matrix_version = 34bb7653a50b58b8`
- 74 `stage_done`; master `master/master.wav` 255,661,710 B (44:23); package under `publish/` (7 files)
- Window: 2026-09-16T00:22:45Z → 12:10:15Z; 158,768 `gui_log.jsonl` lines
- Per-intervene log (predicate → producer → files → test): [full_auto_forensics_state.md](full_auto_forensics_state.md).
  Rows i12–i54 are verbatim; **i1–i11 were trimmed from that file mid-run** — their subjects are recovered
  below from the cascade fixtures that still carry their ids.

Dominant failure by volume was the `junction_snip_qa` ⇄ `mix` deadlock (4,582 `incomplete_cut*` log lines,
1,642 identical-failure escalations), followed by the fail-closed ownership class (1,199 `authority_denied`
lines — **zero** in the previous campaign, which ran before ownership went fail-closed).

## Root causes fixed

Bands: **OWN** = write authority / catalog · **SEAT** = seat order & gate deadlock · **CONTENT** = audible
product defect · **SHIP** = ship-gate honesty · **OPS** = operator/driver scaffold.

| # | Band | Predicate (short) | Producer / root cause | Files | Cascade test |
|---|------|-------------------|-----------------------|-------|--------------|
| i1 | OWN | G0 gate raised before flush | `transcript_review_build` gate ran ahead of staging flush | G0 gate path | `test_i1_g0_flush_before_gate.py` |
| i2 | OWN | G0 signoff could not `mark_done` | signoff acceptance | G0 signoff path | `test_i2_g0_signoff_mark_done.py` |
| i3 | OWN | `unknown_path` volley pack glob | volley-pack writer uncataloged | `artifact_ownership.py` | `test_i3_volley_pack_ownership.py` |
| i4 | OWN | `not_allow segments/manifest.json` | `vernacular` seats manifest rows | `artifact_ownership.py` | `test_i4_vernacular_may_persist_manifest` |
| i5 | OWN | `not_allow segments/manifest.json` | `connector_fuse` | `artifact_ownership.py` | `test_i5_connector_fuse_may_persist_manifest` |
| i6 | OWN | `not_allow boundaries/rounds` | `connector_fuse` | `artifact_ownership.py` | `test_i6_connector_fuse_may_persist_boundaries_and_rounds` |
| i7 | OWN | DENY research field notes | research wave writer | `artifact_ownership.py` | `test_i7_research_wave_field_notes_allowed` |
| i8 | OWN | `not_allow voice_reference` | GUI voice-reference candidates | `artifact_ownership.py` | `test_i8_voice_reference_candidates_allowed_for_gui` |
| i9 | OWN | `not_allow stage_runs` | `last_volley_input` telemetry | `artifact_ownership.py` | `test_i9_stage_runs_last_volley_input_allowed` |
| i10 | OWN | `unknown_path evidence_packets` | direct-child packet write | `artifact_ownership.py` | `test_i10_evidence_packets_direct_child_allowed` |
| i11 | OWN | `not_allow refinement_champion` | gap-VO champion scorer | `artifact_ownership.py` | `test_i11_refinement_champion_gap_vo_allowed` |
| i12 | OWN | `not_allow reorder_bridges.json` | `full_master_ranking` | `artifact_ownership.py` | `test_i12_full_master_ranking_reorder_bridges_allowed` |
| i13 | OWN | `not_allow mastering_plan.json` | `information_package_plan` | `artifact_ownership.py` | `test_i13_information_package_plan_may_write_mastering_plan` |
| i14 | OWN | `not_allow` plan/layup + `transcripts/vo` | `nugget_layup_compose`, `gap_framing_recompose` | `artifact_ownership.py` | `test_i14_nugget_and_recompose_ownership` |
| i15 | OWN | `not_allow gap_report.json` | `selection_framing_apply` rebase | `artifact_ownership.py` | `test_i15_selection_framing_apply_may_rebase_gap_report` |
| i16 | OWN | `unknown_path synthetic_context_packet` | `transitions` packet commit | `artifact_ownership.py` | `test_i16_synthetic_context_packet_allowed_for_transitions` |
| i17 | OWN | `not_allow gap_report` + `refinement_shadow` | `vo_line_adjudicate`, shadow scorer | `artifact_ownership.py` | `test_i17_vo_line_adjudicate_and_shadow_ownership` |
| i18 | OWN | `authority_denied selection.json:edl:hard_freeze` | `run_edl` persisted its own selection repairs | `stages/assembly.py` | `test_i18_edl_never_rewrites_frozen_selection.py` |
| i19 | OWN | `authority_denied gap_report:edl:hard_freeze` | `_commit_edl_gap_report` | `stages/assembly.py` | same file (i19 cases) |
| i20 | OWN | same predicate persisted after i19 | `opening_orientation.retarget_orientation_to_open` | `opening_orientation.py` | `test_i20_orientation_retarget_skips_frozen_gap_report` |
| i21 | OWN | `authority_denied reorder_bridges:edl` | `seam_glue.rebuild_reorder_bridges` | `seam_glue.py` | `test_i21_seam_glue_skips_frozen_reorder_bridges` |
| i22 | OPS | `authority_denied deferred_transition_pairs` ×70 → stack jam | read-side sync persisted from any consumer, incl. the `get_job` API path → `master/.write.lock` contention | `transition_vo.py` | `test_i22_deferred_pairs_sync_skips_sealed_doc` |
| i23 | OWN | `authority_denied sound_design_plan` | `music_palette_compose`, `sfx_prompt_craft`, `sound_design_vo_finalize` were not owners | `artifact_ownership.py` | `test_i23_sound_design_plan_cue_writers_allowed` |
| i24 | OWN | `unknown_path master/sfx/manifest.json` | `mmaudio_sfx` bed manifest + WAVs uncataloged | `artifact_ownership.py` | `test_i24_master_sfx_manifest_and_wavs_allowed` |
| i25 | SEAT | `incomplete_cut_unresolved` → `class_failure x3 halt` | mix refuses on live criticals and pins junction; `_seed_prereq_block` refuses junction behind mix — nobody could recut | `homunculus/runtime.py` | `test_i25_junction_recut_before_first_mix.py` |
| i25b | SEAT | `500: Missing master/assembly.wav` | runner preflight hard-required an artifact only mix can mint | `stage_input_checks.py` | same file |
| i25c | SEAT | `Prerequisite stage mix is not complete` | third gate (`llm_flow_hardening`); introduced SSOT `junction_recut_precedes_mix` | `llm_flow_hardening.py`, `junction_snip_qa.py` | same file |
| i25d | SEAT | conductor kept pinning front to `mix` | `constrain_conductor_to_seed_front` | `homunculus/agenda.py` | same file |
| i25e | SEAT | `assembly_not_rendered_from_current_edl` | freshness can never hold pre-mix | `air_order.py` | same file |
| i26 | OWN | `authority_denied sound_design_plan:junction` | `_patch_sdp_cue_crossfade` mirrored into a sealed SDP | `junction_snip_qa.py` | `test_i26_junction_does_not_rewrite_sealed_sdp` |
| i27 | OWN | `authority_denied selection.json:junction_snip_qa` | fuse/omit is junction's only resolution for an unrecoverable cut, but it owned no selection seat | `artifact_ownership.py` | `test_i27_junction_may_omit_from_selection` |
| i28 | SEAT | ladder could not clear `unrecoverable_within_clip` | junction's inner remaster hit its own mix refusal; no escalation for a noop in-clip repair | `junction_snip_qa.py` | `test_i28_unrecoverable_cut_escalates.py` |
| i29 | SEAT | inner-remaster exemption never fired | nested feel audit `delattr`'d the outer `_junction_snip_qa_inner` marker | `junction_snip_qa.py` | `test_i29_nested_feel_audit_keeps_outer_inner_flag` |
| i30 | SEAT | `seat_freeze: opportunity_below_threshold` | seat freeze refused junction's ship-blocking omit, then restored the id | `air_order_boundary.py` | `test_i30_junction_incomplete_cut_omit_is_freeze_exempt` |
| i31 | SEAT | `publishability blocked at pre_mix` | `_check_critical_junction` refused junction's own repair round | `publishability_boundary.py` | `test_i31_inner_remaster_passes_pre_mix_critical_junction` |
| i32 | OWN | `authority_denied vo_synthesize.json` | `persist_vo_pair_gap` bookkeeping into a sealed report | `transition_vo.py` | `test_i32_vo_pair_gap_skips_sealed_report` |
| i33 | OWN | `authority_denied segments/manifest.json:edl_overlap_repair` (fatal) | overlap union + `segment_id_remap` walker uncataloged | `artifact_ownership.py` | `test_i33_*`, `test_i33b_*` |
| i34 | OWN | `authority_denied mastering_plan:air_contract_sanitize` | `reconcile_execution_contract` seat sync | `execution_contract.py` | `test_i34_reconcile_skips_sealed_mastering_plan` |
| i35 | OPS | denial storm on `operator/execution_status.json`; job lock jam | version-mismatch refusal preceded the operational carve-out — the operator lost the surfaces that would show the mismatch | `artifact_ownership.py` | `test_i35_version_mismatch_still_allows_operator_scaffold` |
| i36 | OWN | `authority_denied transcripts/speech/*` + plan rewrite | `sync_speech_sidecars` uncataloged; real plan writer was `place_episode_close_cue` | `artifact_ownership.py`, `listen_quality.py` | `test_i36_*` |
| i37 | SEAT | `speech clip order diverges from selection` (61 vs 62) | union retirement refused by seat freeze | `air_order_boundary.py` | `test_i37_overlap_union_retire_is_freeze_exempt` |
| i38 | SEAT | `edl_unsanitary: selection_edl_order_drift` (unclosable) | absorbed `seg_073` stayed in selection; with no overlap left the merge could never re-run to reconcile | `edl_overlap_repair.py`, `recovery_controller.py` | `test_i38_*` |
| i39 | CONTENT | `refuse hollow gap_report under G-Framing Yes (2 < 3)` | LLM recompose loop on a refusal recompose cannot satisfy | `nugget_layup.py` | `test_i39_floor_topup_restores_prior_authority_line` |
| i40 | OWN | `authority_denied master/transitions.json:edl` | `synthesize_spoken_transitions` persisted with hardcoded `stage_key="edl"` (a DENY row) → whole synth pass failed open | `transition_vo.py` | `test_i40_*` |
| i41 | SEAT | `mix/incomplete_cut_unresolved x83 halt` ping-pong | helper keyed on assembly *existing*; a stale `assembly.wav` stranded the recut | `junction_snip_qa.py` | `test_i41_stale_assembly_does_not_strand_the_recut` |
| i42 | CONTENT | `missing VO pickup WAV — inserted silence for [3 ids]` | EDL `vo_pickup` clips kept `source_path: null`; the only heal sat behind an input check that refused on those clips | `stages/assembly.py`, `stages/vo_synthesize.py`, `stage_input_checks.py` | `test_i42_*` |
| i43 | CONTENT | `incomplete_cut_unresolved x75 halt` | fuse refused because both sides are hard keeps, though a fuse is a lossless union | `junction_snip_qa.py` | `test_i43_*` |
| i43b | CONTENT | `skipped_no_recommendation` | a chapter *bleed* has no same-chapter neighbour by definition | `junction_snip_qa.py` | `test_i43b_*` |
| i44 | OWN | `authority_denied sound_design_plan` → remaster abort | `apply_cheap_remediation` bed trim wrote a sealed SDP | `soundscape_verify.py` | `test_i44_*` |
| i45 | CONTENT | `layup_qc:insufficient_analysis` | i39 re-aired a typed-skip row that carries no analysis fields | `nugget_layup.py` | `test_i39_floor_topup_restores_prior_authority_line` |
| i46 | CONTENT | `Overlapping speech: vo_layup_seg_047 / seg_047` (240 ms) | i42's bind replaced a 500 ms placeholder with a 17.5 s take without re-timing | `stages/assembly.py` | `test_i46_*` |
| i47 | SHIP | `committed master integrity failed after loudnorm` | loudnorm renders into staging; the gate reads `final_path`; flush only runs after `mark_done` — unsatisfiable by construction | `stages/mastering.py` | `test_i47_*` |
| i48 | SHIP | `authority_denied listen_delight_audit:master_finalize` → `mark_done:hollow` | ship pass re-scores the audit but was not a co-producer | `artifact_ownership.py` | `test_i48_*` |
| i49 | SHIP | `authority_denied seam_autopsy:master_finalize` | ship-time autopsy + ledger annotation blocked the whole post-master pass | `artifact_ownership.py`, `seam_autopsy` in `junction_snip_qa.py` | `test_i49_*` |
| i50 | SHIP | `publish/cover.jpg is pending` + `utf-8 codec can't decode 0xff` | JPEG fell through to the JSON reader; `UnicodeDecodeError` (a `ValueError`) became `status=pending` on one path and a crash on another — each round re-billed 3 cover generations | `artifact_completeness.py`, `stage_acceptance.py`, `artifact_lifecycle.py` | `test_i50_*` |
| i51 | SHIP | `unknown_path publish/chapters.json` | the whole `s3_layout.episode_files` set was uncataloged | `artifact_ownership.py` | `test_i51_*` |
| i52 | SHIP | package promised `episode.json` + `description.txt` that did not exist | undeclared staged outputs are dropped by `operator_visible_staging_path` | `web/stages.py` | `test_i52_*` |
| i53 | SHIP | `verify_master: True peak -0.40 dBTP exceeds ceiling -0.75` | limiter sat *before* `loudnorm` (whose make-up gain re-lifted peaks) **and** `_run_master_qa` waived every true-peak miss as noise | `stages/mastering.py`, `web/runner.py` | `test_i53_*` |
| i54 | SHIP | on-disk delight audit was the pre-mix advisory doc | same undeclared-staged-output class as i52, on the authoritative ship verdict | `web/stages.py`, `write_staging.py` | `test_i54_*` |

> Id collision note: the [exec-11630 status doc](../../docs/cross-cutting/exec-11630-major-errors-status.md) also
> references "i24/i25" and ships `tests/test_i24_commitment_remaster.py` / `tests/test_i25_pmq_omit_clarity.py`.
> Those are the **previous** campaign's ids, unrelated to i24/i25 above.

## Guardrails added

- Campaign cascade: **112 tests green** under `MUX_FORENSICS=0` across
  `test_i1_g0_flush_before_gate.py`, `test_i2_g0_signoff_mark_done.py`, `test_i3_volley_pack_ownership.py`,
  `test_i4_vernacular_manifest_ownership.py` (i4–i17, i23, i24, i27),
  `test_i18_edl_never_rewrites_frozen_selection.py`, `test_i25_junction_recut_before_first_mix.py` (i25a–e, i26, i41),
  `test_i28_unrecoverable_cut_escalates.py`, `test_i29_junction_ladder_can_land_omit.py` (i29–i54).
- New product guardrail: `flush_stage_writes` now logs `undeclared_owned_staging_path` whenever it drops a staged
  path the stage **is** permitted to own — the i52/i54 class can no longer be silent.
- One SSOT for pre-mix recut (`junction_snip_qa.junction_recut_precedes_mix`) consulted by all five gates that
  previously disagreed (seed order, runner preflight, LLM hardening, conductor front-pin, `assert_consumer`).
- One SSOT for bytes-only artifacts (`artifact_completeness.BINARY_ARTIFACT_SUFFIXES`, now incl. images), imported
  by `stage_acceptance` and `artifact_lifecycle`.
- True-peak honesty: overshoot is advisory only inside a 0.15 dB measurement-noise band; beyond that it refuses.

## Dead ends

- **Second fresh exec to verify a late fix** — never used. Every patch continued this run_id (`MUX_FRESH=0`);
  `fresh_launches` stayed at 1.
- **Soft-completing sealed consumers** (`edl` / `mix` / `master_finalize`) — refused throughout; i47/i48/i49 were
  fixed at the producer/ownership level instead of waiving `mark_done`.
- **e2e / PMQ quality waivers** — not used. i53 went the other way and *tightened* the true-peak gate.
- **Loosening seat freeze generally** — rejected; i30/i37 are narrow carve-outs for omit-only deltas whose survivor
  span still covers the retired tape. Reorders stay freeze-owned.
- **Mapping predicates to End-*/family ledgers mid-run** — deferred per §0.1; clustering lives in the cross-run
  comparison, not in the campaign loop.

## Quality & cleanup

| Gate | Result |
|------|--------|
| Master | `master/master.wav` 255,661,710 B (44:23) |
| `tools/verify_master.py` | **OK** — −15.00 LUFS, **−0.96 dBTP** (pass ≤ −0.75) |
| `listen_delight_audit` | mode=authoritative, pass=`post_master`, overall **0.9503**, `failed_dimensions=[]` |
| PMQ | `publish_allowed: true`, status=pass |
| Cover + publish | 74 `stage_done`; `package_ready.ready=true`; all 7 packaged files present; `publish/master.wav` hash == `master/master.wav` |
| S3 | not uploaded by design — G-Publish operator consent (`publish_blocked_quality_advisories`) |
| North star | human-listen rubric pending operator audition |
| Daemon | stopped; nudge loop retired at ship |
| Prereqs | `./tools/check_prerequisites.sh` OK (fixed a pre-existing ruff F821 in `tests/test_opening_orientation.py`); `tools/audit_config_keys.py` OK |

**Known debt (pre-existing, reproduced with this campaign's edits stashed):**
`scripts/verify_artifact_contract.sh` fails on `sfx_prompt_refine` / `synthetic_framing_plan` (no contract outputs),
and full `pytest tests/` carries ~200 failures from earlier campaigns (old fixtures vs. new gap_report ownership
rows, missing artifact fixtures for `junction_snip_qa` / `sound_design_vo_finalize`, seed-prereq consent ordering).

**Open residuals from this run (logged, not patched):**

1. `sound_design_plan` has no ALLOW row for `master/narrative_plan.json`, `understanding/soundscape_policy.json`,
   `understanding/episode_structure.json` — 5 denials at 09:29, non-fatal this run.
2. `mastering/homunculus/ears/**` uncataloged — one `unknown_path` at 11:06.
3. `mastering/listen_delight_audit.json` denials from `mix` (×1) and `junction_snip_qa` (×3): the refusal is correct
   but is logged at `error` severity; those callers should be advisory the way i44 made the SDP bed trim.
4. Nugget-layup copy churn: `spoken_next_clip_restatement` ×7, `layup_coverage` ×3, `stamp_valueless_skips`, plus 20
   `seed order: complete nugget_layup_compose before running mix` refusals. Self-healed via recompose; costs time and tokens.

## Later review

Cross-run comparison against the previous campaign (`exec_11630`, see
[exec-11630-major-errors-status.md](../../docs/cross-cutting/exec-11630-major-errors-status.md)) established:

- 11630's dominant families are dead here — orientation `audible_count=0`, `vo_seated_coverage`,
  `scorecard_dimension_floors` / `omit_ledger_air_contract` all measured **0** across this run's full log.
- Recurred with new causes: `seed_order_prereq` (16 → 112), heal `budget_exhausted` (35 → 4,608, as a symptom of the
  junction deadlock), `selection_edl_order_drift`, `mix_seat` / `phase_a_edl` premature-complete residuals, and the
  VO-audio family — which came back in a *more dangerous* form (silent silence instead of a loud refusal).
- **Latent in 11630, first caught here:** i52 (that run's `package_ready.json` also promises `episode.json` /
  `description.txt`, neither of which exists on disk) and i54 (its `listen_delight_audit.json` is still
  `advisory: true, pass: pre_mix`, so its delight pass was unbacked too). 11630's own master measures −1.00 dBTP,
  so i53's overshoot did not manifest there even though both code flaws were present.
- Reporting gap worth fixing: `operator/forensics_errors.json` rolls at 2,000 entries, so both runs lost their
  first hours of ledger; only `gui_log.jsonl` holds the full record. §13 was also skipped at ship for 11630.

---

## Archive — `exec_4741_d19c15b58ab4_20260901T001444Z` (2026-09-01)

INPUT `mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3` → ship. ~18 interventions. Final package under
`publish/` (audio.mp3, cover.jpg, transcript.vtt, chapters). Master ~171 MiB / 1865 s.

| Predicate | Class | Files |
|-----------|-------|-------|
| Driver suicide on fresh DELETE | keep_driver | web ensure_run / driver launch path |
| G1 VO open seed-order | seed → producer | g1 / seed-order routing |
| Chapter overflow | clamp + commit | chapter merge/clamp |
| Hollow layup seed thrash | seed-complete | layup seed thrash fix |
| Stale transitions → layup wipe | route | stale transition router |
| Stale SDP seed-complete | SDP completeness | stale SDP detection |
| Synth hash thrash | backfill | synthesis_report refresh |
| Mint/suppress gap mismatch | bridge mint | gap mint vs skip |
| Clone-adj transition thrash | suppress | clone adjacency |
| Missing SDP WAVs → wrong resume | safe_mix_resume | `delivery_guardrails.py` |
| Hollow mmaudio marked done | incompleteness | `stage_completion.py`, `agenda.py` |
| Lazy MusicGen vs full palette | E3 referenced-only | `sdp_cross_validate.py` |
| Junction remaster archives mix | skip layup invalidate | `air_order_integrity.py` |
| PMQ `spoken_unsupported_entity:Mohan` | enrich at PMQ | `spoken_copy_guard.py`, `post_master_quality.py` |
| Sentence-initial `Every`/`Each` false entity | ENTITY_IGNORE | `spoken_copy_guard.py` |
| Advisories blocked local encode | docs/product mismatch | `post_master_quality.py`, `aspirational_quality.py`, `sync_assets.py` |

Guardrails: `test_safe_mix_resume_routes_missing_sdp_wavs_to_mmaudio`,
`test_mmaudio_incomplete_when_sdp_wavs_missing`, `test_missing_sdp_wavs_ignores_unreferenced_lazy_slots`,
`test_junction_source_skips_layup_invalidate`, `test_sentence_initial_determiners_are_not_unsupported_entities`;
S3 sync still gated by advisories until G-Publish Prepare (`g_publish_cleared`).

Dead ends: driver/homunculus diverting `master_finalize` → junction remaster (wipe assembly); forcing PMQ / e2e
quality waivers (forbidden — fixed grounding + advisory/local-package split instead); hash-only refresh without
aligning gap↔synthesis scripts.

Quality: `master/master.wav` present (~179 MB); `verify_master` OK — LUFS −16.03, TP −1.00;
`listen_delight_audit` `passed: true`, overall 0.9376, `blocking: false`; PMQ `publish_allowed: true`;
`episode_cover_generate` / `podcast_publish` done; daemon stopped; S3 left for operator G-Publish sync.
