# Swarm merge appendix — additional OPEN_RISK cards from parallel agents

Identify-only. Deduped lightly against INDEX; keep for cluster reviews.

### Key symbols

- `operator_gates.OPERATOR_GATE_STAGES`, `is_operator_gate`, `should_stamp_needs_operator`, `is_unattended_run`
- `gates.check_*` / `require_*` / `clear_*` for G0, G1, G-Listen, G-Publish, optimizer, post-listen
- `operator_gate_view.build_operator_gates`, `resolve_*_gate`
- `automation_run.PARTIAL_AUTO_PREPARE_UNTIL_G0`, `automation_driver_run`, `is_partially_accelerated_run`, `is_full_auto_run`
- `web/runner._stages_for_execute` — `analysis_until_g0` branch

---

## 2. Frontend gate panels → actions → APIs

Under `frontend/src/components/gates/`:

| Panel | Main actions | APIs |
|---|---|---|
| `TranscriptReviewPanel` | Edit chunk text; listen clips | `PUT/PATCH …/transcript-review/{chunkId}`; complete via AppContext `…/transcript-review/complete` |
| `StageReviewGateBanner` / `ReviewGateBannerShell` | Complete / accept-unreviewed G0 | via `useTranscriptReviewGate` → `completeTranscriptReview` → `POST …/transcript-review/complete` |
| `GapFramingGatePanel` | Yes / No framing | `GET …/gap-framing`; `POST …/gap-framing/enable` |
| `PickupSpeakerPanel` | Select/confirm speaker; skip gap | `GET/POST …/pickup-speaker`; `POST …/pickup-speaker/confirm`; `POST …/gap-fill/skip`; audio |
| `VoiceReferencePanel` | Select segment; approve | `GET …/voice-reference`; `POST …/voice-reference/select`; `POST …/voice-reference/approve`; audio |
| `GapDeliveryPanel` | Chatterbox / record | `GET …/gap-framing`; `POST …/gap-framing/delivery` |
| `VoiceCloneConsent` | Grant / re

---

### VJ-01 — `premature_cap_hard_pin` lease can stick a dead job
| Field | Value |
|---|---|
| **id** | VJ-01 |
| **Surface** | Delivery resume / Full-auto heal |
| **Modes** | Full-auto \| Partial |
| **Brain 0.1.0** | Yes (driver + guardrails) |
| **Call graph** | `full_auto_driver` → `premature_cap_hard_pin` → `expensive_stage_lease_active` |
| **Prompt/schema/artifact** | `operator/delivery_pin.json`; GUI job JSON |
| **Model invoke** | None |
| **Invariant** | Premature-cap must pin incomplete **producer**, never advance consumer |
| **Why weak** | If GUI job stays `running`/`starting` on an expensive stage, lease short-circuits all fail-class pins |
| **Manifestation** | `"forbid premature rewrite"` / lease returns `lease_stage` before music/VO/finalize classes |
| **Heal/stop path** | Clear/recover GUI job; sticky heal ×3; identical_failures |
| **Footgun?** | Yes — stale job lease traps resume |
| **Likelihood** | L2 |
| **Severity** | S2 |
| **Evidence** | `delivery_guardrails.py:premature_cap_hard_pin`, `thrash_hardening.py:expensive_stage_lease_active` |
| **fix-cluster** | premature-cap-lease |
| **Status** | OPEN_RISK |

---


---

### VJ-02 — `heal_navigate` / `path_to_master_pin` Phase-A seal skew → music
| Field | Value |
|---|---|
| **id** | VJ-02 |
| **Surface** | Heal resume ladder |
| **Modes** | Manual \| Full-auto \| Partial |
| **Brain 0.1.0** | Yes |
| **Call graph** | `heal_navigate` → `path_to_master_pin` / `canonical_resume_pin` |
| **Prompt/schema/artifact** | `operator/delivery_checkpoint.json`, `delivery_epoch` |
| **Model invoke** | None |
| **Invariant** | Post–Phase-A never rewind to `edl_narrative_audit`; pre-seal never pin music while filter empties music |
| **Why weak** | Non-hard upstream reasons fall through (“Seal-only skew”) into music producers while Phase A still open |
| **Manifestation** | `"Seal-only skew: fall through to music / mix ladder below."` |
| **Heal/stop path** | `premature_cap_hard_pin` music-epoch branch; `filter_delivery_candidates` |
| **Footgun?** | Medium — seal lag + music pin |
| **Likelihood** | L2 |
| **Severity** | S2 |
| **Evidence** | `thrash_hardening.py:path_to_master_pin`, `thrash_hardening.py:heal_navigate` |
| **fix-cluster** | heal-navigate-ladder |
| **Status** | OPEN_RISK |

---


---

### VJ-04 — `may_rewind_to_vo_synthesize` fail-open on G1 exception
| Field | Value |
|---|---|
| **id** | VJ-04 |
| **Surface** | G1 ↔ VO monotonicity |
| **Modes** | Manual \| Full-auto \| Partial |
| **Brain 0.1.0** | Yes (`agenda.earliest_incomplete_seed_stage`) |
| **Call graph** | agenda / `recovery_controller` / `llm_flow_hardening` → `may_rewind_to_vo_synthesize` |
| **Prompt/schema/artifact** | G1 gate, `vo_contract`, transition pairs |
| **Model invoke** | None |
| **Invariant** | After assembly, rewind to VO only for G1/script/transition holes |
| **Why weak** | `check_g1_vo` exception path returns **True** (allows rewind) |
| **Manifestation** | `"except Exception: return True"` after G1 skip/check |
| **Heal/stop path** | `refuse_vo_synthesize_rewind` wasted-work; seed-order continue |
| **Footgun?** | Yes |
| **Likelihood** | L2 |
| **Severity** | S3 |
| **Evidence** | `delivery_guardrails.py:may_rewind_to_vo_synthesize` |
| **fix-cluster** | vo-g1-monotonic |
| **Status** | OPEN_RISK |

