# Delivery quality preservation + adaptive policy matrix

Repo-wide inventory of every operator-encounterable surface for **one recording → one `master.wav`**.

Each row has a `policy_role`:

| Role | Meaning |
|------|---------|
| `produce` | Creates or rebuilds adaptive policy (`flow_adaptation` and/or `delivery_brief`) |
| `honor` | Must read and respect `delivery_brief` (and related caps) |
| `integrity_only` | Schema / gate / cross-validate only; does not invent duration or questions |
| `logging_only` | Operator log / UX chrome; no editorial policy |
| `removed` | Dead single-flow residue — do not use in default journey |

Columns: `surface_id` · `kind` · `action_id(s)` · `policy_role` · `reads_brief` · `writes_brief` · `cross_validate` · `notes`

See also: [reliability-charter.md](./reliability-charter.md), [single-flow-rename-map.md](./single-flow-rename-map.md), [operator_action_catalog.json](./operator_action_catalog.json), [gui-surface-map.md](../workflows/gui-surface-map.md).

---

## Analysis stages (`ANALYSIS_ORDER`)

| surface_id | kind | action_id(s) | policy_role | reads_brief | writes_brief | cross_validate | notes |
|------------|------|--------------|-------------|-------------|--------------|----------------|-------|
| audio_preclean | stage | pipeline.stage.audio_preclean; gui.preclean.* | integrity_only | no | no | — | Quality offer; never auto |
| ingest | stage | pipeline.stage.ingest | integrity_only | no | no | — | Fingerprint / normalized.wav |
| transcribe | stage | pipeline.stage.transcribe | integrity_only | no | no | — | Local MLX STT |
| transcript_review_build | stage | pipeline.stage.transcript_review_build | integrity_only | no | no | — | Builds G0 queue |
| disfluency_extract | stage | pipeline.stage.disfluency_extract | removed | — | — | — | G0.5 cut |
| source_acoustic_profile | stage | pipeline.stage.source_acoustic_profile | integrity_only | no | no | — | SAP for mix |
| interview_spine_build | stage | pipeline.stage.interview_spine_build | integrity_only | no | no | post_interview_spine | Soft unless escalated |
| speaker_roles | stage | pipeline.stage.speaker_roles | integrity_only | no | no | — | LLM |
| source_topology_build | stage | pipeline.stage.source_topology_build | produce | no | no | — | Writes `flow_adaptation.json` + graduated `tbiy_conformance` when TBIY |
| content_context | stage | pipeline.stage.content_context | integrity_only | no | no | — | content_brief |
| boundary_detection | stage | pipeline.stage.boundary_detection | integrity_only | no | no | post_boundary_detection | Hard |
| segment_classification | stage | pipeline.stage.segment_classification | integrity_only | no | no | post_segmentation | Hard |
| content_brief_reanchor | stage | pipeline.stage.content_brief_reanchor | integrity_only | no | no | post_reanchor | Hard |
| sonic_context_build | stage | pipeline.stage.sonic_context_build | integrity_only | no | no | post_sonic_context | Hard |
| sound_design_palettes | stage | pipeline.stage.sound_design_palettes | integrity_only | no | no | post_sound_palettes | Soft→harden with brief density |
| missing_framing | stage | pipeline.stage.missing_framing | integrity_only | no | no | post_gaps | Hard |
| optimal_questions | stage | pipeline.stage.optimal_questions | integrity_only | no | no | post_optimal_questions | Feeds gap_report → brief |
| delivery_brief_build | stage | pipeline.stage.delivery_brief_build; gui.delivery_brief.* | produce | no | yes | post_delivery_brief | Deterministic adaptive policy |
| soundscape_policy_build | stage | pipeline.stage.soundscape_policy_build; gui.soundscape.* | produce | yes | no | — | Merges SAP+sonic+brief → soundscape_policy |

---

## Gates

