# Stage Clinic ledger

| stage | phase | wave | L1_map | L2_target | L3_patch | simplified_to_rules | open_questions | blocked_on |
|-------|-------|------|--------|-----------|----------|---------------------|----------------|------------|
| `audio_preclean` | analysis | remediation | complete | draft | done | yes |  | PRECLEAN-B3 docs=Full-auto may auto (6A) |
| `ingest` | analysis | remediation | complete | draft | done | yes |  | ING-B3 ingest-only peaks (1B) |
| `transcribe` | analysis | remediation | complete | draft | done | yes |  | TR-B4 KEEP empty-words done (4B) |
| `transcript_review_build` | analysis | remediation | complete | draft | done | yes | G0 body never auto-closes |  |
| `audio_probe_build` | analysis | remediation | complete | draft | done | yes |  | APB-B2 KEEP fail_open empties (4B) |
| `source_acoustic_profile` | analysis | remediation | complete | draft | done | yes |  | SAP-B5 not thrash hotspot; KEEP FORCE_DONE (2B) |
| `interview_spine_build` | analysis | remediation | complete | draft | done | yes |  | ISB-B1 KEEP stub-in-seed (4B) |
| `speaker_roles` | analysis | remediation | complete | draft | done | yes |  |  |
| `source_topology_build` | analysis | remediation | complete | draft | done | yes |  | STB-B6 KEEP framing pickup (3A) |
| `content_context` | analysis | remediation | complete | draft | done | yes |  | CC-B1 topology harden (Q1A) |
| `talking_points_compose` | analysis | remediation | complete | draft | done | yes |  |  |
| `ideal_cuts_propose` | analysis | remediation | complete | draft | done | yes |  | ICP-B3 KEEP enable=false stub (4B) |
| `ideal_cuts_materialize` | analysis | remediation | complete | draft | done | yes |  | B2 KEEP soft-stale (4A) |
| `boundary_detection` | analysis | remediation | complete | draft | done | yes |  | BD-B5 KEEP skip-when-bound (5A) |
| `segment_classification` | analysis | remediation | complete | draft | done | yes |  | SC-B5 KEEP skip-when-bound (5A); SC-B6 thrash only (5A) |
| `content_brief_reanchor` | analysis | remediation | complete | draft | done | yes |  | CBR-B4 thrash only (5A) |
| `framing_posture_decide` | analysis | remediation | complete | draft | done | yes |  |  |
| `boundary_topic_resplit` | analysis | remediation | complete | draft | done | yes |  | B2 KEEP empty skip (6A) |
| `vernacular_segment_sanitize` | analysis | remediation | complete | draft | done | yes |  | VSS-B5 KEEP fail_open (7A) |
| `low_conf_island_scan` | analysis | remediation | complete | draft | done | yes | disabled skip-done confirm |  |
| `connector_fuse_pass` | analysis | remediation | complete | draft | done | yes |  | CFP-B5/B6 KEEP (8A) |
| `sonic_context_build` | analysis | remediation | complete | draft | done | yes |  |  |
| `sound_design_palettes` | analysis | remediation | complete | draft | done | yes |  |  |
| `mastering_research_routing` | analysis | remediation | complete | draft | done | yes |  | Q2A CSP-05; CSP-02 hard:[] (no empty-hard SDP) |
| `mastering_research_waves` | analysis | remediation | complete | draft | done | yes |  | MRW-B1 hard:[] routing demote (Q1A) |
| `mastering_research_rollup` | analysis | remediation | complete | draft | done | yes |  | MRRoll-B2 RESEARCH_CONSUMER (1A); CSP-02 hard:[] |
| `mastering_shape_agenda` | analysis | remediation | complete | draft | done | yes |  | Q2A CSP-05: rubric LLM fail → incomplete |
| `mastering_shape_candidates` | analysis | remediation | complete | draft | done | yes |  | MSC-B2 LLM-only when shape.llm (2B) |
| `mastering_plan_synthesize` | analysis | remediation | complete | draft | done | yes |  | MPS-B2 KEEP consumers_bind=false (3A; re-ask A 2026-09-18) |
| `missing_framing` | analysis | remediation | complete | done | done | yes |  | B1 Full-auto arms auto path; B3 KEEP auto_skip=false |
| `mastering_plan_confirm` | analysis | remediation | complete | draft | done | yes |  | MPC-B2 drop upstream missing_framing (4A) |
| `gap_framing_compose` | analysis | remediation | complete | draft | done | yes |  | Q2A CSP-05: framing Yes + zero lines → incomplete |
| `delivery_brief_build` | analysis | remediation | complete | draft | done | yes |  |  |
| `soundscape_policy_build` | analysis | remediation | complete | draft | done | yes |  | SSP-B1 invent-block incomplete (5A) |
| `episode_structure_compose` | analysis | remediation | complete | draft | done | yes |  |  |
| `topic_coverage_audit` | delivery | remediation | complete | draft | done | yes |  | Q2A CSP-05: soft-fail LLM → incomplete/refuse |
| `narrative_arc_plan` | delivery | remediation | complete | draft | done | yes |  | NAP-B2 dual OK document (6C) |
| `chapter_close_hitch` | delivery | remediation | complete | draft | done | yes |  | CCH-B2 dual OK document (6C) |
| `connector_fuse_pass_pre_ranking` | delivery | remediation | complete | draft | done | yes |  |  |
| `full_master_ranking` | delivery | remediation | complete | done | done | yes |  | FMR-B2 Full-auto QC soft advisory |
| `selection_order_sanitize` | delivery | remediation | complete | draft | done | yes |  |  |
| `air_script_compose` | delivery | remediation | complete | applied | done | yes |  | ASC-B3 leave selection alone (1B) |
| `nugget_corpus_mine` | delivery | remediation | complete | draft | done | yes |  | NCM-B2 empty→incomplete (CONTINUE) |
| `information_package_plan` | delivery | remediation | complete | draft | done | yes |  | IPP-B2 empty corpus incomplete (CONTINUE) |
| `nugget_layup_compose` | delivery | remediation | complete | draft | done | yes |  | NLC-B2 compose hard nugget-air floor (CONTINUE) |
| `gap_report_sanitize` | delivery | remediation | complete | draft | done | yes |  | GRS-B2 empty stub incomplete framing Yes (CONTINUE) |
| `refinement_agenda` | delivery | remediation | complete | done | done | yes |  | RA-B2 block dirty gap |
| `gap_framing_recompose` | delivery | remediation | complete | done | done | yes |  | GFR-B3 legacy activate retired |
| `selection_framing_apply` | delivery | remediation | complete | draft | done | yes |  |  |
| `air_script_seams` | delivery | remediation | complete | applied | done | yes |  | ASS-B3 KEEP soft-freeze (7A) |
| `air_contract_sanitize` | delivery | remediation | complete | draft | done | yes |  | ACS-B1 KEEP reentry refuse (1A) |
| `transitions` | delivery | remediation | complete | applied | done | yes |  | B1 KEEP empty OK (min_rows 0) (CONTINUE) |
| `sound_design_plan` | delivery | remediation | complete | draft | done | yes |  | SDP-B3 KEEP enabled=true (7A); SDP-B1 KEEP fingerprint (5A) |
| `vo_line_adjudicate` | delivery | remediation | complete | applied | done | yes |  | B1 KEEP HV3; B2 fail_open=true (CONTINUE) |
| `vo_synthesize` | delivery | remediation | complete | applied | done | yes |  | B1 KEEP honesty; B2 prior; B3 Full-auto record→synth (CONTINUE) |
| `sound_design_vo_finalize` | delivery | remediation | complete | draft | done | yes |  | SDVF-B3 trim VO invalidates (8B) |
| `edl_narrative_audit` | delivery | remediation | complete | draft | done | yes |  | HE-1 KEEP (4A); ENA-B3 trim (8B) |
| `edl` | delivery | remediation | complete | draft | done | yes |  | EDL-B1 KEEP F4 (2A) |
| `assembly_preview` | delivery | remediation | complete | draft | done | yes |  | AP-B1 KEEP heard_wav (3A) |
| `listen_delight_audit` | delivery | remediation | complete | applied | done | yes |  | B1/B2 KEEP fail_early=false + finalize ship re-run (CONTINUE notes); B3 remutate N=3 |
| `music_palette_compose` | delivery | remediation | complete | draft | done | yes |  | MPC-B2 producer=plan + body require SDP (Q1A) |
| `sfx_prompt_craft` | delivery | remediation | complete | done | done | yes | — | B2 Full-auto auto-approve incl. soft warnings (operator binding) |
| `mmaudio_sfx` | delivery | remediation | complete | applied | done | yes |  | B2 KEEP omit-all fail delight/block mix — confirmed landed (CONTINUE notes) |
| `mix` | delivery | remediation | complete | draft | done | yes | — | B3 Full-auto g_listen auto-clear (shared); B4 VO soft/SFX hard kept |
| `junction_snip_qa` | delivery | remediation | complete | applied | done | yes |  | B3 classified refuse / no needs_operator on osc/budget (CONTINUE rebind) |
| `master_finalize` | delivery | remediation | complete | applied | done | yes |  | B2 Full-auto g_listen auto-clear; B3 Advisory=ship OK (CONTINUE) |
| `master_transcript_build` | delivery | remediation | complete | draft | done | yes |  | MTB-B2 dual producer documented (9A) |
| `episode_meta_build` | delivery | remediation | complete | applied | done | yes |  | EMB-B1 refuse Untitled (6B) |
| `episode_cover_prompt_craft` | delivery | remediation | complete | draft | done | yes | empty prompt incomplete; soft meta | |
| `podcast_encode_mp3` | delivery | remediation | complete | draft | done | yes | dedicated helper vs generic binary | |
| `episode_cover_generate` | delivery | remediation | complete | draft | done | yes |  |  |
| `podcast_publish` | delivery | remediation | complete | applied | done | yes |  | B2 DONE-local/refuse-remote; B4 KEEP DEAD require_g_publish_clear (CONTINUE) |