---


---

### VJ-05 — Seed-order VO hole when rewind guard throws
| Field | Value |
|---|---|
| **id** | VJ-05 |
| **Surface** | Homunculus seed front |
| **Modes** | Full-auto \| Partial (0.1.0) |
| **Brain 0.1.0** | Yes |
| **Call graph** | `earliest_incomplete_seed_stage` → `may_rewind_to_vo_synthesize` |
| **Prompt/schema/artifact** | `master/assembly.wav`, VO incompleteness |
| **Model invoke** | None |
| **Invariant** | Late transition pairs must not yank conductor to `vo_synthesize` |
| **Why weak** | Outer `except` around may_rewind is pass-through; later `check_g1_vo` except **returns** `vo_synthesize` |
| **Manifestation** | `"Late-added spoken transition pairs after assembly must not yank…"` then except→`return sid` |
| **Heal/stop path** | Manual pin / unstick |
| **Footgun?** | Yes |
| **Likelihood** | L2 |
| **Severity** | S3 |
| **Evidence** | `homunculus/agenda.py:earliest_incomplete_seed_stage` |
| **fix-cluster** | vo-g1-monotonic |
| **Status** | OPEN_RISK |

---


---

### VJ-06 — `music_epoch_complete` stamp trust + raw marker reseat
| Field | Value |
|---|---|
| **id** | VJ-06 |
| **Surface** | Music → mix gate |
| **Modes** | Manual \| Full-auto \| Partial |
| **Brain 0.1.0** | Yes |
| **Call graph** | filter / pipeline / runtime / `safe_mix_resume_stage` → `music_epoch_complete` |
| **Prompt/schema/artifact** | `delivery_epoch.music_complete_at`, SDP WAVs, `.stage_done` |
| **Model invoke** | MusicGen / MMAudio (downstream) |
| **Invariant** | No hollow QA bypass; no MusicGen reburn on hollow adjudicate |
| **Why weak** | Stamp path uses `_mark_done_raw` to touch markers; broad `except: pass` after missing-SDP check can fall through |
| **Manifestation** | `"TH1a: bypass heal_or_refuse — stamp already proves epoch."` |
| **Heal/stop path** | `break_music_epoch_seal` on missing SDP |
| **Footgun?** | Medium |
| **Likelihood** | L2 |
| **Severity** | S3 |
| **Evidence** | `delivery_guardrails.py:music_epoch_complete` |
| **fix-cluster** | music-epoch |
| **Status** | OPEN_RISK |

---


---

### VJ-07 — `mix_epoch_block` no-ops when Phase A unsealed + unstable
| Field | Value |
|---|---|
| **id** | VJ-07 |
| **Surface** | Mix/junction/finalize dispatch |
| **Modes** | Manual \| Full-auto \| Partial |
| **Brain 0.1.0** | Yes (`runtime.dispatch_stage`, `pipeline`) |
| **Call graph** | `dispatch_stage` / `pipeline` → `mix_epoch_block` |
| **Prompt/schema/artifact** | Phase A seal, music epoch |
| **Model invoke** | None at gate |
| **Invariant** | Mix waits until `music_epoch_complete` |
| **Why weak** | `if not stable and not phase_a_sealed: return None` → **no block**; forced `--from-stage mix` can run early (filter may not apply) |
| **Manifestation** | `"B3: mix/master/ship wait until music_epoch_complete"` vs early `return None` |
| **Heal/stop path** | `filter_delivery_candidates`; `safe_mix_resume_stage` on driver redirect |
| **Footgun?** | Yes — forced mix |
| **Likelihood** | L2 |
| **Severity** | S3 |
| **Evidence** | `delivery_guardrails.py:mix_epoch_block`, `homunculus/runtime.py` (~272) |
| **fix-cluster** | music-epoch |
| **Status** | OPEN_RISK |

---


---

### VJ-10 — Sticky heal progress-token reset
| Field | Value |
|---|---|
| **id** | VJ-10 |
| **Surface** | Driver premature / incomplete-after-conductor |
| **Modes** | Full-auto |
| **Brain 0.1.0** | Driver-coupled |
| **Call graph** | `full_auto_driver` → `note_sticky_heal_attempt` |
| **Prompt/schema/artifact** | `operator/sticky_heal.json` |
| **Model invoke** | None |
| **Invariant** | Same pin+predicate ×3 → STOP; token change resets |
| **Why weak** | Oscillating predicate tokens can reset forever (bounded only if token stabilizes) |
| **Manifestation** | `"Progress (predicate token change) resets the counter"` |
| **Heal/stop path** | `STOP: … sticky heal`; true_waste |
| **Footgun?** | Medium |
| **Likelihood** | L2 |
| **Severity** | S2 |
| **Evidence** | `thrash_hardening.py:note_sticky_heal_attempt` |
| **fix-cluster** | identical-sticky-waste |
| **Status** | OPEN_RISK |

---


---

