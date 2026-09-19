# Artifact ownership — ALLOW / DENY

matrix_version: `5c1cb0bdae461afd`

## Primary paths (live stages)

| stage | path |
|---|---|
| `air_contract_sanitize` | `mastering/mastering_plan.json` |
| `air_script_compose` | `mastering/mastering_plan.json` |
| `air_script_seams` | `mastering/mastering_plan.json` |
| `assembly_preview` | `master/assembly_preview.wav` |
| `audio_preclean` | `preclean/isolated.wav` |
| `audio_probe_build` | `analysis/run_golden_facts.json` |
| `boundary_detection` | `segments/boundaries.json` |
| `boundary_topic_resplit` | `segments/boundaries.json` |
| `chapter_close_hitch` | `mastering/chapter_close_hitch.json` |
| `connector_fuse_pass` | `analysis/connector_fuse_audit.json` |
| `connector_fuse_pass_pre_ranking` | `analysis/connector_fuse_rounds.json` |
| `content_brief_reanchor` | `understanding/content_brief.json` |
| `content_context` | `understanding/content_brief.json` |
| `delivery_brief_build` | `understanding/delivery_brief.json` |
| `edl` | `master/edl.json` |
| `edl_narrative_audit` | `master/edl_narrative_audit.json` |
| `episode_cover_generate` | `publish/cover.jpg` |
| `episode_cover_prompt_craft` | `publish/cover_prompt.json` |
| `episode_meta_build` | `publish/episode_meta.json` |
| `episode_structure_compose` | `understanding/episode_structure.json` |
| `framing_posture_decide` | `understanding/framing_posture_decision.json` |
| `full_master_ranking` | `master/selection.json` |
| `gap_framing_compose` | `understanding/gap_report.json` |
| `gap_framing_recompose` | `understanding/gap_framing_recompose.json` |
| `gap_report_sanitize` | `understanding/gap_report.json` |
| `ideal_cuts_materialize` | `understanding/ideal_cuts_materialized.json` |
| `ideal_cuts_propose` | `understanding/ideal_cuts.json` |
| `information_package_plan` | `mastering/shape/information_packages_audit.json` |
| `ingest` | `ingest/normalized.wav` |
| `interview_spine_build` | `understanding/interview_spine.json` |
| `junction_snip_qa` | `master/junction_snip_qa.json` |
| `listen_delight_audit` | `mastering/listen_delight_audit.json` |
| `low_conf_island_scan` | `analysis/low_conf_islands.json` |
| `master_finalize` | `master/master.wav` |
| `master_transcript_build` | `master/transcript.json` |
| `mastering_plan_confirm` | `mastering/mastering_plan.json` |
| `mastering_plan_synthesize` | `mastering/mastering_plan.json` |
| `mastering_research_rollup` | `mastering/research/rollup.json` |
| `mastering_research_routing` | `mastering/research/routing.json` |
| `mastering_research_waves` | `mastering/research/waves.json` |
| `mastering_shape_agenda` | `mastering/shape/agenda.json` |
| `mastering_shape_candidates` | `mastering/shape/candidates.json` |
| `missing_framing` | `understanding/gap_evaluations.json` |
| `mix` | `master/assembly.wav` |
| `mmaudio_sfx` | `sound_design/mmaudio_qa.json` |
| `music_palette_compose` | `sound_design/music_palette_compose.json` |
| `narrative_arc_plan` | `master/narrative_plan.json` |
| `nugget_corpus_mine` | `understanding/nugget_corpus.json` |
| `nugget_layup_compose` | `understanding/nugget_layup_plan.json` |
| `podcast_encode_mp3` | `publish/audio.mp3` |
| `podcast_publish` | `publish/package_ready.json` |
| `refinement_agenda` | `understanding/refinement_agenda.json` |
| `segment_classification` | `segments/manifest.json` |
| `selection_framing_apply` | `understanding/selection_framing_apply.json` |
| `selection_order_sanitize` | `master/selection.json` |
| `sfx_prompt_craft` | `sound_design/sfx_prompts.json` |
| `sonic_context_build` | `understanding/sonic_context.json` |
| `sound_design_palettes` | `understanding/sound_design_plan.json` |
| `sound_design_plan` | `understanding/sound_design_plan.json` |
| `sound_design_vo_finalize` | `mastering/sound_design_vo_finalize.json` |
| `soundscape_policy_build` | `understanding/soundscape_policy.json` |
| `source_acoustic_profile` | `understanding/source_acoustic_profile.json` |
| `source_topology_build` | `understanding/source_topology.json` |
| `speaker_roles` | `understanding/speakers.json` |
| `talking_points_compose` | `understanding/talking_points.json` |
| `topic_coverage_audit` | `master/coverage_audit.json` |
| `transcribe` | `transcript/full.json` |
| `transcript_review_build` | `transcript/review_queue.json` |
| `transitions` | `master/transitions.json` |
| `vernacular_segment_sanitize` | `vernacular/resplit_report.json` |
| `vo_line_adjudicate` | `understanding/vo_line_adjudication.json` |
| `vo_synthesize` | `mastering/vo_synthesize.json` |