| surface_id | kind | action_id(s) | policy_role | reads_brief | writes_brief | cross_validate | notes |
|------------|------|--------------|-------------|-------------|--------------|----------------|-------|
| transcript_review | gate | gui.transcript_review.complete | integrity_only | no | no | — | G0 |
| disfluency_review | gate | gui.disfluency_review.complete | removed | — | — | — | G0.5 cut |
| analysis_profile | gate | gui.analysis_profile.verify | removed | — | — | — | Profile gate cut |
| g1_vo_pickup | gate | gui.g1.vo.continue; gui.vo.trim.apply | honor | yes | no | — | Lines ≤ question_budget |
| g1_5_preview_pickup | gate | gui.g1_5.preview.continue; gui.g1_5.vo.upload | honor | yes | no | — | Duration band messaging |
| pickup_speaker | gate | gui.adaptation.pickup_speaker; gui.adaptation.confirm | produce | no | yes | — | Via flow_adaptation → brief copy |

---

## Delivery stages (`DELIVERY_ORDER`)

| surface_id | kind | action_id(s) | policy_role | reads_brief | writes_brief | cross_validate | notes |
|------------|------|--------------|-------------|-------------|--------------|----------------|-------|
| topic_coverage_audit | stage | pipeline.stage.topic_coverage_audit | honor | yes | no | post_coherence | Soft |
| narrative_arc_plan | stage | pipeline.stage.narrative_arc_plan | honor | yes | no | post_narrative | Chapters ⊆ brief |
| full_master_ranking | stage | pipeline.stage.full_master_ranking | honor | yes | no | post_ranking | Duration estimate vs band |
| transitions | stage | pipeline.stage.transitions | honor | yes | no | post_transitions | |
| sound_design_plan | stage | pipeline.stage.sound_design_plan | honor | yes | no | post_sound_plan | Asset caps ∩ brief/soundscape |
| sound_design_vo_finalize | stage | pipeline.stage.sound_design_vo_finalize | honor | yes | no | — | |
| edl_narrative_audit | stage | pipeline.stage.edl_narrative_audit | honor | yes | no | post_edl_audit | |
| edl | stage | pipeline.stage.edl | honor | yes | no | — | |
| assembly_preview | stage | pipeline.stage.assembly_preview | integrity_only | yes | no | — | Preview listen |
| sfx_prompt_craft | stage | pipeline.stage.sfx_prompt_craft | honor | yes | no | pre_sfx_generation | |
| mmaudio_sfx | stage | pipeline.stage.mmaudio_sfx; pipeline.soundscape.fitness_remediate | honor | yes | no | pre_mix | Fitness regen/skip |
| mix | stage | pipeline.stage.mix; pipeline.soundscape.verify | honor | yes | no | — | Verify→remux |
| master_finalize | stage | pipeline.stage.master_finalize | honor | yes | no | pre_master_finalize | |

---

## Legacy execute aliases

| surface_id | kind | action_id(s) | policy_role | reads_brief | writes_brief | notes |
|------------|------|--------------|-------------|-------------|--------------|-------|
| mux_flow1 | stage | pipeline.stage.mix (alias) | integrity_only | yes | no | Advanced rerun only; not sidebar |
| podcast_sfx_brief | stage | — | removed | no | no | SDP path is default; keep registered for power-user only |

---

## GUI primary actions (`gui.*`)