### GFR-01 — Posture LLM is advisory; sticky Yes/No is separate
- Surface: gate | LLM | homunculus-tool
- Modes: Manual | Full-auto | Partial
- Brain: 0.1.0 only runs LLM; non-homunculus heals-mark without artifact
- Call graph: `stages/framing_posture_decide.py:run_framing_posture_decide` → `framing_posture.py:persist_framing_decision` (`advisory_only=True`) → later `gap_vo_gates.py:set_gap_framing_enabled` (operator/API/auto-accept only)
- Prompt/schema/artifact: `docs/prompts/framing/framing-posture-decide.system.txt`; `docs/cross-cutting/json-schemas/framing_posture_decision.schema.json`; `understanding/framing_posture_decision.json`
- Model: `run_analysis_llm_stage` (homunculus runs only)
- Invariant: LLM recommendation must not silently flip `run_meta.gap_framing_enabled`
- Why weak: `apply_host_gate` enforces `native_only` only for `deterministic_monologue|operator_g_framing|forced_skip` — **not** `llm_advisory`. Auto-accept uses `recommended_gap_framing_enabled()` (config default True), not posture JSON.
- Manifestation: `llm_recommended_framing` in `gap_gate_payload_for_run` while sticky key unset/pending; Homunculus still auto-Yes on hosted 1:1
- Heal/stop: Operator No via `POST …/gap-framing/enable`; monologue → `ensure_gap_fill_skipped`
- Footgun: UI/operator may think posture “No” turned framing off
- L3 / S2 — Evidence: `framing_posture.py:apply_host_gate`, `gap_vo_gates.py:maybe_auto_accept_gap_gate_defaults`, `homunculus/gates.py:recommended_framing_action`
- 

---

### GFR-02 — Pending vs `gap_framing_enabled` default True
- Surface: gate | API | GUI
- Modes: Manual | Partial (Full-auto / Homunculus usually auto-stamps)
- Call graph: `gap_vo_gates.py:gap_framing_enabled` (fallback default) vs `check_gap_framing_decision_pending` vs `pipeline.py:_run_missing_framing_stage` → `require_gap_framing_decision_clear`
- Invariant: No gap LLM until explicit Yes/No (or auto-accept)
- Why weak: Unset key → `enabled=True` **and** `decision_pending=True` simultaneously in payload
- Manifestation: `gap_framing_enabled: true` + `gap_framing_decision_pending: true` from `gap_gate_payload_for_run`
- Footgun: Partial accelerated overlay treats framing as `automation_pending` (`partialAcceleratedGuard.ts`)
- L2 / S3 — Evidence: `gap_vo_gates.py:gap_framing_enabled`, `check_gap_framing_decision_pending`; `operator_gate_view.py:resolve_framing_gate`
- Fix-cluster: `g_framing_pending_semantics`
- Status: **OPEN_RISK** (guarded by SystemExit / hard_block UI; semantics still lie)


---

### GFR-03 — Homunculus auto-resolve path
- Surface: homunculus-tool | gate
- Modes: Full-auto | Partial (driver) | Manual N/A unless `INTERVIEW_MUX_AUTO_ACCEPT_GATES`
- Call graph: `homunculus/gates.py:recommended_framing_action` → `maybe_auto_accept_gap_gate_defaults` → `set_gap_framing_enabled` + pickup/voice/delivery cascade
- Invariant: Hosted 1:1 auto-Yes + least-spoken host clone
- Why weak: `set_gate_decision(..., auto_resolve)` only writes `mastering/homunculus/gate_decisions.json` — sticky enable is pipeline-side; posture LLM ignored
- L2 / S2 — Evidence: `gap_vo_gates.py:maybe_auto_accept_gap_gate_defaults`, `homunculus/gates.py:set_gate_decision`
- Fix-cluster: `homunculus_framing_auto_yes`
- Status: **LIKELY_MITIGATED_ON_HEAD** for monologue skip; **OPEN_RISK** for advisory ignore

---

## Stage cards


---

### MRR-01 — `mastering_research_routing`
- Surface: stage
- Modes: all (mode-invariant stub)
- Impl: `mastering_research.py:run_mastering_research_routing` → `run_research_routing`
- Dispatch: `pipeline.py` STAGE map → `run_mastering_research_routing`
- Prompt: `docs/prompts/mastering/research-router.system.txt` (**spec only** — README: “Until cutover”)
- Schema: `mastering_research_routing.schema.json` requires `fields`, mode∈{off,advisory,authoritative}; writer emits `mode:"sequential_waves"`, `waves`, `field_count` — **shape mismatch**; stage-contract `schema: null`
- Artifact: `mastering/research/routing.json`
- Model: **N/A** (non-LLM). Port-manifest says `non_llm` (ok); docs still describe LLM router
- Weak junction: Hollow routing always “complete”; no source-adaptive field disposition
- L3 / S2 — Evidence: `mastering_research.py:run_research_routing`; schema vs writer
- Fix-cluster: `research_llm_cutover_gap`
- Status: **OPEN_RISK**


---

### MRW-01 — `mastering_research_waves`
- Surface: stage
- Modes: all
- Impl: `mastering_research.py:run_mastering_research_waves` → `_probe` existence checks only
- Prompt: field mint prompts documented; **not invoked**
- Schema: field reports exist; waves.json informal
- Port-manifest: **`llm`** — **false on HEAD**
- Call graph: probes many **future** artifacts (`delivery_brief`, `episode_structure`, `selection`, `edl`, mix…) → mostly `skipped_or_thin` at analysis time by design
- Weak junction: Fail-open thin dossier presented as research waves; Shape compiles thin evidence
- L3 / S2 — Evidence: `mastering_research.py:FIELD_PROBES`, `write_field_report`; `docs/prompts/mastering/README.md`
- Fix-cluster: `research_probe_stub_as_waves`
- Status: **OPEN_RISK**