## DENY (high-risk)

| path | stage/role | epoch | reason |
|---|---|---|---|
| `vo_pickup/*.wav` | `edl` | `*` | edl_must_not_write_vo_pickup |
| `vo_pickup/*.wav` | `mix` | `*` | mix_must_not_write_vo_pickup |
| `vo_pickup/*.wav` | `master_finalize` | `*` | finalize_must_not_write_vo_pickup |
| `vo_pickup/*.wav` | `missing_framing` | `*` | missing_framing_must_not_write_vo_pickup |
| `understanding/gap_report.json` | `edl` | `*` | edl_must_not_rewrite_gap_copy |
| `understanding/gap_report.json` | `edl` | `*` | edl_must_not_stamp_voice_speaker |
| `understanding/gap_report.json` | `ensure_hosted_framing_vo_seats` | `hard_freeze` | protect_hosted_vo_floor_reseat |
| `understanding/gap_report.json` | `catastrophe_hosted_vo_floor` | `hard_freeze` | catastrophe_hosted_vo_floor |
| `understanding/gap_report.json` | `*` | `*` | cta_never_touch_as_floor_seat |
| `vo_pickup/*.wav` | `edl` | `*` | non_owner_vo_pending_flush |
| `vo_pickup/*` | `driver` | `*` | driver_must_not_flush_foreign_vo |
| `understanding/gap_report.json` | `edl` | `*` | non_owner_gap_pending_flush |
| `understanding/gap_report.json` | `mix` | `*` | non_owner_gap_pending_flush |
| `understanding/gap_report.json` | `junction_snip_qa` | `*` | non_owner_gap_pending_flush |
| `master/transitions.json` | `edl` | `*` | non_owner_transitions_pending_flush |
| `master/selection.json` | `edl` | `*` | non_owner_selection_pending_flush |
| `mastering/mastering_plan.json` | `edl` | `*` | non_owner_plan_pending_flush |
| `understanding/reorder_bridges.json` | `edl` | `*` | non_owner_bridges_pending_flush |
| `master/edl.json` | `gui` | `*` | gui_must_not_rewrite_edl |
| `mastering/vo_synthesize.json` | `vo_line_adjudicate` | `*` | adjudicate_must_not_unmark_live_vo |
| `vo_pickup/*.wav` | `vo_line_adjudicate` | `*` | adjudicate_must_not_unmark_vo_wavs |
| `master/transitions.json` | `edl` | `*` | edl_must_not_mint_transitions |
| `master/transitions.json` | `edl_narrative_audit` | `*` | narrative_must_not_mint_transitions |
| `master/bridge_completeness.json` | `driver` | `*` | soft_complete_requires_e2e_waiver |
| `../**` | `*` | `*` | cross_exec_isolation |

## Notes

- Owner re-execute is ALLOW; consumer re-execute never becomes owner.
- Nested VO staging under EDL is ALLOW; flushing `vo_pickup` from non-owner pending is DENY.
- Empty heal pin must not execute (no delivery rewind / no music_palette_compose coalesce).
