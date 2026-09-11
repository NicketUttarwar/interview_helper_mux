# Prompt ↔ schema ↔ artifact mismatch register

Identify-only. HEAD. Built from `llm_interaction_registry`.

## Stage primary map

| Stage | Registry id | Artifact schema | Prompt file exists |
|---|---|---|---|
| `boundary_detection` | OA-03 | boundaries_artifact.schema.json | see registry |
| `boundary_topic_resplit` | OA-03 | boundaries_artifact.schema.json | see registry |
| `connector_seam_adjudicate` | OF-02a | connector_seam_adjudicate.schema.json | see registry |
| `content_brief_reanchor` | OA-05 | content_brief_artifact.schema.json | see registry |
| `content_context` | OA-02 | content_brief_artifact.schema.json | see registry |
| `edl_narrative_audit` | OF-06 | edl_narrative_audit_artifact.schema.json | see registry |
| `episode_cover_prompt_craft` | MISSING_PRIMARY | MISSING_SCHEMA | see registry |
| `episode_meta_build` | MISSING_PRIMARY | MISSING_SCHEMA | see registry |
| `framing_posture_decide` | OA-09 | framing_posture_decision.schema.json | see registry |
| `full_master_ranking` | OF-03 | master_selection_artifact.schema.json | see registry |
| `gap_framing_compose` | OA-08 | gap_report.schema.json | see registry |
| `ideal_cuts_propose` | OA-10 | ideal_cuts_artifact.schema.json | see registry |
| `island_cluster_structure_adjudicate` | OF-02b | island_cluster_structure_adjudicate.schema.json | see registry |
| `junction_feel_audit` | OH-J1 | junction_feel_audit.schema.json | see registry |
| `junction_thought_complete` | OH-J2 | junction_thought_complete.schema.json | see registry |
| `missing_framing` | OA-07 | gap_evaluations_artifact.schema.json | see registry |
| `music_palette_compose` | OF-06b | music_palette_compose_artifact.schema.json | see registry |
| `narrative_arc_plan` | OF-02 | narrative_plan_artifact.schema.json | see registry |
| `nugget_corpus_mine` | OF-03a | nugget_corpus_artifact.schema.json | see registry |
| `nugget_intro_compose` | OF-06a-i | MISSING_SCHEMA | see registry |
| `nugget_layup_compose` | OF-03b | nugget_layup_plan_artifact.schema.json | see registry |
| `optimal_questions` | OA-08 | gap_report.schema.json | see registry |
| `podcast_sfx_brief` | OF-L1 | podcast_sfx_artifact.schema.json | see registry |
| `segment_classification` | OA-04 | manifest_artifact.schema.json | see registry |
| `sfx_brief` | OF-L2 | sfx_montage_artifact.schema.json | see registry |
| `sfx_prompt_craft` | OF-07 | sfx_prompts_artifact.schema.json | see registry |
| `sfx_prompt_refine` | OF-L3 | sfx_prompts_artifact.schema.json | see registry |
| `sound_design_palettes` | OA-06 | sound_design_palettes_artifact.schema.json | see registry |
| `sound_design_plan` | OF-05 | sound_design_plan_artifact.schema.json | see registry |
| `speaker_roles` | OA-01 | speakers_artifact.schema.json | see registry |
| `synthetic_framing_plan` | MISSING_PRIMARY | synthetic_framing_plan.schema.json | see registry |
| `talking_points_compose` | OA-09 | talking_points_artifact.schema.json | see registry |
| `topic_coverage_audit` | OF-01 | coverage_audit_artifact.schema.json | see registry |
| `transitions` | OF-04 | transitions_artifact.schema.json | see registry |
| `vo_line_adjudicate` | OF-06a | vo_line_adjudication_artifact.schema.json | see registry |

## OPEN_RISK — registry / order mismatches

### PSM-LLM-NO-PRIMARY — `episode_cover_prompt_craft` in ALL_LLM_STAGES but not STAGE_PRIMARY_IDS
- Status: OPEN_RISK | L2 | S2 | Fix-cluster: `prompt-schema-registry`

### PSM-LLM-NO-PRIMARY — `episode_meta_build` in ALL_LLM_STAGES but not STAGE_PRIMARY_IDS
- Status: OPEN_RISK | L2 | S2 | Fix-cluster: `prompt-schema-registry`

### PSM-LLM-NO-PRIMARY — `synthetic_framing_plan` in ALL_LLM_STAGES but not STAGE_PRIMARY_IDS
- Status: OPEN_RISK | L2 | S2 | Fix-cluster: `prompt-schema-registry`

### PSM-ORPHAN-PRIMARY — `island_cluster_structure_adjudicate` in STAGE_PRIMARY_IDS but not in pipeline orders
- Status: OPEN_RISK | L2 | S1 | Fix-cluster: `prompt-schema-registry`