---

### MRU-01 — `mastering_research_rollup`
- Surface: stage
- Modes: all
- Impl: `run_mastering_research_rollup` → `run_research_rollup` (re-runs routing+waves, writes dossier)
- Schema: `mastering_research_dossier.schema.json` requires `field_reports`, `salience_map`; writer uses `waves`/`fields`/`complete_fields`/`thin_fields` — **mismatch**; not in STAGE_ARTIFACT_SCHEMAS enforcement path for rollup
- Artifacts: `mastering/research_dossier.json` + `mastering/research/rollup.json` (duplicate)
- Weak junction: Double-write + schema drift; consumers trust dossier completeness counts that are probe-based
- L2 / S2 — Evidence: `mastering_research.py:run_research_rollup`; dossier schema
- Fix-cluster: `research_dossier_schema_drift`
- Status: **OPEN_RISK**


---

### MSA-01 — `mastering_shape_agenda`
- Surface: stage
- Modes: all
- Impl: `mastering_shape_runtime.py:run_mastering_shape_agenda` — heuristic `nearest_mode_from_priors`; **early return if `soft_gate_enabled()` false** (no artifact)
- Prompt: `shape-meta-architect.system.txt` / L0–L5 — **spec contracts, unwired**
- Schema: `mastering_shape_agenda.schema.json` requires `steps`/`budgets`/`north_star_pillars`; writer uses `mode_candidates`/`custom_steps` — **mismatch**
- Not in `ALL_LLM_STAGES`; port-manifest marks `llm`
- Weak junction: Soft-gate off → silent no-op; soft-gate on → rubric weights 0 for nugget/sonic; advisory L0 only
- L3 / S2 — Evidence: `run_mastering_shape_agenda`; `docs/prompts/mastering/README.md`; `config/app.defaults.json` soft_gate `mode:advisory`
- Fix-cluster: `shape_llm_cutover_gap`
- Status: **OPEN_RISK**


---

### MSC-01 — `mastering_shape_candidates`
- Surface: stage
- Modes: all
- Impl: `run_mastering_shape_candidates` — deterministic cand list from agenda modes; hardcoded descending scores; diversity skipped by default (`skip_diversity: true`)
- Prompt: `shape-l2-candidates.system.txt` unwired
- Artifact: `mastering/shape/candidates.json`
- Weak junction: Fake competition scores; first cand wins downstream
- L3 / S2 — Evidence: `mastering_shape_runtime.py:run_mastering_shape_candidates` (scores `0.7 - i*0.05`)
- Fix-cluster: `shape_heuristic_candidates`
- Status: **OPEN_RISK**


---

### MPS-01 — `mastering_plan_synthesize`
- Surface: stage
- Modes: all
- Impl: `run_mastering_plan_synthesize` — picks `cands[0]`; fail → `forced_sparse_plan`; soft_gate off → forced sparse write
- Prompt: `flagship-synthesize.system.txt` unwired
- Schema: `mastering_plan.schema.json` via `write_plan` / loader degrade path
- Artifact: `mastering/mastering_plan.json` (provisional)
- Config: `consumers_bind: false`, soft_gate `mode: advisory` — plan often **non-binding** for air
- Weak junction: Provisional “complete” plan from hollow research + first heuristic cand
- L3 / S2 — Evidence: `run_mastering_plan_synthesize`; `mastering_plan_loader.py:consumers_bind_enabled`; defaults
- Fix-cluster: `shape_plan_advisory_hollow`
- Status: **OPEN_RISK**


---

### MF-01 — `missing_framing`
- Surface: stage | LLM | gate
- Modes: Manual (hard-block G-Framing); Full-auto/Partial (auto-accept + hard-stop if Yes+ineligible)
- Impl: `pipeline.py:_run_missing_framing_stage` → gates → `stages/gaps.py:run_missing_framing` (shard/batch LLM)
- Prompt: `docs/prompts/interviewer-gap/missing-framing.system.txt` (+ tbiy variant)
- Schema: `gap_evaluations_artifact.schema.json` → `understanding/gap_evaluations.json`
- Call graph: `maybe_auto_accept` → `require_gap_framing_decision_clear` → `require_gap_path_clear` (speaker/voice/delivery/consent) → eligibility loud-fail or skip stub
- Weak junctions: (1) Yes + ineligible → `raise_loud_failure` unless `auto_skip_when_ineligible`; (2) large-tape sharding + default fill for uncovered segs; (3) lint only checks nonempty evals
- L2 / S3 (stuck) / S2 (quality) — Evidence: `pipeline.py:_run_missing_framing_stage`; `gaps.py:run_missing_framing`; `deterministic_lint.py:_lint_missing_framing`
- Tests: `test_gap_framing_gates.py`, `test_gap_fill_eligibility.py`
- Fix-cluster: `gap_fill_gate_ladder`
- Status: **OPEN_RISK** (eligibility hard-stop intentional; quality/lint weak)


---

