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

Post-hooks: OA-04 → OS-02; OA-07 / OF-03 → OS-01.

---

## OpenAI — flow stages (OF)

| ID | stage_key | Goal |
|----|-----------|------|
| OF-01 | `topic_coverage_audit` | Theme coverage score |
| OF-02 | `narrative_arc_plan` | Chapter arc |
| OF-03 | `full_master_ranking` | Ordered segment_ids |
| OF-04 | `transitions` | Short bridge VO |
| OF-05 | `sound_design_plan_flow1` | Cues + assets flow1 |
| OF-06 | `edl_narrative_audit` | Narrative QC verdict |
| OF-07 | `sfx_prompt_craft` | MMAudio prompt rows |
| OF-08 | `highlight_selection` | Highlight clips |
| OF-09 | `sound_design_plan_flow2` | Montage SDP |
| OF-10 | `podcast_show_description` | Show blurb |
| OF-L1 | `podcast_sfx_brief` | Legacy v1 SFX brief |
| OF-L2 | `sfx_brief` | Legacy montage brief |
| OF-L3 | `sfx_prompt_refine` | Patch failed asset prompts |

Post-hook: OF-01 → OS-03.

---

## OpenAI — meta calls (OM)

| ID | task_kind | When | Goal |
|----|-----------|------|------|
| OM-01 | `primary` | Every stage attempt | Produce stage artifacts |
| OM-02 | `arbiter` | After primary parse | accept / uptier / decompose / investigate |
| OM-03 | `shard` | Decompose or proactive shard | Partial artifact batch |
| OM-04 | `collate` | After ≥1 shard | Merge shard envelopes |
| OM-05 | `collate` + volley retry | Collate lint fail | Second collate attempt |

Schema: composed `analysis_envelope` + stage artifact (`docs/cross-cutting/json-schemas/artifacts/`).  
Arbiter: `arbiter_verdict.schema.json`.

---

## OpenAI — specialists (OS)

| ID | specialist_key | Parent stage(s) | Artifact |
|----|----------------|-----------------|----------|
| OS-01 | `comprehension_risk_blind` | `missing_framing`, `full_master_ranking` | `comprehension_risks[]` |
| OS-02 | `theme_coverage_pass` | `segment_classification` | `segment_topic_patches[]` |
| OS-03 | `emphasis_coverage_pass` | `topic_coverage_audit` | `emphasis_coverage` |

---

## Local MLX (LX)

| ID | interaction | When | Schema |
|----|-------------|------|--------|
| LX-01 | `local_framer` | Before OpenAI when `local_llm.enabled` | `local_framer_response.schema.json` |
| LX-01a–d | `local_{primary,shard,collate,specialist}` | Per task_kind | same |
| LX-02 | `itr_clarification` | Blocking ITR + `local_llm_for_important` | `itr_clarification_options.schema.json` |

ITR fail-open on verify failure (`local_llm.structured_outputs.fail_open_on_verify`).

---

## Explicitly NOT LLM

| Component | Module |
|-----------|--------|
| Coherence report | `coherence/analyze.py` |
| MMAudio | `sfx_mmaudio` |
| AWS Transcribe | `transcribe_aws` |
| Interview spine build | `interview_spine_stage` |
| Disfluency extract | `disfluency` |

---

## Golden schemas

- Artifacts: `docs/cross-cutting/json-schemas/artifacts/`
- Envelope: `analysis_envelope.schema.json`
- Composed OpenAI cache: `tools/codegen_openai_schemas.py` → `json-schemas/composed/`

Prompt min examples: `required_response_format.py` via `schema_to_min_example()`.
