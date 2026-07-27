# Stage ↔ volley matrix

Every analysis, delivery, and gate stage declares how it relates to **speaker volley** and/or **LLM volley**. See [volley-glossary.md](./volley-glossary.md).

"LLM volley" in the right-hand column means only *how the message packet for that stage call is assembled*. There is no volley routing layer, no shard/collate/arbiter path, and no Volley review tab — every cloud call goes through `llm_simple.py` with a max of 2 attempts. See [../v2/drop-manifest.md](../v2/drop-manifest.md).

Rows marked **(Pass 2)** are [Refinement Pass](./refinement-passes.md) stages — deterministic recompose/refine passes gated by L0/L1, not additional LLM calls.

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
| `source_topology_build` | Topology predicts volley shape | LLM volley |
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
| `refinement_agenda` (L0) | Confirms eligible Pass 2 classes against kept volleys | Deterministic |
| `gap_framing_recompose` (Pass 2) | Rewrites host VO against the kept-order volleys; drops orphan lines | Deterministic (constitution: `docs/prompts/interviewer-gap/gap-framing-recompose.system.txt`) |
| `selection_framing_apply` (Pass 2) | Applies `covered_by_framing_vo` excludes after recompose, coverage-guarded | Deterministic |
| `ranking_refine` (Pass 2) | Re-checks topic-survival volleys when coverage holes remain | Deterministic |
| `narrative_arc_refine` (Pass 2) | Re-checks chapters against the volleys that actually kept | Deterministic |
| NLE (optional) | Must not silently split locked volleys | — |
| `transitions` | Bridges only at speaker-volley boundaries | LLM volley |
| `transitions_refine` (Pass 2) | No duplicate bridges after final gap VO | Deterministic |
| `sound_design_plan` | Beds under volleys; stingers at hinges | LLM volley |
| `sdp_intent_refine` (Pass 2) | SFX restraint check against final timeline volleys | Deterministic |
| `sound_design_vo_finalize` | VO duration at volley edges | — |
| `edl_narrative_audit` | Narrative readiness of volley order | LLM volley |
| `edl_narrative_refine` (Pass 2) | Last editorial sanity on volley order before EDL | Deterministic |
| `edl` | Timeline encodes speaker-volley integrity | QC |
| `assembly_preview` | Listen to speaker volleys (speech+VO) | — |
| G1.5 (TBIY) | Re-record with preview of volleys | — |
| `sfx_prompt_craft` | Prompts support speaker volley / hinge | LLM volley |
| `mmaudio_sfx` | Assets placed relative to volleys | — |
| `mix` | Duck beds under speech in active volleys | — |
| `master_finalize` | Master of volley-ordered timeline | — |
| `verify_master` | Loudness of final enjoyable master | — |

Flow 2 / Flow 3 stages were removed from the codebase and are **permanently excluded** from this matrix.

## Mastering quality-hardening gates

Advisory by default; each writes an artifact and only blocks when its mode is `authoritative`. Canon: [mastering-quality-hardening.md](./mastering-quality-hardening.md).

| Gate | Speaker-volley relevance | LLM volley |
|------|--------------------------|------------|
| `evidence_packets` | Bounds what each consumer sees per volley | Deterministic |
| `eval_rubric` | Weights that judge volley pacing for this source | LLM volley (flagship, OH-02) |
| `diversity` | Forces candidates to differ in volley ordering, not just labels | Deterministic |
| `feasibility` | Hard check that locked volleys stay intact | Deterministic |
| `semantic_integrity` | Blocks reorders that fabricate cross-volley meaning | Deterministic + LLM volley (OH-03) |
| `auditions` | Renders 30–90 s of real volley audio per candidate | Deterministic render |
| `critics` | Six critics score volley arc, audio, pacing, integrity | LLM volley ×6 (OH-C1…C6) |
| `arbiter` | Merges the panel; enforces integrity kills | LLM volley (flagship, OH-A1) |
| `pareto` | Keeps frontier survivors instead of one score | Deterministic |

`research_routing` and `polish` config keys survive in `mastering_hardening_config.py`, but their implementing modules (`mastering_research_router.py`, `mastering_polish_loop.py`) were removed — treat both as inert.