### MPC-01 — `mastering_plan_confirm`
- Surface: stage
- Modes: all
- Impl: `run_mastering_plan_confirm` — Pass2 after `missing_framing`, **before** `gap_framing_compose`
- Order: `v2/config.py` ANALYSIS_ORDER places confirm between missing_framing and gap_framing_compose
- Weak junction: Mode flip uses eval **count** heuristics (`n==0`→sparse, `n>=8`→guide_summary); `_maybe_shadow_diff` reads `gap_report` which usually **does not exist yet** → vo_density_air=0; soft_gate off → early return leaves provisional
- Prompt: semantic-integrity / L5 unwired
- L3 / S2 — Evidence: `mastering_shape_runtime.py:run_mastering_plan_confirm`, `_maybe_shadow_diff`; `v2/config.py:ANALYSIS_ORDER`
- Fix-cluster: `shape_pass2_before_compose`
- Status: **OPEN_RISK**


---

### GFC-01 — `gap_framing_compose`
- Surface: stage | LLM
- Modes: Manual/Full-auto/Partial — skipped stubs when framing No / gap-fill skip
- Impl: `pipeline.py:_run_gap_framing_compose_stage` → `gaps.py:run_gap_framing_compose` → repairs/high-gap fill → `after_gap_compose_hook`
- Prompt: `interviewer-gap/gap-framing-compose.system.txt`
- Schema: `gap_report.schema.json` → `understanding/gap_report.json` (+ companions)
- Weak junctions: LLM fail → high-gap fill seed path; draft only until delivery `gap_framing_recompose`; skip-stub refuse while framing Yes (`ensure_gap_fill_skipped`); stage_completion detects skip stub under Yes
- L2 / S2 — Evidence: `gaps.py:run_gap_framing_compose`; `stage_completion.py:_gap_report_skip_stub_while_framing`
- Fix-cluster: `gap_compose_draft_quality`
- Status: **OPEN_RISK**


---

### DBB-01 — `delivery_brief_build`
- Surface: stage (deterministic)
- Modes: all
- Impl: `delivery_brief.py:run_delivery_brief_build` / `build_delivery_brief`
- Prompt: N/A
- Schema: `delivery_brief.schema.json` (validated on write path / cross-validate)
- Stage-contract hard input: `gap_report` — OK in order after compose/skip
- Weak junction: Disabled → zeroed stub still written; VO budgets from gap_report lines (skip stub → near-zero questions); TBIY heritage fields still attachable
- L2 / S2 — Evidence: `delivery_brief.py:run_delivery_brief_build`, `_count_vo_gaps`
- Fix-cluster: `delivery_brief_density_from_stub`
- Status: **OPEN_RISK** (mild when framing Yes + real compose)


---

### SPB-01 — `soundscape_policy_build`
- Surface: stage
- Modes: all
- Impl: `soundscape_policy.py:run_soundscape_policy_build`
- Prompt: N/A
- Schema: `soundscape_policy.schema.json` (raises on invalid)
- Weak junctions: `soundscape.enabled=false` → `mark_done` **without** policy artifact; enabled 


## Agent `6840cbfc-ee0a-4726-a2ab-02ffc40fe7bf`

len=26157


## Scoring (HEAD)
- **L3** multi-writer / missing happy-path guard / mode bypass / spin · **L2** incomplete call-sites · **L1** single path + tests  
- **S4** heal/invalidation loop · **S3** stuck `needs_operator` · **S2** hollow/wrong master · **S1** footgun/waste  
- **Status:** `OPEN_RISK` | `LIKELY_MITIGATED_ON_HEAD` | `UNKNOWN_NEEDS_READ`

Focus junctions: **VO/G1 · seats · transitions freeze · music epoch · remutate · junction · pending master · publish S3 consent (Partial)**. Brain **0.1.0**.

---


---

### D-TCA-01 — topic_coverage_audit LLM/deterministic fork
- Surface: stage | LLM  
- Modes: Manual | Full-auto | Partial  
- Brain: 0.1.0  
- Call graph: `pipeline.execute` → `analysis_extended.run_topic_coverage` → `run_flow_llm_stage` / deterministic heal  
- Prompt/schema/artifact: `docs/prompts/selection/topic-coverage-audit*` · `master/coverage_audit.json` · OF-01  
- Model: llm_simple / loop gateway  
- Invariant: coverage must match talking-points/ideal-cuts authority before ranking  
- Why weak: dual path (deterministic skip vs LLM); hollow done possible if artifact weak  
- Manifestation: `"topic_coverage_audit: deterministic from talking points"`  
- Heal: incompleteness / re-run from seed front  
- Footgun: Manual re-run after hitch wipe  
- Likelihood: **L2** | Severity: **S2**  
- Evidence: `analysis_extended.py:run_topic_coverage` · TEST_GAP (coverage-specific thrash)  
- Fix-cluster: `coverage-authority`  
- Status: **OPEN_RISK**

---


---

### D-NAP-01 — narrative_arc_plan chapter map seed
- Surface: stage | LLM  
- Modes: Manual | Full-auto | Partial  
- Brain: 0.1.0  
- Call graph: `analysis_extended.run_narrative_arc` → hitch consumer  
- Prompt/schema: `selection/narrative-arc-plan*` · `master/narrative_plan.json`  
- Invariant: plan frozen by hitch before ranking mutates chapters  
- Why weak: hitch can wipe/restage; plan may lag VO snapshot  
- Manifestation: hitch `INTENT_REL` copy from narrative  
- Heal: `chapter_close_hitch` latch / remutate host repair  
- Likelihood: **L2** | Severity: **S2**  
- Evidence: `analysis_extended.py:run_narrative_arc`, `chapter_close_hitch.py:run_chapter_close_hitch`  
- Fix-cluster: `hitch-chapter-freeze`  
- Status: **OPEN_RISK**

