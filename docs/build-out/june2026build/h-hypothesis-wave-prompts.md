# H-hypothesis wave build prompts (June 2026)

**Six** paste-ready **Cursor Agent commands** — **Command 0 (Wave 0 harness) first**, then Waves **A → E**. Each generates one consolidated, evidence-gated implementation plan. Later steps must reference promotion status and open gates from earlier docs.

**Output folder:** `docs/build-out/june2026build/`  
**Do not edit:** `.cursor/plans/h-hypothesis_plan_files_909fce9f.plan.md`

---

## Realistic success definition (copy into every generated doc)

The product goal is **not** literal zero-failure on arbitrary first upload. Target instead:

| # | Criterion | How verified |
|---|-----------|--------------|
| 1 | **No silent failure** | Every block/warn emits `gui_log.jsonl` + gate panel text + [troubleshooting.md](../../workflows/troubleshooting.md) row |
| 2 | **Always recoverable** | Operator can fix via G0/G1/G2, investigations, or `--from-stage` without re-ingest |
| 3 | **Scenario robustness** | [Scenario coverage matrix](#scenario-coverage-matrix) passes for affected waves |
| 4 | **Fail open** | Missing deps/signals **omit feature**, do not halt (except documented hard gates) |
| 5 | **Promote with evidence** | No default-on until [15-point checklist](#promote-with-evidence-checklist-15-points) passes |

**North star (final product):** listener-trustworthy mastered episodes — [podcast-quality-roadmap.md](../../cross-cutting/podcast-quality-roadmap.md), [evaluation-metrics.md](../../cross-cutting/evaluation-metrics.md), `tools/verify_master.py`, `tools/validate_narrative.py`.

---

## Promote-with-evidence checklist (15 points)

Copy into **every** generated wave doc. For **each hypothesis**, include subsection **Promotion gates** with pass/fail checkboxes — **≥1 Implementation todo per point**.

| # | Gate | Pass criteria |
|---|------|---------------|
| 1 | **Spike stability** | Winner stable listener-first **and** idea-first ([phase3-spike-framework.md](../../pipeline/value-analysis/phase3-spike-framework.md)); ±20% weight perturbation does not flip rank |
| 2 | **Mechanism** | MEC-A ≥ 3; MEC-D ≥ 3 with documented [fail-open](#fail-open-contract) behavior |
| 3 | **Fixture proof** | Spike JSON re-run via `tools/run_value_spike.py` ≥ baseline |
| 4 | **Automated tests** | `pytest` green for touched modules |
| 5 | **Schema / artifact** | json-schemas + codegen + [artifact-layout.md](../../cross-cutting/artifact-layout.md) if I/O changes |
| 6 | **Config documented** | [config-keys.md](../../cross-cutting/config-keys.md) + `app.defaults.json` + templates |
| 7 | **Volley parity** | [context-padding.md](../../cross-cutting/context-padding.md) ↔ `STAGE_PLANS`; `python tools/audit_stage_plans_doc.py` |
| 8 | **Operator surface** | [gui-surface-map.md](../../workflows/gui-surface-map.md), [operator-stage-checklists.md](../../workflows/operator-stage-checklists.md), [operator-gates.md](../../workflows/operator-gates.md) |
| 9 | **Final product link** | Named Flow + validator (`master.wav`, retell, narrative QC, hook montage) |
| 10 | **Doc maintenance** | [doc-maintenance.md](../doc-maintenance.md) checklist |
| 11 | **Do-not-promote-until** | Explicit blockers listed |
| 12 | **Observability** | `ctx.log()` event shape; `gui_log.jsonl` key; gate panel copy; troubleshooting row added/verified |
| 13 | **Scenario matrix** | Applicable atlas/sonic fixtures pass ([matrix below](#scenario-coverage-matrix)) |
| 14 | **Fail-open** | Documented behavior when WAV/transcript/CLAP/NISQA/specialist missing; no undeclared `SystemExit` |
| 15 | **Recovery** | Named gate or `--from-stage <stage>` path documented; no dead-end without operator action |

**Kill / park:** prompt-only evidence channels; confidence-only G0 as primary; Wave E until spike-results deferred row updates.

---

## Status ladder

| Status | Config default | Evidence bar |
|--------|----------------|--------------|
| **Parked** | `false` / absent | Research only |
| **Partial** | often `true`, weak | Fixture + tests; scenario matrix **recommended** |
| **Promoted** | flag exists | All 15 points for that hypothesis |
| **Shipped default-on** | `true` in `app.defaults.json` | 15 points + smoke + nine-scenario listen subset |

Waves **A–D:** Partial → Promoted → Shipped. Wave **E:** Parked until unpark gates only.

---

## Scenario coverage matrix (required in Wave 0 + every wave doc)

Generated plans must include a **Scenario regression** section mapping atlas buckets to fixtures and waves. Pass = no regression vs atlas **failure mode recovery** tables ([interview-scenario-atlas.md](../../prompts/_shared/interview-scenario-atlas.md)).

| Atlas bucket | Fixture | Primary waves | Must not regress |
|--------------|---------|---------------|------------------|
| `one_on_one` | `tests/fixtures/sonic_context/one_on_one.json` | All | Baseline G0 + ranking + sparse sound |
| `panel` | `tests/fixtures/sonic_context/panel.json` | A, B | Speaker collapse; overlap mud mix |
| `noisy_room` | `tests/fixtures/sonic_context/noisy_room.json` | A, D | False trust dips; false emphasis; beds under speech |
| `trauma_adjacent` | `tests/fixtures/sonic_context/trauma_adjacent.json` | C, D | Cold open on peak; stingers on trauma segments |
| `dense_jargon` | `tests/fixtures/sonic_context/dense_jargon.json` | A, D | Comprehension false positives |
| `fireside` | `tests/fixtures/sonic_context/fireside.json` | B, D | Over-segmentation; over-bridging |
| `technical_deep_dive` | `tests/fixtures/sonic_context/technical_deep_dive.json` | B, C | Long-run coherence noise on short runs |
| `media_profile` | `tests/fixtures/sonic_context/media_profile.json` | D | Hook montage flat; hype show notes |
| `debate` | `tests/fixtures/sonic_context/debate.json` | A, B | Role swap; crosstalk boundaries |
| Long interview | `tests/fixtures/runs/coherence_30m_planted_drift/` | C | ORC-03 only when ≥30m; no spam on short |
| **Prosody diversity** (cross-cutting) | Manual CRE-B clips + rubric | A | See [Prosody & delivery diversity](#prosody--delivery-diversity-cross-cutting) |

**Nine-scenario listen matrix:** [definition-of-done-signoff.md](../definition-of-done-signoff.md) §6 — Wave D promotion should reference spot-check before Shipped.

---

## Prosody & delivery diversity (cross-cutting)

Speech impediment, stutter, heavy accent, quiet delivery, and high disfluency are **not** separate atlas buckets today. Every wave doc must include subsection **Prosody & delivery guardrails**:

| Risk | Mitigation in plans |
|------|---------------------|
| Low volume / quiet speech | H-F1N-02 emphasis must **surface** quiet vital claims, not skip them; H-ING-03 RMS dips must not auto-flag quiet thoughtful speech without corroboration |
| Irregular pauses | H-SEG-02 ladder must not over-split reflective speakers; align with SAP `pace_class` |
| High disfluency | Align with [disfluency-extract.md](../../pipeline/transcription/disfluency-extract.md) + [transcript-quality-rubric.md](../../prompts/_shared/transcript-quality-rubric.md) — fillers ≠ comprehension gaps by default |
| Accent / ASR unevenness | H-G0-01 salience must not **purely** punish low confidence; require H-G0-02 stress corroboration or idea-break text signal ([value-metrics-library.md](../../pipeline/value-analysis/value-metrics-library.md) accent bias warning) |
| Atypical prosody | Down-rank review/investigate signals, never **exclude** analysis; fail-open |

**Promotion gate:** Before Promoted → Shipped on Wave A proxies, document manual or fixture-backed check on ≥2 “hard listener” clips (quiet, disfluent, or noisy) per [transcript-quality-rubric.md](../../prompts/_shared/transcript-quality-rubric.md).

---

## Fail-open contract (required per hypothesis)

Every hypothesis section must document:

| Condition | Required behavior |
|-----------|-------------------|
| Missing `ingest/normalized.wav` | Skip audio-derived signals; log `value_analysis_skip_no_wav` |
| Missing CLAP / MMAudio venv | Spine ships; `retrieval.enabled: false` ([interview-spine.md](../../cross-cutting/interview-spine.md)) |
| `value_analysis.enabled: false` | No investigations from extract; stages unchanged |
| Specialist failure / timeout | Gap stage continues; log specialist skip |
| Coherence below 30m | No coherence risks; stub topic_shift suppressed if configured |
| Low-confidence acoustic signal | Omit flag; do not enqueue investigation |

**Hard gates (allowed to stop):** `analysis.flow_hardening` cross-artifact checks, blocking `claim_contradiction`, G0/G1/G2 operator gates, `verify_master` / narrative QC at ship — each must cite [troubleshooting.md](../../workflows/troubleshooting.md).

---

## Per-wave do-no-harm rules (copy into each wave doc)

| Wave | Risk if promoted carelessly | Guardrails |
|------|----------------------------|------------|
| **0** | Over-gating blocks all runs | Hardening on; operator gates preserved; fail-open inventory complete |
| **A** | Bad G0 order; false trust dips on noisy_room | A/B vs confidence-only; cap flags; scenario matrix noisy_room + prosody checks |
| **B** | Over-segmentation; spine/CLAP break installs | Boundary-truth tests; CLAP fail-open; ladder/spine dedupe |
| **C** | Investigation loops; false contradictions block ship | `flow_hardening` budgets; 30m gate; blocking threshold high-confidence only |
| **D** | Stingers on laughter; trauma violations; flat montage | placement QA; trauma_adjacent examples; highlight diversity |
| **E** | Heavy deps break core venv | Stay parked; isolated research venv; never block A–D |

---

## Repository harness map

Include applicable rows in each generated **Repository touch matrix**:

| Layer | Paths / docs |
|-------|----------------|
| Pipeline | `pipeline.py`, [stage-registry.md](../stage-registry.md) |
| Volley | `context_volley.py`, [context-padding.md](../../cross-cutting/context-padding.md), [analysis-memory.md](../../cross-cutting/analysis-memory.md) |
| LLM hardening | `llm_flow_hardening.py`, `llm_preflight.py`, `artifact_cross_validate.py`, [LLM-ANALYSIS-ARCHITECTURE.md](../../LLM-ANALYSIS-ARCHITECTURE.md) §18–20 |
| Orchestration | `journey_orchestrator.py`, [analysis-orchestration-loop.md](../../workflows/analysis-orchestration-loop.md) |
| Value analysis | `stage_enrichment.py`, `value_analysis/extract.py` |
| Spine / coherence | `interview_spine/*`, `coherence/*` |
| Scenario / sonic | [interview-scenario-atlas.md](../../prompts/_shared/interview-scenario-atlas.md), `sonic_context.py`, [sonic-context.md](../../cross-cutting/sonic-context.md) |
| Acoustic adapt | `acoustic_profile.py`, [source-derived-sonic-mix-profile.md](../../cross-cutting/source-derived-sonic-mix-profile.md) |
| Observability | `gui_log.jsonl`, [troubleshooting.md](../../workflows/troubleshooting.md), [operator-journey.md](../../workflows/operator-journey.md) |
| QA / ship | `verify_master.py`, `validate_narrative.py`, [smoke-test.md](../../workflows/smoke-test.md) |
| Config | [config-keys.md](../../cross-cutting/config-keys.md) |

---

## Todo thoroughness rule

- **No cap** on todos. Target **60–120+ per wave doc**; **45+ per hypothesis** (Waves A–D).
- Include **all 15 promotion gate** items as explicit todos.
- Include **scenario matrix** row verification todos.
- Include **fail-open** test todos per signal path.
- Include **observability** todos (`ctx.log`, troubleshooting row, checklist row).

---

## Canonical references

| Doc | Use |
|-----|-----|
| [interview-scenario-atlas.md](../../prompts/_shared/interview-scenario-atlas.md) | Format/tone/recovery |
| [transcript-quality-rubric.md](../../prompts/_shared/transcript-quality-rubric.md) | G0 + prosody |
| [spike-results-and-winners.md](../../pipeline/value-analysis/spike-results-and-winners.md) | Promote/park/kill |
| [phase3-spike-framework.md](../../pipeline/value-analysis/phase3-spike-framework.md) | Rubrics |
| [coherence-orc03.md](../../cross-cutting/coherence-orc03.md) | ORC-03 template |
| [doc-maintenance.md](../doc-maintenance.md) | PR obligations |

---

## Command overview

| Cmd | Output | When |
|-----|--------|------|
| **0** | `wave-0-resilience-harness.md` | **First** — before any hypothesis code plans |
| 1 | `wave-a-early-truth.md` | After Wave 0 gates documented |
| 2 | `wave-b-audio-structure.md` | After Wave A promotion gates or documented exceptions |
| 3 | `wave-c-self-healing.md` | After Wave B |
| 4 | `wave-d-output-resilience.md` | After Wave C |
| 5 | `wave-e-big-bets.md` | Last — parked only |

---

## Command 0 — Wave 0: Resilience harness (run first)

Paste into a **new Cursor Agent chat**:

```
Create docs/build-out/june2026build/wave-0-resilience-harness.md — the cross-cutting application resilience plan. Read the repo exhaustively. Real paths only. Single file. Do NOT edit .cursor/plans/*. Documentation only — no Python changes.

## Purpose

Wave 0 documents guardrails that apply BEFORE and ACROSS hypothesis waves A–E so the system:
- Stops at named gates with gui_log + troubleshooting guidance (not silent wrong output)
- Recovers via operator gates and --from-stage
- Handles diverse interview scenarios via scenario atlas + sonic_context
- Fail-opens when optional signals/deps are missing

No H-hypothesis feature work should ship until Wave 0 Implementation todos for applicable rows are addressed or explicitly waived with rationale.

## Required sections

1. **Realistic success definition** — copy from h-hypothesis-wave-prompts.md (5 criteria)
2. **15-point promote-with-evidence checklist** — full table
3. **Scenario coverage matrix** — all atlas buckets + sonic fixtures + coherence 30m fixture + prosody diversity row
4. **Prosody & delivery guardrails** — full subsection
5. **Fail-open inventory** — table per subsystem:
   - interview_spine / CLAP
   - value_analysis / stage_enrichment
   - coherence (duration gate)
   - llm_specialists
   - sonic_context_build
   - source_acoustic_profile
   - audio_preclean (never auto — BUILD-072)
6. **Observability contract**
   - gui_log.jsonl event naming conventions
   - Gate panel messages for G0, G1, G2, flow_hardening, investigation, coherence
   - Map each hard stop to troubleshooting.md row (extend table if gap)
   - ctx.log() requirements for new operator-facing strings
7. **LLM flow hardening audit**
   - analysis.flow_hardening.* keys from config-keys.md
   - preflight, cross_validate, attempt_budget, arbiter path
   - When enabled=false is allowed (dev only — document risk)
8. **Operator gates audit** — G0 transcript, disfluency_review, G1 VO, G2 ship, profile gate BUILD-081, quality offers BUILD-072
9. **Scenario atlas integration**
   - How content_context sets format_class / tone_class
   - sonic_context atlas_bucket → sound_posture → sound_design plans
   - placement_adjustments scenario_override schema
10. **Deterministic QC chain** — narrative_qc, validate_edl, verify_master, placement_qa, show_description_qc — when each runs; what operator sees on fail
11. **Cross-artifact validation** — artifact_cross_validate.py; relationship to flow_hardening
12. **Wave blocking rules** — Wave A may start after Wave 0 doc exists; B after A; etc.
13. **Repository touch matrix** — full harness map from prompts doc
14. **Implementation todos** — minimum 80 checkboxes covering:
    - Every fail-open path verification
    - Every troubleshooting gap filled
    - Every scenario fixture linked to a test or manual sign-off procedure
    - audit_stage_plans_doc.py in CI checklist
    - definition-of-done nine-scenario matrix procedure
    - disfluency + transcript-quality-rubric alignment
    - No new default-on flags without 15-point checklist template
15. **Promotion gate for Wave A** — Wave A hypothesis implementation must not begin until Wave 0 todos marked complete OR waived with signed rationale table

Target 500–900 lines. Unlimited todos.
```

---

## Command 1 — Wave A: Early truth

```
Create docs/build-out/june2026build/wave-a-early-truth.md (seq 01–04). Read repo. Single file. Docs only. Do NOT edit .cursor/plans/*.

## Requires Wave 0

wave-0-resilience-harness.md must exist. Reference its fail-open inventory, observability contract, and scenario matrix. Wave B blocked until Wave A promotion gates pass or documented exceptions.

## Hypotheses

| Seq | ID | Status | Spike | Tier |
|-----|-----|--------|-------|------|
| 01 | H-ING-03 | partial RMS proxy | 3.738 | T0 |
| 02 | H-G0-02 | partial | — | T1 |
| 03 | H-G0-01 | partial | 4.037 | T0 |
| 04 | H-GAP-01 | partial specialist | 4.037 | T0 |

## Wave A do-no-harm

False trust dips on noisy_room; salience punishing accent/low confidence; comprehension specialist blocking gaps loop — document mitigations + scenario tests.

## Required wave-level sections

1. Realistic success definition + 15-point checklist + scenario matrix (rows: noisy_room, panel, debate, dense_jargon, prosody diversity)
2. Prosody & delivery guardrails — per-hypothesis application
3. Fail-open per H-ING-03, H-G0-01, H-GAP-01
4. Observability: ctx.log events for queue mode, trust flags, comprehension_risk threshold; troubleshooting rows
5. Mermaid: ingest → G0 → value_features → missing_framing
6. Wave A promotion gate for Wave B (3 bullets from prior doc + scenario matrix pass)
7. Final product impact — transcript → content_brief → master chain

## Per-hypothesis (×4) — each includes sections A–R from prior spec PLUS:

### S. Fail-open table (hypothesis-specific)
### T. Observability & recovery (log keys, gate, --from-stage)
### U. Scenario regression (which matrix rows apply; pass criteria)
### V. Prosody guardrails (hypothesis-specific)
### W. Promotion gates — all **15 points** with pass criteria
### X. Implementation todos — **minimum 50 per hypothesis** including 15 gate todos + scenario + fail-open + observability

## Code anchors

H-ING-03: stage_enrichment.py quality_trajectory_flags; boundaries.py; value_analysis/*; sonic_context.py; spike_shared_ingest_transcribe.json

H-G0-02: transcript_review.py _acoustic_stress_score; audio_energy.py

H-G0-01: communicative_salience_score; transcript_review sort; spike_shared_g0_and_profile.json; transcript-review.md

H-GAP-01: llm_specialists comprehension_risk_blind; gaps.py; flow_hardening; context_volley; spike_shared_gaps_and_vo.json

## Wave todos (40+)

Link wave-0 doc; update section value maps; smoke-test G0; future-proofing table; INDEX.md

Target 500–900 lines. Unlimited todos.
```

---

## Command 2 — Wave B: Audio structure

```
Create docs/build-out/june2026build/wave-b-audio-structure.md (seq 05–06). Requires wave-0 + wave-a docs. Docs only.

## Hypotheses

| Seq | ID | Status | Spike |
|-----|-----|--------|-------|
| 05 | H-SEG-02 | partial word-gap ladder | 4.033 |
| 06 | H-ORC-01 | shipped harden | — |

## Wave B do-no-harm

Over-segmentation (fireside, prosody); spine without CLAP breaking; ladder/spine drift

## Required sections

1. Full global framework (15-point, scenario matrix rows: one_on_one, fireside, panel, debate, technical_deep_dive)
2. Prosody: irregular pauses vs pause ladder; SAP pace_class integration
3. Fail-open: CLAP missing; ssl_enabled false; spine rebuild skip when derived_from match
4. Observability: recompute-interview-spine API errors logged; boundary_detection volley truncation flags
5. Mermaid: pause_ladder → boundary_detection → interview_spine_build → consumers
6. Wave C promotion gate
7. H-SEG-02 + H-ORC-01 full sections (50+ todos each, 15 gate points each)
8. Consumer audit list for ORC-01 (context_volley, theme_evidence, framer, flow2 quotability, SAP prosody)

Scenario: panel.json speaker boundaries; fireside over-split; technical_deep_dive long segments

Target 500–950 lines. Unlimited todos.
```

---

## Command 3 — Wave C: Self-healing

```
Create docs/build-out/june2026build/wave-c-self-healing.md (seq 07–08). Requires wave-0, wave-a, wave-b. Docs only.

## Hypotheses (shipped — HARDEN)

| Seq | ID | Spike | Artifact |
|-----|-----|-------|----------|
| 07 | H-ORC-02 | 4.071 | investigation_queue.json |
| 08 | H-ORC-03 | promote | coherence_report.json |

## Wave C do-no-harm

Investigation loops (flow_hardening budgets); false contradictions blocking analysis_ready; coherence spam on short interviews

## Required sections

1. 15-point checklist + scenario rows: technical_deep_dive, coherence_30m_planted_drift, trauma_adjacent (blocking contradictions)
2. Orthogonality: ORC-02 trust dip vs ORC-03 topic_drift
3. Fail-open: investigations cap; coherence duration gate; novelty CLAP fallback
4. Observability: investigation_queue writes logged; journey_orchestrator block reasons; CoherenceRisksPanel empty state
5. Rate limits: coherence.max_investigations_per_run; flow_hardening attempt_budget — config todos
6. Mermaid dual path orchestration + coherence hooks
7. H-ORC-02 (55+ todos) + H-ORC-03 (60+ todos)
8. troubleshooting.md investigation loop section aligned

Wave D gate: dedupe tested; 30m fixture CI; volley parity audit

Target 550–1000 lines. Unlimited todos.
```

---

## Command 4 — Wave D: Output resilience

```
Create docs/build-out/june2026build/wave-d-output-resilience.md (seq 09–11). Requires waves 0–C. Docs only.

## Hypotheses

| Seq | ID | Spike | Product tie |
|-----|-----|-------|-------------|
| 09 | H-F1N-02 | 4.037 | ranking → EDL → mix_flow1 |
| 10 | H-F2-02 | 3.971 | mix_flow2 montage |
| 11 | H-F1S-02 | — | sting intelligibility |

## Wave D do-no-harm

Stingers on laughter; trauma_adjacent cold open; flat highlight montage; emphasis false positives on noisy_room

## Required sections

1. 15-point checklist + **all nine sonic fixtures** + definition-of-done §6 listen matrix procedure
2. Prosody: quiet emphasis (F1N-02); paralinguistic proxy limits (F2-02)
3. Fail-open: laughter_windows empty → placement unchanged; quotability without spine boost
4. Observability: narrative_qc failures; placement_qa warnings; verify_master LUFS fail messages
5. Pipeline mermaid through mix_flow1/2 + placement_qa + verify_master
6. Non-H deps: source_acoustic_profile, sonic_context, sdp_craft_path — integration todos
7. H-F1N-02, H-F2-02, H-F1S-02 — 50+ todos each; trauma_adjacent + noisy_room scenario tests required

Final product: COM retell, hook first-3s, LEX-B after mix

Target 550–1000 lines. Unlimited todos.
```

---

## Command 5 — Wave E: Big bets (parked)

```
Create docs/build-out/june2026build/wave-e-big-bets.md (seq 12–15). Requires wave-0 doc. Docs only.

## CRITICAL: Parked — unpark gates only, never default-on with A–D

## Hypotheses

H-ING-02, H-ING-04, H-ING-01, H-SEG-01 — all Parked

## Required sections

1. 15-point checklist adapted to **unpark** language (all 15 must pass BEFORE config true)
2. Shared unpark gates: Command 8; pip-audit; listener study; spike-results deferred row; no core torch
3. Prosody: accent/multitrack research must document bias mitigation ([value-metrics-library.md](../../pipeline/value-analysis/value-metrics-library.md))
4. Fail-open: research flags only; production path unchanged when parked
5. Wave E must NOT block Waves A–D (explicit)
6. Per-hypothesis 55+ todos including ≥8 unpark gates each + kill criteria
7. Sequential: ING-02 → ING-04 → ING-01 → SEG-01

Scenario matrix: document which buckets each unpark would help (no implementation until unparked)

Target 600–1100 lines. Unlimited todos.
```

---

## After all six commands

1. Verify each doc: **15-point checklist**, **scenario matrix**, **fail-open**, **observability**, **prosody guardrails**, **do-no-harm**, **50–120+ todos**.
2. Update [README.md](./README.md) with Wave 0 + A–E links.
3. Implementation order: **0 → A → B → C → D → E**; never flip defaults without point 15 recovery path tested.
4. Run smoke-test + validate_narrative + verify_master after each wave code PR.
5. Wave E: never default-on without human promote + spike-results row.

---

## Final product quality (include in every generated doc)

| Flow | Artifact | Validator |
|------|----------|-----------|
| Flow 1 | `master_flow1/master.wav` | verify_master, validate_narrative, assembly preview listen |
| Flow 2 | `master_flow2/master.wav` | Hook listen + diversity |
| Flow 3 | show description | show_description_qc, CRE-C |
| Analysis | analysis_ready | G1/G2, coherence blocking |

Partial proxies remain **Partial** until prosody scenario checks + listener/operator study clear **do-not-promote-until**.

---

## Related

Prior per-hypothesis drafts under `docs/build-out/hypothesis-plans/` (if any) are reference only. June 2026 = **Wave 0 harness + five evidence-gated wave documents**.