| surface_id | kind | action_id(s) | policy_role | reads_brief | writes_brief | notes |
|------------|------|--------------|-------------|-------------|--------------|-------|
| gui.start.select_audio | gui_action | gui.start.select_audio | logging_only | no | no | |
| gui.start.set_REMOVED_flow_intent | gui_action | gui.start.set_REMOVED_flow_intent | removed | no | no | Quarantine |
| gui.run.create | gui_action | gui.run.create | logging_only | no | no | |
| gui.run.resume | gui_action | gui.run.resume | logging_only | no | no | |
| gui.executions.refresh | gui_action | gui.executions.refresh | logging_only | no | no | |
| gui.session.* | gui_action | gui.session.clear/resume_server/retry_load/mute_alerts/open_logs_tab | logging_only | no | no | |
| gui.api_consent.grant | gui_action | gui.api_consent.grant | integrity_only | no | no | Provider consent |
| gui.confirm.* | gui_action | gui.confirm.ok/cancel | logging_only | no | no | |
| gui.nav.tab | gui_action | gui.nav.tab | logging_only | no | no | |
| gui.activity.* | gui_action | gui.activity.dump_last/open_step/toggle_collapsed/tab | logging_only | no | no | |
| gui.write_approval.* | gui_action | gui.write_approval.save/discard/saved/error/still_pending | integrity_only | no | no | Kernel; never auto |
| gui.write_approval.batch_save | gui_action | gui.write_approval.batch_save | integrity_only | no | no | First-try phase-end batch Save |
| gui.g1.skip_optional | gui_action | gui.g1.skip_optional | produce | no | yes | Skip non-blocking VO; rebuild brief |
| gui.transcript_review.complete_auto | gui_action | gui.transcript_review.complete_auto | integrity_only | no | no | First-try clean G0 |
| gui.sfx_prompts.approve_auto | gui_action | gui.sfx_prompts.approve_auto | integrity_only | no | no | First-try G1.5 QA green |
| pipeline.selection.auto_pack | pipeline | pipeline.selection.auto_pack | honor | yes | no | Trim to brief max |
| source_readiness | artifact | understanding/source_readiness.json | integrity_only | no | no | Preclean recommend / auto-dismiss green |
| gui.operator.action | gui_action | gui.operator.action | logging_only | no | no | Generic |
| gui.step_action.* | gui_action | gui.step_action.primary/secondary | integrity_only | no | no | Resolves per-stage |
| gui.checkpoint.continue | gui_action | gui.checkpoint.continue | integrity_only | no | no | advanceFromCheckpoint |
| gui.handoff.acknowledge | gui_action | gui.handoff.acknowledge | integrity_only | no | no | |
| gui.preclean.accept/dismiss/skip | gui_action | gui.preclean.* | integrity_only | no | no | Never auto-run |
| gui.stage_reuse.accept/decline | gui_action | gui.stage_reuse.* | integrity_only | no | no | Brief reuse rules apply |
| gui.g2.select_flow / gui.g2.use_planned | gui_action | gui.g2.* | removed | no | no | Single delivery |
| gui.transcript_review.complete | gui_action | gui.transcript_review.complete | integrity_only | no | no | G0 |
| gui.disfluency_review.complete | gui_action | gui.disfluency_review.complete | removed | — | — | G0.5 cut |
| gui.analysis_profile.verify | gui_action | gui.analysis_profile.verify | removed | — | — | Profile gate cut |
| gui.live_status.primary | gui_action | gui.live_status.primary | integrity_only | no | no | |
| gui.decision.* | gui_action | gui.decision.resolve.start/apply | honor | yes | no | ITR / autopilot |
| gui.autopilot.save | gui_action | gui.autopilot.save | honor | yes | no | Must not skip brief |
| gui.adaptation.confirm | gui_action | gui.adaptation.confirm | produce | no | yes | flow_adaptation → brief |
| gui.adaptation.pickup_speaker | gui_action | gui.adaptation.pickup_speaker | produce | no | yes | |
| gui.gap_report.add_line/remove_line | gui_action | gui.gap_report.* | produce | no | yes | Rebuild question_budget |
| gui.g1.vo.continue | gui_action | gui.g1.vo.continue | honor | yes | no | |
| gui.g1_5.* | gui_action | gui.g1_5.vo.upload / preview.continue | honor | yes | no | |
| gui.vo.trim.apply | gui_action | gui.vo.trim.apply | honor | yes | no | |
| gui.delivery_brief.save / gui.delivery_brief.reset | gui_action | gui.delivery_brief.* | produce | yes | yes | Operator overrides |

---

## Mutating API groups

| surface_id | kind | policy_role | reads_brief | writes_brief | notes |
|------------|------|-------------|-------------|--------------|-------|
| POST /api/runs | api | logging_only | no | no | Create run |
| POST …/execute | api | honor | yes | no | Stage runners; brief before delivery |
| write_approval approve/discard | api | integrity_only | no | no | |
| write_approval approve-batch | api | integrity_only | no | no | First-try phase-end |
| g1/skip-optional | api | produce | no | yes | |
| stages reuse / reuse-from-previous | api | integrity_only | no | no | Brief copy rules |
| transcript-review / disfluency complete | api | integrity_only | no | no | |
| analysis-profile verify | api | produce | yes | yes | |
| VO upload / trim / g1.5 | api | honor | yes | no | |
| flow-adaptation PATCH / confirm / pickup | api | produce | no | yes | |
| gap-report line CRUD | api | produce | no | yes | |
| delivery-brief GET/PATCH | api | produce | yes | yes | New |
| NLE PUT/PATCH/batch | api | produce | yes | yes | Rebuild on structural |
| SFX prompts approve/listen/refine | api | honor | yes | no | Asset caps |
| preclean-offer | api | integrity_only | no | no | |
| ITR auto-resolve / decisions | api | honor | yes | no | |
| artifacts PUT | api | integrity_only | if path=brief | if path=brief | Write validators |
| log / action-trace | api | logging_only | no | no | |

