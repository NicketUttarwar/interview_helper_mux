# Stage ↔ volley matrix

Every analysis, delivery, and gate stage declares how it relates to **speaker volley** and/or **LLM volley**. See [volley-glossary.md](./volley-glossary.md).

| Stage / gate | Speaker volley | LLM volley |
|--------------|----------------|------------|
| Preclean offer | Preserves speech for later detection | — |
| `audio_preclean` | Cleaner stem for volley clips | — |
| `ingest` | Canonical WAV for volley slices | — |
| `transcribe` | Diarization/turns feed detection | — |
| `transcript_review_build` | Review clips are turn truth | — |
| G0 `transcript_review` | Who-said-what inside volleys | — |
| `source_acoustic_profile` | Pacing/energy of conversational stretches | Compact → LLM volley digests |
| `interview_spine_build` | Time index → volley candidates | Compact → LLM volley |
| `speaker_roles` | Who can participate in a speaker volley | Stage call = LLM volley |
| `source_topology_build` | Topology predicts volley shape | LLM volley + adaptation |
| G-Framing / VoiceRef / Delivery | Host lines between/around volleys | Synthesis prompts = LLM volley |
| `content_context` | Themes spanning volleys | LLM volley |
| `boundary_detection` | Edges that define volley boundaries | LLM volley |
| `segment_classification` | Labels (Q/A/…) for detection | LLM volley |
| `content_brief_reanchor` | Brief grounded to segments in volleys | LLM volley |
| `boundary_topic_resplit` | Split overloaded segments carefully | LLM volley |
| `sonic_context_build` | Cue opportunities at volley hinges | LLM volley / compact |
| `sound_design_palettes` | Palettes support volley mood | LLM volley |
| `missing_framing` | Gaps around volleys | LLM volley |
| `gap_framing_compose` | Framing VO before/between volleys | LLM volley |
| G1 `g1_vo_pickup` | Recorded/synth lines at volley edges | — |
| `delivery_brief_build` | `speaker_volley_density` (soft) | — |
| `soundscape_policy_build` | Cue slots honor volley boundaries | Compact → LLM volley |
| `episode_structure_compose` | Emits `speaker_volleys[]`; cold open → first volley | Deterministic; honors atom |
| `topic_coverage_audit` | Coverage across volley groups | LLM volley |
| `narrative_arc_plan` | Chapters group speaker volleys | LLM volley |
| `full_master_ranking` | Atomic speaker volleys; quality-first | LLM volley |
| NLE (optional) | Must not silently split locked volleys | — |
| `transitions` | Bridges only at speaker-volley boundaries | LLM volley |
| `sound_design_plan` | Beds under volleys; stingers at hinges | LLM volley |
| `sound_design_vo_finalize` | VO duration at volley edges | — |
| `edl_narrative_audit` | Narrative readiness of volley order | LLM volley |
| `edl` | Timeline encodes speaker-volley integrity | QC |
| `assembly_preview` | Listen to speaker volleys (speech+VO) | — |
| G1.5 (TBIY) | Re-record with preview of volleys | — |
| `sfx_prompt_craft` | Prompts support speaker volley / hinge | LLM volley |
| `mmaudio_sfx` | Assets placed relative to volleys | — |
| `mix` | Duck beds under speech in active volleys | — |
| `master_finalize` | Master of volley-ordered timeline | — |
| `verify_master` | Loudness of final enjoyable master | — |

Flow 2 / Flow 3 stages: **permanently excluded** from this matrix’s product path.
