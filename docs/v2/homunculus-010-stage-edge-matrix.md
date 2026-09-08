# Homunculus 0.1.0 — per-stage edge catalog (R2)

Every stage id in ANALYSIS (35) + DELIVERY (34).
Primary artifacts from `STAGE_ARTIFACT_DISK_PATHS` where registered; else stage module.

| Stage | Order | Primary artifact | Heal-only? | ADG inv len | Blast listed | Missing/hollow | Surgical rerun | Pin hint |
|-------|-------|------------------|------------|------------:|--------------|----------------|----------------|----------|
| `audio_preclean` | analysis | `(see stage module / incompleteness)` | no | 34 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `ingest` |
| `ingest` | analysis | `(see stage module / incompleteness)` | no | 33 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `transcribe` |
| `transcribe` | analysis | `(see stage module / incompleteness)` | no | 32 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `transcript_review_build` |
| `transcript_review_build` | analysis | `(see stage module / incompleteness)` | no | 31 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `audio_probe_build` |
| `audio_probe_build` | analysis | `(see stage module / incompleteness)` | no | 30 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `source_acoustic_profile` |
| `source_acoustic_profile` | analysis | `(see stage module / incompleteness)` | no | 29 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `interview_spine_build` |
| `interview_spine_build` | analysis | `(see stage module / incompleteness)` | no | 28 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `speaker_roles` |
| `speaker_roles` | analysis | `understanding/speakers.json` | no | 27 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `source_topology_build` |
| `source_topology_build` | analysis | `(see stage module / incompleteness)` | no | 60 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `content_context` |
| `content_context` | analysis | `understanding/content_brief.json` | no | 59 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `talking_points_compose` |
| `talking_points_compose` | analysis | `understanding/talking_points.json` | no | 24 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `ideal_cuts_propose` |
| `ideal_cuts_propose` | analysis | `understanding/ideal_cuts.json` | no | 23 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `ideal_cuts_materialize` |
| `ideal_cuts_materialize` | analysis | `understanding/ideal_cuts_materialized.json` | no | 22 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `boundary_detection` |
| `boundary_detection` | analysis | `segments/boundaries.json` | no | 22 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `segment_classification` |
| `segment_classification` | analysis | `segments/manifest.json` | no | 21 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `content_brief_reanchor` |
| `content_brief_reanchor` | analysis | `understanding/content_brief.json` | no | 20 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `framing_posture_decide` |
| `framing_posture_decide` | analysis | `understanding/framing_posture_decision.json` | no | 18 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `boundary_topic_resplit` |
| `boundary_topic_resplit` | analysis | `segments/boundaries.json` | no | 22 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `vernacular_segment_sanitize` |
| `vernacular_segment_sanitize` | analysis | `(see stage module / incompleteness)` | no | 16 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `low_conf_island_scan` |
| `low_conf_island_scan` | analysis | `analysis/low_conf_islands.json` | no | 45 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `connector_fuse_pass` |
| `connector_fuse_pass` | analysis | `analysis/connector_fuse_audit.json` | no | 48 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `sonic_context_build` |
| `sonic_context_build` | analysis | `(see stage module / incompleteness)` | no | 13 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `sound_design_palettes` |
| `sound_design_palettes` | analysis | `understanding/sound_design_plan.json` | no | 13 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `mastering_research_routing` |
| `mastering_research_routing` | analysis | `mastering/research/routing.json` | no | 11 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `mastering_research_waves` |
| `mastering_research_waves` | analysis | `mastering/research/waves.json` | no | 10 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `mastering_research_rollup` |
| `mastering_research_rollup` | analysis | `mastering/research/rollup.json` | no | 9 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `mastering_shape_agenda` |
| `mastering_shape_agenda` | analysis | `(see stage module / incompleteness)` | no | 8 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `mastering_shape_candidates` |
| `mastering_shape_candidates` | analysis | `(see stage module / incompleteness)` | no | 7 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `mastering_plan_synthesize` |
| `mastering_plan_synthesize` | analysis | `(see stage module / incompleteness)` | no | 6 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `missing_framing` |
| `missing_framing` | analysis | `understanding/gap_evaluations.json` | no | 5 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `mastering_plan_confirm` |
| `mastering_plan_confirm` | analysis | `(see stage module / incompleteness)` | no | 4 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `gap_framing_compose` |
| `gap_framing_compose` | analysis | `understanding/gap_report.json` | yes | 3 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `delivery_brief_build` |
| `delivery_brief_build` | analysis | `(see stage module / incompleteness)` | no | 2 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `soundscape_policy_build` |
| `soundscape_policy_build` | analysis | `(see stage module / incompleteness)` | no | 1 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `episode_structure_compose` |
| `episode_structure_compose` | analysis | `(see stage module / incompleteness)` | no | 0 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `episode_structure_compose` |
| `topic_coverage_audit` | delivery | `master/coverage_audit.json` | no | 33 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `narrative_arc_plan` |
| `narrative_arc_plan` | delivery | `master/narrative_plan.json` | no | 32 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `chapter_close_hitch` |
| `chapter_close_hitch` | delivery | `mastering/chapter_close_hitch.json` | no | 31 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `connector_fuse_pass_pre_ranking` |
| `connector_fuse_pass_pre_ranking` | delivery | `analysis/connector_fuse_rounds.json` | no | 30 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `full_master_ranking` |
| `full_master_ranking` | delivery | `master/selection.json` | no | 29 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `air_script_compose` |
| `air_script_compose` | delivery | `mastering/mastering_plan.json` | no | 28 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `nugget_corpus_mine` |
| `nugget_corpus_mine` | delivery | `understanding/nugget_corpus.json` | no | 27 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `information_package_plan` |
| `information_package_plan` | delivery | `(see stage module / incompleteness)` | no | 26 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `nugget_layup_compose` |
| `nugget_layup_compose` | delivery | `understanding/nugget_layup_plan.json` | yes | 25 | listen_delight_audit,edl_narrative_audit,vo_synthesize,edl | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `refinement_agenda` |
| `refinement_agenda` | delivery | `(see stage module / incompleteness)` | no | 24 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `gap_framing_recompose` |
| `gap_framing_recompose` | delivery | `(see stage module / incompleteness)` | yes | 23 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `selection_framing_apply` |
| `selection_framing_apply` | delivery | `(see stage module / incompleteness)` | no | 22 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `air_script_seams` |
| `air_script_seams` | delivery | `mastering/mastering_plan.json` | no | 21 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `transitions` |
| `transitions` | delivery | `master/transitions.json` | no | 20 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `sound_design_plan` |
| `sound_design_plan` | delivery | `understanding/sound_design_plan.json` | no | 19 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `sound_design_vo_finalize` |
| `sound_design_vo_finalize` | delivery | `(see stage module / incompleteness)` | no | 18 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `vo_line_adjudicate` |
| `vo_line_adjudicate` | delivery | `understanding/vo_line_adjudication.json` | yes | 17 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `vo_synthesize` |
| `vo_synthesize` | delivery | `mastering/vo_synthesize.json` | no | 16 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `edl_narrative_audit` |
| `edl_narrative_audit` | delivery | `master/edl_narrative_audit.json` | no | 17 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `edl` |
| `edl` | delivery | `master/edl.json` | no | 14 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `assembly_preview` |
| `assembly_preview` | delivery | `master/assembly_preview.wav` | no | 13 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `listen_delight_audit` |
| `listen_delight_audit` | delivery | `mastering/listen_delight_audit.json` | no | 12 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `music_palette_compose` |
| `music_palette_compose` | delivery | `sound_design/music_palette_compose.json` | no | 11 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `sfx_prompt_craft` |
| `sfx_prompt_craft` | delivery | `sound_design/sfx_prompts.json` | no | 10 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `mmaudio_sfx` |
| `mmaudio_sfx` | delivery | `sound_design/mmaudio_qa.json` | no | 9 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `mix` |
| `mix` | delivery | `master/assembly.wav` | no | 8 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `junction_snip_qa` |
| `junction_snip_qa` | delivery | `master/seam_autopsy.json` | no | 7 | master/transitions.json,mix,junction_snip_qa,master_finalize | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `master_finalize` |
| `master_finalize` | delivery | `(see stage module / incompleteness)` | no | 6 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `master_transcript_build` |
| `master_transcript_build` | delivery | `master/transcript.json` | no | 5 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `episode_meta_build` |
| `episode_meta_build` | delivery | `(see stage module / incompleteness)` | no | 4 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `episode_cover_prompt_craft` |
| `episode_cover_prompt_craft` | delivery | `(see stage module / incompleteness)` | no | 3 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `podcast_encode_mp3` |
| `podcast_encode_mp3` | delivery | `(see stage module / incompleteness)` | no | 2 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `episode_cover_generate` |
| `episode_cover_generate` | delivery | `(see stage module / incompleteness)` | no | 1 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `podcast_publish` |
| `podcast_publish` | delivery | `(see stage module / incompleteness)` | no | 0 | — | yes — seed_stage_complete requires artifact_usable | yes via rerun_stage (no downstream clear) | `podcast_publish` |

## Stage-internal branches (common predicates)

| Family | Internal branches to watch |
|--------|---------------------------|
| ingest/transcribe/preclean | missing wav; G0 lock after close |
| framing/gap | G-Framing Yes/No; eligibility skip |
| layup/selection | omit CTA; fragment omit; order change → seating |
| VO triad | adjudicate before synth; pair freeze; hash freshness |
| EDL/preview/mix | source_path; seating generation; script hash sync |
| music triad | assembly required; generate-missing; seal |
| delight/junction/finalize | seal≠waive; remaster budget; PMQ Tier-0 |
| ship chain | package_ready; advisories; no auto-S3 |