---


---

### D-CCH-01 — chapter_close_hitch VO snapshot / reseat (seats · VO/G1)
- Surface: stage  
- Modes: Manual | Full-auto | Partial (Full-auto auto-continues wipe)  
- Brain: 0.1.0  
- Call graph: `run_chapter_close_hitch` → `snapshot_pre_hitch_state` → remap keepers → `clamp_hosted_seats_to_rendered_wavs`  
- Artifact: `mastering/chapter_close_hitch.json`, `vo_snapshot.json`  
- Invariant: remapped G1 WAVs stay seated; clamp after mutate  
- Why weak: listen_restage / wipe paths; clamp only at hitch terminal — mid-path omit writers elsewhere may not clamp  
- Manifestation: `"chapter_close_hitch: latch committed — no-op"`  
- Heal: latch resume; `vo_contract.ensure_hosted_framing_vo_seats`  
- Footgun: Manual force re-hitch after G1 green  
- Likelihood: **L2** | Severity: **S3**  
- Evidence: `chapter_close_hitch.py:run_chapter_close_hitch`, `vo_contract.py:clamp_hosted_seats_to_rendered_wavs`, `tests/test_chapter_close_hitch.py`  
- Fix-cluster: `seat-clamp-after-mutate`  
- Status: **OPEN_RISK** (clamp inventory incomplete vs W4)

---


---

### D-FMR-01 — full_master_ranking order authority
- Surface: stage | LLM  
- Modes: all (Partial operator may NLE-edit)  
- Call graph: `selection.run_full_master_ranking` → selection.json → sanitize  
- Prompt: `selection/full-master-ranking*` · OF-03  
- Invariant: `ordered_segment_ids` lead EDL; no zero-ms keeps  
- Why weak: ranking compact gap; later remutate can rewind to ranking and recreate late-intro clusters (host repair tries to avoid)  
- Manifestation: remutate notes `drop_late_intro_reset` → `nugget_layup_compose`  
- Heal: `plan_edl_narrative_remutate` / host repair  
- Likelihood: **L2** | Severity: **S3**  
- Evidence: `selection.py:run_full_master_ranking`, `edl_narrative_remutate.py:apply_edl_narrative_remutate`  
- Fix-cluster: `remutate-pin`  
- Status: **OPEN_RISK**

---


---

### D-SOS-01 — selection_order_sanitize sanitary gate
- Surface: stage  
- Modes: all  
- Call graph: `artifact_sanitize.selection.run_selection_order_sanitize` · incompleteness in `stage_completion`  
- Invariant: layup/SDP refuse unsanitary selection  
- Why weak: consumers pin sanitize; heal thrash if order flip-flops  
- Likelihood: **L2** | Severity: **S2**  
- Evidence: `stage_completion.py:stage_artifact_incompleteness` (`selection_order_sanitize`)  
- Fix-cluster: `sanitize-completeness`  
- Status: **OPEN_RISK**

---


---

### D-ASC-01 — air_script_compose seats writer (seats)
- Surface: stage  
- Modes: all  
- Call graph: `air_script.run_air_script_compose` → `build_vo_seats` · later omit paths call clamp  
- Artifact: mastering plan `air_script.vo_seats`  
- Invariant: one writer authority (`vo_contract` / `build_vo_seats`)  
- Why weak: multiple rebuild sites; not every omit path documented to terminal clamp (omit Pass B covered by test; other writers TBD)  
- Likelihood: **L2** | Severity: **S3**  
- Evidence: `air_script.py:build_vo_seats`, `vo_contract.py:ensure_hosted_framing_vo_seats`, `tests/test_delivery_thrash_hardening.py:test_omit_pass_b_clamp_active_count_bounded`  
- Fix-cluster: `seat-clamp-after-mutate`  
- Status: **OPEN_RISK**

---


---

### D-NCM-01 — nugget_corpus_mine tape mine
- Surface: stage | LLM  
- Modes: all  
- Call graph: `analysis_extended.run_nugget_corpus_mine` · OF-03a  
- Invariant: corpus grounded; no metadata in LLM packet  
- Why weak: weak corpus → layup invents gaps → G1 seat explosion  
- Likelihood: **L2** | Severity: **S2**  
- Evidence: `analysis_extended.py:run_nugget_corpus_mine`, `llm_interaction_registry.py` OF-03a  
- Fix-cluster: `layup-authority`  
- Status: **OPEN_RISK**

---


---

### D-IPP-01 — information_package_plan shadow mode
- Surface: stage  
- Modes: all  
- Call graph: `information_packages.run_information_package_plan` · cfg `mode` default `"shadow"`  
- Invariant: episode-close theme_outro required when enabled  
- Why weak: shadow vs enable mismatch → music epoch missing outro cue later  
- Likelihood: **L2** | Severity: **S2**  
- Evidence: `information_packages.py:information_packages_cfg`  
- Fix-cluster: `music-epoch-policy`  
- Status: **OPEN_RISK**

---


---

### D-NLC-01 — nugget_layup_compose authoritative gap (seats · VO/G1)
- Surface: stage | LLM  
- Modes: all  
- Call graph: `analysis_extended.run_nugget_layup_compose` · sanitary incompleteness  
- Invariant: gap_report authority for VO seats; no seed under `nugget_layup_authority` without sanitize  
- Why weak: layup rewrite → G1 open / adjudicate text change → WAV nuke  
- Likelihood: **L3** | Severity: **S3**  
- Evidence: `stage_completion.py` nugget_layup branch, `delivery_guardrails.py:seal_adjudicate_stale_when_g1_green`  
- Fix-cluster: `vo-g1-monotonic`  
- Status: **OPEN_RISK**