---

## CLI

| surface_id | kind | policy_role | reads_brief | writes_brief | notes |
|------------|------|-------------|-------------|--------------|-------|
| tools/run_analysis.py | cli | produce | no | yes | Ends with delivery_brief_build |
| tools/run_delivery.py | cli | honor | yes | no | Requires brief when hardening on |
| validate_*/verify_* | cli | integrity_only | yes | no | Duration/asset checks where applicable |
| scripts/run.sh | cli | logging_only | no | no | GUI launch |

---

## Config policy planes

| surface_id | kind | policy_role | notes |
|------------|------|-------------|-------|
| analysis.delivery_brief.* | config | produce | Editorial soft targets |
| journey_ui.* | config | integrity_only | UX autopilot / write approval / reuse / handoff |
| sound_design.max_assets | config | honor | Cap ∩ brief.sfx_density |
| analysis.prompt_thresholds.max_chapters | config | honor | Chapter budget ceiling |
| production_profiles.* | config | produce | Seeds flow_adaptation |

---

## Catalog REMOVED (quarantine / delete in Pillar E)

| action_id | policy_role |
|-----------|-------------|
| gui.start.set_REMOVED_flow_intent | removed |
| gui.g2.select_flow | removed |
| gui.g2.use_planned | removed |
| pipeline.execute_flow2 | removed |
| pipeline.execute_flow3 | removed |
| pipeline.stage.REMOVED_* | removed |

---

## KEEP / MERGE / DEFER (product features)

**v2 simplified app** (see [NORTH_STAR.md](../../NORTH_STAR.md), [docs/v2/drop-manifest.md](../v2/drop-manifest.md)):

| Layer | Features |
|-------|----------|
| KEEP | 32-stage analysis + delivery spine, G0 mandatory, G1 optional, SDP chain, QC (`verify_master`), NLE, stage reuse, preclean offer |
| SIMPLIFY | LLM: schema + 1 retry (`llm_simple.py`); auto-commit artifacts; linear pipeline (no volley/autopilot/handoffs) |
| CUT | G0.5 disfluency, profile gate, investigation queue, write approval, handoffs, Decision Wizard, Flow 2 / Flow 3, AWS Transcribe. **Kept:** local MLX framer + STT, `first_try`, `llm_specialists`. |
| MERGE | Former flow2 quotability → `full_master_ranking` via enrichment flags |
| DEFER | Show notes export after master (not a parallel flow) |
| DEPRECATED | Flow 2 montage, Flow 3 parallel pipeline, G2 picker, legacy mux/sfx_brief as default |

---

## Mastering quality hardening

Reliability gates layered on the Mastering Process. All ship `advisory` (fail-open) and are flipped to `authoritative` one at a time. Canon: [mastering-quality-hardening.md](./mastering-quality-hardening.md).

| Gate | Artifact | Preserves |
|------|----------|-----------|
| research routing | `mastering/research/routing.json` | Analysis depth where this source needs it |
| evidence packets | `mastering/evidence_packets/*.json` | Provenance + token discipline per consumer |
| eval rubric | `mastering/shape/eval_rubric.json` | Style-appropriate definition of quality |
| diversity | `mastering/shape/diversity_report.json` | Genuinely different candidates, not renamed clones |
| feasibility | `mastering/shape/feasibility.json` | Buildable plans; locked speaker-volley integrity |
| semantic integrity | `mastering/shape/semantic_integrity.json` | No fabricated meaning from real clips |
| voice clone | `mastering/voice_clone_audit.json` | Consent + scope; guest cloning impossible |
| auditions | `mastering/auditions/*/manifest.json` | Judgement on rendered audio, not plan text |
| multi-critic L4 | `mastering/shape/cross_critique.json` | Independent lanes; integrity may hard-fail |
| Pareto | `mastering/shape/pareto.json` | Strong-somewhere beats mediocre-everywhere |
| closed-loop polish | `mastering/polish_audit.json` | Masking, jolts, dead air fixed before finalize |
| prompt promotion | `mastering/prompt_promotions.json` | Run-local edits cannot silently become global |
