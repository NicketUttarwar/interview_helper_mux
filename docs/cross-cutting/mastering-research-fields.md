# Mastering research fields

Exhaustive catalog for the Mastering Process research lane. Canon: [mastering-process.md](./mastering-process.md).

Each field: mint system prompt → research volley → acceptance → optional clarify → `mastering/research/{field_id}.json`. Skip-aware when operator skipped the source flow.

**Acceptance seeds (all fields):** cite evidence refs; no invented assets; `confidence` 0–1; list assumptions; if thin → `status=skipped_or_thin`.

---

## Wave 1 — Source hygiene and ingest readiness

| Field id | Knowledge | Artifacts / stages | Operator flows | Skip if |
|----------|-----------|--------------------|----------------|---------|
| `preclean_lineage` | Noise reduction choices | `preclean/*`, `operator/preclean_decisions.json`; `audio_preclean` | Preclean offer | Preclean dismissed |
| `ingest_normalization` | Sample rate, checksum, loudness stabilize | `ingest/normalized.wav`, `checksums.json`, `loudness.json`; `ingest` | Start / new run | — |
| `source_acoustic_profile` | Pacing, energy, SAP mix | `source_acoustic_profile.json`, overrides; `source_acoustic_profile` | Acoustic / SAP panels | — |
| `source_readiness_band` | Green/yellow/red readiness | `source_readiness.json` | First-try / reuse | — |

## Wave 2 — Transcript fidelity and speaker identity

| Field id | Knowledge | Artifacts / stages | Operator flows | Skip if |
|----------|-----------|--------------------|----------------|---------|
| `g0_transcript_fidelity` | STT quality, corrections | `transcript/full.json`, review queue, corrections; `transcribe`, `transcript_review_build` | **G0** | — (G0 mandatory) |
| `speaker_roles` | Roles, narrative function | `understanding/speakers.json`; `speaker_roles` | Profile / role edits | — |
| `source_topology` | Topology class | `source_topology.json`, `flow_adaptation.json`; `source_topology_build` | Pickup speaker confirm | — |
| `speaker_volleys` | Conversation atoms | `episode_structure.speaker_volleys[]`; `episode_structure_compose` | Conversation Studio / volley timeline | Thin if no volleys detected |
| `pickup_speaker_voice` | Least-spoken VO + refs | voice_reference, speaker_samples | G-Speaker / G-VoiceRef / VO | — |
| `interview_spine_windows` | Time-aligned index | `interview_spine.json`, CLAP embeddings; `interview_spine_build` | Spine / debug | Spine disabled |

## Wave 3 — Narrative meaning and coherence

| Field id | Knowledge | Artifacts / stages | Operator flows | Skip if |
|----------|-----------|--------------------|----------------|---------|
| `thesis_claims` | Thesis, claims, topics | `content_brief.json`, reanchor, analysis_state; `content_context`, `content_brief_reanchor` | Stage detail themes | — |
| `value_features` | Deterministic spikes | `value_features.json` | Value-analysis | Value analysis off |
| `coherence_risks` | Drift / contradiction | `coherence_report.json`, investigation_queue | Stage detail investigations | Coherence off / short run |
| `topic_coverage` | Topic survival | `coverage_audit.json` or brief+segments; `topic_coverage_audit` | Coverage audit | Pre-delivery: proxy only |
| `narrative_arc_candidates` | Arc as *candidate only* | `narrative_plan.json`; `narrative_arc_plan` | Arc panel | Pre-arc: thin |
| `transition_bridge_inventory` | Spoken bridges | `transitions.json`, gap VO notes; `transitions` | Transitions / gap studio | Pre-transitions: thin |

## Wave 4 — Segmentation, budgets, and edit intent

| Field id | Knowledge | Artifacts / stages | Operator flows | Skip if |
|----------|-----------|--------------------|----------------|---------|
| `boundaries_segments` | Segment inventory | `segments/boundaries.json`, `manifest.json`; boundary + classification stages | Segmentation review | — |
| `delivery_brief_budgets` | Soft budgets | `delivery_brief.json`; `delivery_brief_build` | Delivery brief | — |
| `episode_structure_pack` | Pack slot *candidates* | `episode_structure.json`, packs YAML; `episode_structure_compose` | Structure compose | — |
| `nle_operator_edits` | Operator trims | `nle_edits.json` | **Timeline / NLE** | No NLE edits |
| `master_ranking_exclusions` | Prior ranking | `selection.json`; `full_master_ranking` | Ranking | First pass: thin |
| `edl_speech_timeline` | Prior EDL / preview | `edl.json`, `assembly_preview.wav`; `edl`, `assembly_preview` | Assembly preview | Pre-EDL: thin |

## Wave 5 — Gaps, framing, and VO assets

| Field id | Knowledge | Artifacts / stages | Operator flows | Skip if |
|----------|-----------|--------------------|----------------|---------|
| `gap_framing_plan` | Framing plan / lines | gap_evaluations, gap_framing_plan, gap_report; `missing_framing`, `gap_framing_compose` | G-Framing / Conversation Studio | Gaps skipped empty |
| `gap_vo_synthesis` | VO files + metadata | `vo_pickup/*`, synthesis_report; G1 / Chatterbox / S2S | **G1** record/skip/synth | G1 skipped |
| `framing_coverage_guard` | Impact survival | framing_coverage_guard outputs | Gap framing panels | Thin if no framing excludes |

## Wave 6 — Soundscape, SFX, and mix policy