---


---

### D-GRS-01 — gap_report_sanitize seat/omit drift
- Surface: stage  
- Modes: all  
- Call graph: sanitize registry · `vo_synthesize` waits on `gap_unsanitary`  
- Invariant: gap sanitary before synth/EDL  
- Why weak: sanitize can omit without guaranteed clamp on every branch  
- Likelihood: **L2** | Severity: **S3**  
- Evidence: `stage_completion.py` gap_report_sanitize / vo_synthesize sanitary checks  
- Fix-cluster: `seat-clamp-after-mutate`  
- Status: **OPEN_RISK**

---


---

### D-RA-01 — refinement_agenda slim Pass-2
- Surface: stage  
- Modes: all  
- Call graph: `refinement_agenda.run_refinement_agenda(phase="confirm")`  
- Invariant: agenda-only; no no-op refine stages  
- Why weak: agenda can re-open framing recompose → seat churn  
- Likelihood: **L2** | Severity: **S2**  
- Evidence: `pipeline.py` DELIVERY registration, `refinement_agenda.py:run_refinement_agenda`  
- Fix-cluster: `refinement-slim`  
- Status: **OPEN_RISK**

---


---

### D-GFR-01 — gap_framing_recompose Pass-2 (seats)
- Surface: stage  
- Modes: Manual (operator framing sticky) | Full-auto | Partial  
- Call graph: `refinement_passes.run_gap_framing_recompose`  
- Invariant: must not expand G1 after WAVs rendered without clamp  
- Why weak: recompose changes line text → adjudicate purge  
- Likelihood: **L2** | Severity: **S3**  
- Evidence: `refinement_passes.py:run_gap_framing_recompose`  
- Fix-cluster: `vo-g1-monotonic`  
- Status: **OPEN_RISK**

---


---

### D-SFA-01 — selection_framing_apply order touch
- Surface: stage  
- Modes: all  
- Call graph: `run_selection_framing_apply` → selection mutation → freeze clear risk  
- Invariant: framing apply must not clear pair freeze mid-delivery without VO rewind policy  
- Likelihood: **L2** | Severity: **S3**  
- Evidence: `refinement_passes.py:run_selection_framing_apply`, `air_order_integrity.py:clear_transitions_pair_freeze`  
- Fix-cluster: `transitions-pair-freeze`  
- Status: **OPEN_RISK**

---


---

### D-ASS-01 — air_script_seams seat align (seats · VO/G1)
- Surface: stage  
- Modes: all  
- Call graph: `air_script.run_air_script_seams` → `vo_contract.align_*` / clamp  
- Invariant: R10c align gap + seats + omit; clamp when WAVs exist  
- Why weak: seams after assembly green still expand seats → `may_rewind_to_vo_synthesize`  
- Likelihood: **L2** | Severity: **S3**  
- Evidence: `vo_contract.py` align + clamp, `delivery_guardrails.py:may_rewind_to_vo_synthesize`  
- Fix-cluster: `vo-g1-monotonic`  
- Status: **OPEN_RISK**

---


---

### D-ACS-01 — air_contract_sanitize
- Surface: stage  
- Modes: all  
- Call graph: sanitize · blocks `vo_synthesize` when unsanitary  
- Invariant: air contract sanitary before synth  
- Likelihood: **L2** | Severity: **S2**  
- Evidence: `stage_completion.py` air_contract_sanitize / vo_synthesize  
- Fix-cluster: `sanitize-completeness`  
- Status: **OPEN_RISK**

---


---

### D-TRN-01 — transitions pair freeze stamp (transitions freeze)
- Surface: stage | LLM  
- Modes: all  
- Call graph: `selection.run_transitions` → LLM → `stamp_transitions_pair_freeze` **only if** G1 green/skipped  
- Prompt: `assembly/transitions.system.txt` · OF-04 · `master/transitions.json`  
- Invariant: first freeze stamps pair set; later pairs → deferred  
- Why weak: if G1 still open at transitions write, freeze deferred to `assembly.run_edl`; mid-window pair expansion unmarked  
- Manifestation: stamp after persist; prerepair may mutate selection  
- Heal: EDL stamp; `vo_synthesize_pair_incompleteness` ignores deferred when freeze+G1 green  
- Likelihood: **L2** | Severity: **S3**  
- Evidence: `selection.py:run_transitions` (~1043–1048), `transition_vo.py:stamp_transitions_pair_freeze`, `tests/test_delivery_thrash_hardening.py:test_pair_freeze_ignores_deferred_for_vo_incompleteness`  
- Fix-cluster: `transitions-pair-freeze`  
- Status: **LIKELY_MITIGATED_ON_HEAD** (core) / residual **OPEN_RISK** on pre-G1 stamp gap

---


---

### F1 — Empty artifacts bypass schema
- **L:** H · **S:** H · **Status:** OPEN_RISK
- `prompt_validation.validate_stage_artifacts`: `if not artifacts: return []` → `{}` never validated.
- Affects every schema-backed stage on empty envelopes / fail-open paths.


---

