# LLM interaction catalog

Authoritative registry: `src/interview_mux/llm_interaction_registry.py` (`LLM_INTERACTION_REGISTRY`).  
CI completeness: `tests/test_llm_interaction_registry_complete.py`.

## Architecture

**Two gateways, one registry, one verifier.**

| Gateway | Module | Provider |
|---------|--------|----------|
| `run_prompt_envelope` | `stages/llm_runner.py` | OpenAI Chat Completions |
| `generate_local_chat` | `local_llm_runner.py` | Local MLX subprocess |

Post-call: `verify_llm_response()` in `llm_response_verify.py` — results on `llm_call_record.verification` and GUI (`LlmCallsPanel`, `attentionQueue`).

Strict API schemas: `openai_structured_output.py` (`json_schema` strict).  
Local prompt + verify: `local_structured_output.py`.

Config: `analysis.structured_outputs`, `local_llm.structured_outputs` in `config/app.defaults.json`.

---

## OpenAI — analysis stages (OA)

| ID | stage_key | Goal |
|----|-----------|------|
| OA-01 | `speaker_roles` | Map diarization IDs → interviewer/interviewee |
| OA-02 | `content_context` | Thesis, topics, key_claims |
| OA-03 | `boundary_detection` | Non-overlapping segment timeline |
| OA-04 | `segment_classification` | Type every required segment_id |
| OA-05 | `content_brief_reanchor` | Anchor topics to segment_ids |
| OA-06 | `sound_design_palettes` | Palettes + sonic identity |
| OA-07 | `missing_framing` | Per-segment gap eval |
| OA-08 | `optimal_questions` | VO lines for record gaps |

Post-hooks: OA-04 → OS-02; OA-07 / OF-03 → OS-01; OF-03 pre → OS-04.

---

## OpenAI — flow stages (OF)

| ID | stage_key | Goal |
|----|-----------|------|
| OF-01 | `topic_coverage_audit` | Theme coverage score |
| OF-02 | `narrative_arc_plan` | Chapter arc |
| OF-03 | `full_master_ranking` | Ordered segment_ids |
| OF-04 | `transitions` | Short bridge VO |
| OF-05 | `sound_design_plan` | Cues + assets flow1 |
| OF-06 | `edl_narrative_audit` | Narrative QC verdict |
| OF-07 | `sfx_prompt_craft` | MMAudio prompt rows |
| OF-08 | `REMOVED_highlight_selection` | Highlight clips |
| OF-09 | `REMOVED_sdp_flow2` | Montage SDP |
| OF-10 | `REMOVED_podcast_show_description` | Show blurb |
| OF-L1 | `podcast_sfx_brief` | Legacy v1 SFX brief |
| OF-L2 | `sfx_brief` | Legacy montage brief |
| OF-L3 | `sfx_prompt_refine` | Patch failed asset prompts |

Post-hook: OF-01 → OS-03.

---

## OpenAI — meta calls (OM)

| ID | task_kind | When | Goal |
|----|-----------|------|------|
| OM-01 | `primary` | Every stage attempt (`llm_simple.run_llm_stage_simple`) | Produce stage artifacts |
| OM-F01 | `fabricate` | `llm_output_normalizer` finds fabricatable null paths | Benign values for low-risk null fields |
| OM-SAFE | `safe_prune_extract` | Flagship `context_length` API error | Keep only prompt-relevant tape from one chunk |

Schema: composed `analysis_envelope` + stage artifact (`docs/cross-cutting/json-schemas/artifacts/`).

**Dropped in v2:** OM-02 (`arbiter`), OM-03 (`shard`), OM-04 / OM-05 (`collate`) and the `OM-MG-*` micro-gap-fill family. `llm_arbiter.py`, `llm_subtasks.py`, `llm_shard_plans.py`, `micro_gap_fill.py` and the remediation orchestrator were deleted — a stage runs one full volley and hard-stops on failure.

---

## OpenAI — specialists (OS)

| ID | specialist_key | Parent stage(s) | Artifact |
|----|----------------|-----------------|----------|
| OS-01 | `comprehension_risk_blind` | `missing_framing`, `full_master_ranking` | `comprehension_risks[]` |
| OS-02 | `theme_coverage_pass` | `segment_classification` | `segment_topic_patches[]` |
| OS-03 | `emphasis_coverage_pass` | `topic_coverage_audit` | `emphasis_coverage` |
| OS-04 | `stt_lexicon_island_verify` | `full_master_ranking` (pre) | `group_verdicts[]` → soft `stt_trust_priors` |

---

## Local MLX (LX)

| ID | interaction | When | Schema |
|----|-------------|------|--------|
| LX-01 | `local_framer` | Quality allowlist / framing path | `local_framer_response.schema.json` |
| LX-01a–d | `local_{primary,shard,collate,specialist}` | Per task_kind | same |

Only entrypoint: `local_volley_framer.prepare_volley_for_llm` (fail-open).

**Dropped in v2:** LX-02 / LX-02a (`itr_clarification`), LX-03 (`local_digest_compress`), LX-04 (`local_escalate_advisory`), LX-05 (`local_shard_prep`) and OM-LX-P (`local_capability_planner`). `local_capability_router.py`, `local_capability_manifest.py` and `artifact_clarification_llm.py` were deleted.

---

## Mastering quality hardening (OH)

| ID | interaction | Entrypoint |
|----|-------------|------------|
| OH-02 | `eval_rubric_mint` | `mastering_shape_gates.emit_eval_rubric` |
| OH-03 | `semantic_integrity_confirm` | `mastering_semantic_integrity.merge_llm_findings` |
| OH-C1–C6 | L4 critic panel | `mastering_critics.build_critic_packets` |
| OH-A1 | `l4_arbiter` | `mastering_critics.merge_panel` |
| OH-J1 | `junction_feel_audit` | `junction_snip_qa.run_junction_feel_audit` |
| OH-J2 | `junction_thought_complete` | `thought_complete_recut.run_junction_thought_complete` |

Gate status: [mastering-quality-hardening.md](./mastering-quality-hardening.md). **Dropped in v2:** OH-01 (`research_router`) and OH-P1 (`polish_audit_audio`). Junction snip QA is deterministic plus two O(1) LLMs: OH-J2 (batched hanging-end recuts) then OH-J1 (feel audit). Never per-edge OpenAI.

---

## Explicitly NOT LLM

| Component | Module |
|-----------|--------|
| Coherence report | `coherence/analyze.py` |
| MMAudio | `sfx_mmaudio` |
| Local MLX STT | `transcribe_local` |
| Interview spine build | `interview_spine_stage` |

---

## Golden schemas

- Artifacts: `docs/cross-cutting/json-schemas/artifacts/`
- Envelope: `analysis_envelope.schema.json`
- Composed OpenAI cache: `tools/codegen_openai_schemas.py` → `json-schemas/composed/`

Prompt min examples: `required_response_format.py` via `schema_to_min_example()`.
