# Stage Clinic queue — brain 0.2.0 / analysis walk

Order = ANALYSIS_ORDER then DELIVERY_ORDER. Mark `[x]` when L1 map complete or waived.

## Analysis

- [x] `01` `audio_preclean` — gate:preclean
- [x] `02` `ingest`
- [x] `03` `transcribe`
- [x] `04` `transcript_review_build` — gate:G0
- [x] `05` `audio_probe_build`
- [x] `06` `source_acoustic_profile`
- [x] `07` `interview_spine_build`
- [x] `08` `speaker_roles`
- [x] `09` `source_topology_build`
- [x] `10` `content_context`
- [x] `11` `talking_points_compose`
- [x] `12` `ideal_cuts_propose`
- [x] `13` `ideal_cuts_materialize`
- [x] `14` `boundary_detection`
- [x] `15` `segment_classification`
- [x] `16` `content_brief_reanchor`
- [x] `17` `framing_posture_decide` — gate:G-Framing
- [x] `18` `boundary_topic_resplit`
- [x] `19` `vernacular_segment_sanitize`
- [x] `20` `low_conf_island_scan`
- [x] `21` `connector_fuse_pass`
- [x] `22` `sonic_context_build`
- [x] `23` `sound_design_palettes`
- [x] `24` `mastering_research_routing`
- [x] `25` `mastering_research_waves`
- [x] `26` `mastering_research_rollup`
- [x] `27` `mastering_shape_agenda`
- [x] `28` `mastering_shape_candidates`
- [x] `29` `mastering_plan_synthesize`
- [x] `30` `missing_framing` — gate:G-Framing
- [x] `31` `mastering_plan_confirm`
- [x] `32` `gap_framing_compose` — gate:G1
- [x] `33` `delivery_brief_build`
- [x] `34` `soundscape_policy_build`
- [x] `35` `episode_structure_compose`

## Delivery

- [x] `36` `topic_coverage_audit`
- [x] `37` `narrative_arc_plan`
- [x] `38` `chapter_close_hitch`
- [x] `39` `connector_fuse_pass_pre_ranking`
- [x] `40` `full_master_ranking`
- [x] `41` `selection_order_sanitize`
- [x] `42` `air_script_compose`
- [x] `43` `nugget_corpus_mine`
- [x] `44` `information_package_plan`
- [x] `45` `nugget_layup_compose`
- [x] `46` `gap_report_sanitize`
- [x] `47` `refinement_agenda`
- [x] `48` `gap_framing_recompose`
- [x] `49` `selection_framing_apply`
- [x] `50` `air_script_seams`
- [x] `51` `air_contract_sanitize`
- [x] `52` `transitions`
- [x] `53` `sound_design_plan`
- [x] `54` `vo_line_adjudicate`
- [x] `55` `vo_synthesize` — gate:G1
- [x] `56` `sound_design_vo_finalize`
- [x] `57` `edl_narrative_audit`
- [x] `58` `edl`
- [x] `59` `assembly_preview`
- [x] `60` `listen_delight_audit` — gate:listen_delight
- [x] `61` `music_palette_compose`
- [x] `62` `sfx_prompt_craft`
- [x] `63` `mmaudio_sfx`
- [x] `64` `mix`
- [x] `65` `junction_snip_qa`
- [x] `66` `master_finalize`
- [x] `67` `master_transcript_build` — gate:G-Publish
- [x] `68` `episode_meta_build`
- [x] `69` `episode_cover_prompt_craft`
- [x] `70` `podcast_encode_mp3`
- [x] `71` `episode_cover_generate`
- [x] `72` `podcast_publish` — gate:G-Publish