### PSM-ORPHAN-PRIMARY — `junction_feel_audit` in STAGE_PRIMARY_IDS but not in pipeline orders
- Status: OPEN_RISK | L2 | S1 | Fix-cluster: `prompt-schema-registry`

### PSM-ORPHAN-PRIMARY — `junction_thought_complete` in STAGE_PRIMARY_IDS but not in pipeline orders
- Status: OPEN_RISK | L2 | S1 | Fix-cluster: `prompt-schema-registry`

### PSM-ORPHAN-PRIMARY — `nugget_intro_compose` in STAGE_PRIMARY_IDS but not in pipeline orders
- Status: OPEN_RISK | L2 | S1 | Fix-cluster: `prompt-schema-registry`

### PSM-ORPHAN-PRIMARY — `optimal_questions` in STAGE_PRIMARY_IDS but not in pipeline orders
- Status: OPEN_RISK | L2 | S1 | Fix-cluster: `prompt-schema-registry`

### PSM-ORPHAN-PRIMARY — `podcast_sfx_brief` in STAGE_PRIMARY_IDS but not in pipeline orders
- Status: OPEN_RISK | L2 | S1 | Fix-cluster: `prompt-schema-registry`

### PSM-ORPHAN-PRIMARY — `sfx_brief` in STAGE_PRIMARY_IDS but not in pipeline orders
- Status: OPEN_RISK | L2 | S1 | Fix-cluster: `prompt-schema-registry`

### PSM-ORPHAN-PRIMARY — `sfx_prompt_refine` in STAGE_PRIMARY_IDS but not in pipeline orders
- Status: OPEN_RISK | L2 | S1 | Fix-cluster: `prompt-schema-registry`


## Interaction registry cards (sample weaknesses)

### PSM-OA-01
- Surface: LLM
- Registry: `OA-01` entrypoint=`understanding.run_speaker_roles` schema=`composed/envelope+speakers_artifact.schema.json`
- Prompt: `understanding/speaker-roles.system.txt`
- Why weak: schema retry ≤2 then hard stop; packet must strip denylist metadata
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `llm-hard-stop-routing`

### PSM-OA-02
- Surface: LLM
- Registry: `OA-02` entrypoint=`understanding.run_content_context` schema=`composed/envelope+content_brief_artifact.schema.json`
- Prompt: `understanding/content-context.system.txt`
- Why weak: schema retry ≤2 then hard stop; packet must strip denylist metadata
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `llm-hard-stop-routing`

### PSM-OA-09
- Surface: LLM
- Registry: `OA-09` entrypoint=`framing_posture_decide.run_framing_posture_decide` schema=`composed/envelope+framing_posture_decision.schema.json`
- Prompt: `framing/framing-posture-decide.system.txt`
- Why weak: schema retry ≤2 then hard stop; packet must strip denylist metadata
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `llm-hard-stop-routing`

### PSM-OA-10
- Surface: LLM
- Registry: `OA-10` entrypoint=`understanding.run_ideal_cuts_propose` schema=`composed/envelope+ideal_cuts_artifact.schema.json`
- Prompt: `understanding/ideal-cuts-propose.system.txt`
- Why weak: schema retry ≤2 then hard stop; packet must strip denylist metadata
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `llm-hard-stop-routing`

### PSM-OA-03
- Surface: LLM
- Registry: `OA-03` entrypoint=`segmentation.run_boundary_topic_resplit` schema=`composed/envelope+boundaries_artifact.schema.json`
- Prompt: `segmentation/boundary-detection-refine.system.txt`
- Why weak: schema retry ≤2 then hard stop; packet must strip denylist metadata
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `llm-hard-stop-routing`

### PSM-OA-04
- Surface: LLM
- Registry: `OA-04` entrypoint=`segmentation.run_classification` schema=`composed/envelope+manifest_artifact.schema.json`
- Prompt: `segmentation/segment-classification.system.txt`
- Why weak: schema retry ≤2 then hard stop; packet must strip denylist metadata
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `llm-hard-stop-routing`

### PSM-OA-05
- Surface: LLM
- Registry: `OA-05` entrypoint=`understanding.run_content_brief_reanchor` schema=`composed/envelope+content_brief_artifact.schema.json`
- Prompt: `understanding/content-brief-reanchor.system.txt`
- Why weak: schema retry ≤2 then hard stop; packet must strip denylist metadata
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `llm-hard-stop-routing`

### PSM-OA-06
- Surface: LLM
- Registry: `OA-06` entrypoint=`sound_design_stages.run_sound_design_palettes` schema=`composed/envelope+sound_design_palettes_artifact.schema.json`
- Prompt: `sound_design/theme-palettes.system.txt`
- Why weak: schema retry ≤2 then hard stop; packet must strip denylist metadata
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `llm-hard-stop-routing`

### PSM-OA-07
- Surface: LLM
- Registry: `OA-07` entrypoint=`gaps.run_missing_framing` schema=`composed/envelope+gap_evaluations_artifact.schema.json`
- Prompt: `interviewer-gap/missing-framing.system.txt`
- Why weak: schema retry ≤2 then hard stop; packet must strip denylist metadata
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `llm-hard-stop-routing`