| Field id | Knowledge | Artifacts / stages | Operator flows | Skip if |
|----------|-----------|--------------------|----------------|---------|
| `sonic_context_cues` | Scenario / cues | `sonic_context.json`; `sonic_context_build` | SonicContext panels | — |
| `sound_design_palettes` | Theme palettes | palettes artifact; `sound_design_palettes` | Palettes stage | — |
| `soundscape_policy_slots` | Cue-slot policy | `soundscape_policy.json`, soundscape_report; `soundscape_policy_build` | Soundscape | — |
| `sdp_plan_and_prompts` | SDP + prompts | `sound_design_plan.json`, sfx_prompts; `sound_design_plan`, `sfx_prompt_craft` | SDP / prompt approval | Pre-SDP: thin |
| `mmaudio_assets_qa` | Generated assets / QA | assets, mmaudio_qa, sfx_listen_results; `mmaudio_sfx` | MMAudio / post-listen | Pre-SFX: thin |
| `house_chain_levels` | Mix / duck / LUFS | mix config, SAP-adaptive | Mix / sound-and-mix docs | — |
| `production_style_profile` | Profile as *hint only* | production_style, production_profiles | Profile gate | — |

## Wave 7 — Operator intent and journey state

| Field id | Knowledge | Artifacts / stages | Operator flows | Skip if |
|----------|-----------|--------------------|----------------|---------|
| `journey_gates` | Gate completions | journey_state | G0 / G1 / G1.5 / preclean / framing | — |
| `story_board_steering` | Theme / investigation edits | legacy `story-board` API (no GUI) | — | Removed surface: always thin |
| `conversation_studio` | Gap / volley steering | ConversationStudio / gap CRUD | **Conversation Studio** | No studio use: thin |
| `stage_reuse_and_hash` | Reuse / source hash | run_meta, stage_reuse_decisions | PreviousSessionReuse / Start | Fresh run: thin |
| `llm_volley_audit` | Prior LLM quality | `llm_calls/**`, registry | Debug / LlmVolleyReview | — |

## Wave 8 — QC, completeness, and runtime reality

| Field id | Knowledge | Artifacts / stages | Operator flows | Skip if |
|----------|-----------|--------------------|----------------|---------|
| `deterministic_lint` | Per-stage lint | lint outputs | QC cards | — |
| `edl_narrative_qc` | Parity / volley integrity | edl_narrative_qc | EDL QC | Pre-EDL: thin |
| `artifact_completeness` | Missing blockers | artifact_completeness, progression_readiness | Pipeline readiness | — |
| `mix_completeness` | EDL/VO/SFX ready | completeness gate, sdp_cross_validate | Pre-mix | Pre-mix: thin |
| `master_verify` | Prior verify | verify_master, intelligibility_qc | Ship | First master: thin |
| `local_audio_runtimes` | What can run | DeepFilter, MMAudio, local_speech, Chatterbox, CLAP | Bootstrap / verify_local_models | — |
| `llm_routing_tiers` | Model tiers | models.tiers, local_llm | Config / model-routing | — |

**Rollup:** `mastering/research_dossier.json` = ordered field reports + cross-wave salience + open assumptions + unresolved clarifying questions.

---

## User-flow → field coverage matrix

| Operator flow | Primary research fields |
|---------------|-------------------------|
| Start / new run / input path | `ingest_normalization`, `stage_reuse_and_hash` |
| Executions tab | `stage_reuse_and_hash`, `journey_gates` |
| Pipeline tab / stage runner | All waves via stage artifacts; `artifact_completeness` |
| Logs / Debug / Volley review | `llm_volley_audit`, `deterministic_lint` |
| Preclean offer | `preclean_lineage`, `source_readiness_band` |
| G0 transcript review | `g0_transcript_fidelity` |
| Profile / speaker roles | `speaker_roles`, `production_style_profile` |
| Stage detail | `thesis_claims`, `coherence_risks`, `narrative_arc_candidates` |
| Timeline / NLE | `nle_operator_edits`, `boundaries_segments` |
| Conversation Studio | `speaker_volleys`, `gap_framing_plan`, `conversation_studio` |
| G-Framing / G-Speaker / G-VoiceRef / G-Delivery | `gap_framing_plan`, `pickup_speaker_voice`, `delivery_brief_budgets` |
| G1 VO pickup / synthesize / skip | `gap_vo_synthesis`, `pickup_speaker_voice` |
| Assembly preview listen | `edl_speech_timeline` |
| G1.5 post-preview pickup | `journey_gates`, `gap_vo_synthesis` |
| SFX prompt approval / post-listen | `sdp_plan_and_prompts`, `mmaudio_assets_qa` |
| Acoustic / SonicContext / SAP | `source_acoustic_profile`, `sonic_context_cues` |
| Mix / Ship / verify_master | `house_chain_levels`, `mix_completeness`, `master_verify` |
| Bootstrap / local models | `local_audio_runtimes`, `llm_routing_tiers` |

**Coverage rule:** no mastering-critical operator ability may lack a field row. Publishing / Flow 2–3: N/A (non-goals).

---

## Pipeline doc coverage

| Pipeline doc area | Waves |
|-------------------|-------|
| capture / preclean / ingest | 1 |
| transcription | 2 |
| understanding / value-analysis | 2–3, 7 |
| segmentation | 4 |
| interviewer-gap | 5 |
| scoring_and_selection | 3–4 |
| audio_editing / assembly_and_mux | 4, 6, 8 |
| mastering_and_export | 6, 8 |
| publishing | N/A |