### F2 — Schema allows hollow required arrays
- **L:** H · **S:** H · **Status:** OPEN_RISK
- Empty `[]` validates for: `missing_framing.evaluations`, `gap_framing_compose.interviewer_lines`, `nugget_corpus_mine.nuggets`, `nugget_layup_compose.ordered_segment_ids/layups`, `vo_line_adjudicate.lines`, `transitions.transitions`, `narrative_arc_plan.chapters`, `topic_coverage_audit.topic_mappings`, `connector_seam_adjudicate.verdicts`, `content_context.topics`, `synthetic_framing_plan.lines` (with other required filled).
- Completeness/sufficiency may catch some later; schema gate alone does not.


---

### F3 — Ship stages: no schema / not in registry maps
- **L:** H · **S:** M · **Status:** OPEN_RISK
- `episode_meta_build`, `episode_cover_prompt_craft`: in `ALL_LLM_STAGES`, prompts exist, write `publish/episode_meta.json` / `publish/cover_prompt.json`, **missing** from `STAGE_ARTIFACT_SCHEMAS` / `STAGE_ARTIFACT_DISK_PATHS` / `STAGE_PRIMARY_IDS`.
- Cover path uses `run_prompt_envelope`×2 (not `run_llm_stage_simple`); no artifact schema verify.


---

### F4 — Registry primary-ID collisions
- **L:** H · **S:** M · **Status:** OPEN_RISK
- `OA-03`: `boundary_detection` overwritten by `boundary_topic_resplit`
- `OA-08`: `gap_framing_compose` overwritten by `optimal_questions`
- `OA-09`: `talking_points_compose` overwritten by `framing_posture_decide`
- Runtime still works via stage runners; catalog / `resolve_interaction_id` / CI completeness are wrong for losers.


---

### F5 — `gap_framing_compose` prompt asks for non-schema companion
- **L:** M · **S:** M · **Status:** OPEN_RISK (soft)
- Prompt requires `gap_framing_plan` inside artifacts; `gap_report.schema.json` does not define it (root `additionalProperties` open).
- Writer peels to `understanding/gap_framing_plan.json` — intentional companion, but prompt↔schema contract is split.


---

### F6 — Examples contradict schemas
- **L:** M · **S:** M · **Status:** OPEN_RISK
- Failures in: `edl-narrative-audit.examples.md`, `sound-design-plan-flow1.examples.md`, `content-brief-reanchor.examples.md` (missing required keys vs live schema).


---

### F7 — Conductor pack vs tape-only denylist
- **L:** H · **S:** M · **Status:** OPEN_RISK
- Prompt (`docs/prompts/homunculus/conductor/system.txt`): “never pack exists, stage_done, or run_meta”.
- `pack_conductor_context` injects `artifact_exists` + `stage_done` **without** `strip_forbidden_metadata`.
- Nested `pack_volley` does strip; conductor operational context does not. `artifact_exists` is not covered by current denylist substrings.


---

### F8 — Retries > 2 on major LLM entrypoints
- **L:** M · **S:** M · **Status:** OPEN_RISK
- `junction_snip_qa`: `max_attempts = 3` (feel/thought path).
- `connector_seam_adjudicate`: economy→standard→flagship ladder (up to 3 calls), `task_kind="advisory"`.
- Homunculus invoke cap is **3/identity** (separate from stage LLM attempt=2) — documented, but easy to confuse with “max 2 attempts”.


---

### F9 — `synthetic_framing_plan` outside interaction registry
- **L:** M · **S:** L · **Status:** OPEN_RISK
- In `ALL_LLM_STAGES` + schema + disk; **not** in `STAGE_PRIMARY_IDS`. Own retry loop `(1, 2)` — OK on retries.


---

### F10 — `sound_design_palettes` envelope ≠ disk document
- **L:** M · **S:** L · **Status:** NOTE / mild OPEN_RISK
- Schema is palettes envelope; persist **merges** into `understanding/sound_design_plan.json` (`STAGE_MERGE_DISK_PERSIST`). Writer keys differ from sole disk shape by design.


---

### F12 — Writer alias tolerance (meta)
- **L:** L · **S:** L · **Status:** OK
- `_persist_meta` accepts `title_suggestion` / `description_markdown` aliases; prompt asks `title` / `description`. Harmless remapping.

---

## Homunculus conductor ↔ `loop.py` / packer

| Surface | Behavior |
|---|---|
| Prompt | Fact-ID packing only; tape-only; bootstrap G0 / must-keep / source_card / KB lessons; starvation halt |
| `run_conductor` | Loads conductor system; injects `pack_conductor_context` blob into user turn |
| `pack_conductor_context` | **Includes** `stage_done`, `artifact_exists`, readiness, `legal_next_stages` — contradicts tape-only line |
| Nested LLM | `apply_pack_to_kwargs` → `pack_volley` → `strip_forbidden_metadata`; gap stages keep host packet + bootstrap merge |
| Cap | Conductor turns + **max 3 invokes/identity**; nested stage LLM still **2 attempts** via `llm_simple` |

---

## Compact stage → prompt → schema → artifact

Paths under `docs/prompts/` and `docs/cross-cutting/json-schemas/` (artifacts/ unless noted). Retries = stage attempt budget.

| stage | prompt | schema | artifact | retries | runner |
|---|---|---|---|---|---|
| speaker_roles | understanding/speaker-roles.system.txt | artifacts/speakers_artifact.schema.json | understanding/speakers.json | 2 | understanding→llm_simple |
| content_context | understanding/content-context.system.txt | content_brief_artifact.schema.json | understanding/content_brief.json | 2 | understanding→llm_simple |
| talking_poin

---