### PSM-OA-08
- Surface: LLM
- Registry: `OA-08` entrypoint=`gaps.run_gap_framing_compose` schema=`composed/envelope+gap_report.schema.json`
- Prompt: `interviewer-gap/gap-framing-compose.system.txt`
- Why weak: schema retry ≤2 then hard stop; packet must strip denylist metadata
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `llm-hard-stop-routing`

### PSM-OF-01
- Surface: LLM
- Registry: `OF-01` entrypoint=`analysis_extended.run_topic_coverage` schema=`composed/envelope+coverage_audit_artifact.schema.json`
- Prompt: `selection/topic-coverage-audit`
- Why weak: schema retry ≤2 then hard stop; packet must strip denylist metadata
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `llm-hard-stop-routing`

### PSM-OF-02
- Surface: LLM
- Registry: `OF-02` entrypoint=`analysis_extended.run_narrative_arc` schema=`composed/envelope+narrative_plan_artifact.schema.json`
- Prompt: `selection/narrative-arc-plan`
- Why weak: schema retry ≤2 then hard stop; packet must strip denylist metadata
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `llm-hard-stop-routing`

### PSM-OF-02a
- Surface: LLM
- Registry: `OF-02a` entrypoint=`segment_fuse.adjudicate_seams_llm` schema=`composed/envelope+connector_seam_adjudicate.schema.json`
- Prompt: `segmentation/connector-seam-adjudicate`
- Why weak: schema retry ≤2 then hard stop; packet must strip denylist metadata
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `llm-hard-stop-routing`

### PSM-OF-02b
- Surface: LLM
- Registry: `OF-02b` entrypoint=`island_cluster_structure.adjudicate_island_cluster_structure` schema=`composed/envelope+island_cluster_structure_adjudicate.schema.json`
- Prompt: `segmentation/island-cluster-structure-adjudicate`
- Why weak: schema retry ≤2 then hard stop; packet must strip denylist metadata
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `llm-hard-stop-routing`

### PSM-OF-03
- Surface: LLM
- Registry: `OF-03` entrypoint=`selection.run_full_master_ranking` schema=`composed/envelope+master_selection_artifact.schema.json`
- Prompt: `selection/full-master-ranking`
- Why weak: schema retry ≤2 then hard stop; packet must strip denylist metadata
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK
- Fix-cluster: `llm-hard-stop-routing`


## PSM-TBIY-DUAL — parallel `.system.txt` and `.tbiy.system.txt` prompts

- Surface: LLM
- Modes: all
- Why weak: code may load wrong heritage vs current prompt; examples under `_shared/examples` may contradict live schema
- Likelihood: L2 | Severity: S2
- Evidence: docs/prompts/**/*.tbiy.system.txt alongside current system.txt
- Fix-cluster: `prompt-heritage-drift`
- Status: OPEN_RISK

## PSM-DENYLIST — LLM packet metadata denylist

- Surface: LLM
- Call graph: packers / llm volley context — must strip exists/stage_done/run_meta
- Why weak: any assembler still attaching pipeline metadata teaches model hollow facts
- Likelihood: L2 | Severity: S2
- Evidence: docs/cross-cutting/llm-volley-context.md; homunculus packer
- Fix-cluster: `llm-packet-denylist`
- Status: OPEN_RISK

## PSM-MASTERING-PROMPTS — mastering research/shape prompts vs thin stage incompleteness

- Surface: LLM / stage
- Why weak: many mastering/*.system.txt prompts exist but mastering_* stages lack stage_artifact_incompleteness branches — hollow research artifacts can mark done
- Likelihood: L3 | Severity: S2
- Evidence: docs/prompts/mastering/*; stage_completion gaps
- Fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

---

## Wave-2 elevations (from prompt audit swarm)

### PSM-EMPTY-SKIP — `validate_stage_artifacts` treats `{}` as valid
- Status: OPEN_RISK | L3 | S3 | Fix-cluster: `schema-hollow-gate`
- Evidence: `prompt_validation.validate_stage_artifacts` empty early-return

### PSM-HOLLOW-ARRAYS — required arrays accept `[]`
- Status: OPEN_RISK | L3 | S2 | Fix-cluster: `schema-hollow-gate`
- Affects gap/nugget/VO/transitions/coverage/etc. schemas

### PSM-CONDUCTOR-DENY — pack injects stage_done / artifact_exists
- Status: OPEN_RISK | L3 | S2 | Fix-cluster: `llm-packet-denylist`
- Nested `pack_volley` strips; conductor operational pack does not

### PSM-RETRY-OUTLIERS — junction feel max_attempts=3; seam tier ≤3
- Status: OPEN_RISK | L2 | S2 | Fix-cluster: `llm-hard-stop-routing`
