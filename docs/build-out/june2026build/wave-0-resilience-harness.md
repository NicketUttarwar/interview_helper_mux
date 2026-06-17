# Wave 0 — Resilience harness (June 2026)

**Status:** Planning doc — must exist and pass promotion gate before any H-hypothesis code work (Waves A–E).  
**Parent:** [h-hypothesis-wave-prompts.md](./h-hypothesis-wave-prompts.md) Command 0  
**Do not edit:** `.cursor/plans/h-hypothesis_plan_files_909fce9f.plan.md`

Wave 0 documents cross-cutting guardrails that apply **before and across** hypothesis waves A–E. No H-hypothesis feature should ship until applicable Wave 0 Implementation todos are addressed or explicitly waived with rationale.

**Canonical references:** [operator-gates.md](../../workflows/operator-gates.md) · [troubleshooting.md](../../workflows/troubleshooting.md) · [config-keys.md](../../cross-cutting/config-keys.md) · [stage-registry.md](../stage-registry.md) · [interview-scenario-atlas.md](../../prompts/_shared/interview-scenario-atlas.md)

---

## 1. Realistic success definition

The product goal is **not** literal zero-failure on arbitrary first upload. Target instead:

| # | Criterion | How verified |
|---|-----------|--------------|
| 1 | **No silent failure** | Every block/warn emits `gui_log.jsonl` + gate panel text + [troubleshooting.md](../../workflows/troubleshooting.md) row |
| 2 | **Always recoverable** | Operator can fix via G0/G1/G2, investigations, or `--from-stage` without re-ingest |
| 3 | **Scenario robustness** | [Scenario coverage matrix](#3-scenario-coverage-matrix) passes for affected waves |
| 4 | **Fail open** | Missing deps/signals **omit feature**, do not halt (except documented hard gates) |
| 5 | **Promote with evidence** | No default-on until [15-point checklist](#2-promote-with-evidence-checklist-15-points) passes |

**North star (final product):** listener-trustworthy mastered episodes — [podcast-quality-roadmap.md](../../cross-cutting/podcast-quality-roadmap.md), [evaluation-metrics.md](../../cross-cutting/evaluation-metrics.md), `tools/verify_master.py`, `tools/validate_narrative.py`.

---

## 2. Promote-with-evidence checklist (15 points)

Copy into **every** generated wave doc. For **each hypothesis**, include subsection **Promotion gates** with pass/fail checkboxes — **≥1 Implementation todo per point**.

| # | Gate | Pass criteria |
|---|------|---------------|
| 1 | **Spike stability** | Winner stable listener-first **and** idea-first ([phase3-spike-framework.md](../../pipeline/value-analysis/phase3-spike-framework.md)); ±20% weight perturbation does not flip rank |
| 2 | **Mechanism** | MEC-A ≥ 3; MEC-D ≥ 3 with documented [fail-open](#5-fail-open-inventory-per-subsystem) behavior |
| 3 | **Fixture proof** | Spike JSON re-run via `tools/run_value_spike.py` ≥ baseline |
| 4 | **Automated tests** | `pytest` green for touched modules |
| 5 | **Schema / artifact** | json-schemas + codegen + [artifact-layout.md](../../cross-cutting/artifact-layout.md) if I/O changes |
| 6 | **Config documented** | [config-keys.md](../../cross-cutting/config-keys.md) + `config/app.defaults.json` + `config/templates/secrets.env.example` |
| 7 | **Volley parity** | [context-padding.md](../../cross-cutting/context-padding.md) ↔ `STAGE_PLANS` in `src/interview_mux/context_volley.py`; `python tools/audit_stage_plans_doc.py` |
| 8 | **Operator surface** | [gui-surface-map.md](../../workflows/gui-surface-map.md), [operator-stage-checklists.md](../../workflows/operator-stage-checklists.md), [operator-gates.md](../../workflows/operator-gates.md) |
| 9 | **Final product link** | Named Flow + validator (`master.wav`, retell, narrative QC, hook montage) |
| 10 | **Doc maintenance** | [doc-maintenance.md](../doc-maintenance.md) checklist |
| 11 | **Do-not-promote-until** | Explicit blockers listed |
| 12 | **Observability** | `ctx.log()` event shape; `gui_log.jsonl` key; gate panel copy; troubleshooting row added/verified |
| 13 | **Scenario matrix** | Applicable atlas/sonic fixtures pass ([matrix below](#3-scenario-coverage-matrix)) |
| 14 | **Fail-open** | Documented behavior when WAV/transcript/CLAP/NISQA/specialist missing; no undeclared `SystemExit` |
| 15 | **Recovery** | Named gate or `--from-stage <stage>` path documented; no dead-end without operator action |

**Kill / park:** prompt-only evidence channels; confidence-only G0 as primary; Wave E until [spike-results-and-winners.md](../../pipeline/value-analysis/spike-results-and-winners.md) deferred row updates.

**Status ladder:**

| Status | Config default | Evidence bar |
|--------|----------------|--------------|
| **Parked** | `false` / absent | Research only |
| **Partial** | often `true`, weak | Fixture + tests; scenario matrix **recommended** |
| **Promoted** | flag exists | All 15 points for that hypothesis |
| **Shipped default-on** | `true` in `app.defaults.json` | 15 points + smoke + nine-scenario listen subset |

---

## 3. Scenario coverage matrix

Pass = no regression vs atlas **failure mode recovery** tables in [interview-scenario-atlas.md](../../prompts/_shared/interview-scenario-atlas.md).

| Atlas bucket | Fixture | Primary waves | Must not regress | Test / sign-off |
|--------------|---------|---------------|------------------|-----------------|
| `one_on_one` | `tests/fixtures/sonic_context/one_on_one.json` | All | Baseline G0 + ranking + sparse sound | `tests/test_sonic_context.py` |
| `panel` | `tests/fixtures/sonic_context/panel.json` | A, B | Speaker collapse; overlap mud mix | `tests/test_sound_design_scenario.py` |
| `noisy_room` | `tests/fixtures/sonic_context/noisy_room.json` | A, D | False trust dips; false emphasis; beds under speech | `tests/test_mix_acoustic_profile.py` |
| `trauma_adjacent` | `tests/fixtures/sonic_context/trauma_adjacent.json` | C, D | Cold open on peak; stingers on trauma segments | `tests/test_sfx_mmaudio.py` (trauma skip refine) |
| `dense_jargon` | `tests/fixtures/sonic_context/dense_jargon.json` | A, D | Comprehension false positives | `tests/test_sonic_context.py` |
| `fireside` | `tests/fixtures/sonic_context/fireside.json` | B, D | Over-segmentation; over-bridging | Manual boundary spot-check |
| `technical_deep_dive` | `tests/fixtures/sonic_context/technical_deep_dive.json` | B, C | Long-run coherence noise on short runs | `tests/test_coherence_duration_gate.py` |
| `media_profile` | `tests/fixtures/sonic_context/media_profile.json` | D | Hook montage flat; hype show notes | `tests/test_flow2_crossfade.py` |
| `debate` | `tests/fixtures/sonic_context/debate.json` | A, B | Role swap; crosstalk boundaries | `tests/test_style_inference.py` |
| Long interview | `tests/fixtures/runs/coherence_30m_planted_drift/` | C | ORC-03 only when ≥30m; no spam on short | `tests/test_coherence_fixture_planted.py` |
| **Prosody diversity** (cross-cutting) | Manual CRE-B clips + [transcript-quality-rubric.md](../../prompts/_shared/transcript-quality-rubric.md) | A | See [§4](#4-prosody--delivery-guardrails) | Manual ≥2 hard-listener clips |

**Nine-scenario listen matrix:** [definition-of-done-signoff.md](../definition-of-done-signoff.md) §6 — Wave D promotion should reference spot-check before Shipped.

**Fixture validation command:**

```bash
source .venv/bin/activate
pytest tests/test_sonic_context.py tests/test_coherence_duration_gate.py tests/test_coherence_fixture_planted.py -q
```

---

## 4. Prosody & delivery guardrails

Speech impediment, stutter, heavy accent, quiet delivery, and high disfluency are **not** separate atlas buckets today. Every wave doc must include this subsection.

| Risk | Mitigation in plans | Code / doc anchors |
|------|---------------------|-------------------|
| Low volume / quiet speech | H-F1N-02 emphasis must **surface** quiet vital claims, not skip them; H-ING-03 RMS dips must not auto-flag quiet thoughtful speech without corroboration | `src/interview_mux/stage_enrichment.py` (`emphasis_regions_for_segments`, `quality_trajectory_flags`) |
| Irregular pauses | H-SEG-02 ladder must not over-split reflective speakers; align with SAP `pace_class` | `stage_enrichment.pause_ladder_hints`, `understanding/source_acoustic_profile.json` |
| High disfluency | Align with [disfluency-extract.md](../../pipeline/transcription/disfluency-extract.md) + [transcript-quality-rubric.md](../../prompts/_shared/transcript-quality-rubric.md) — fillers ≠ comprehension gaps by default | `disfluency_catalog` in `context_volley.py` |
| Accent / ASR unevenness | H-G0-01 salience must not **purely** punish low confidence; require H-G0-02 stress corroboration or idea-break text signal | [value-metrics-library.md](../../pipeline/value-analysis/value-metrics-library.md) accent bias warning |
| Atypical prosody | Down-rank review/investigate signals, never **exclude** analysis; fail-open | `energy_windows_from_path` returns `None` → empty flags in `stage_enrichment.py` |

**Promotion gate:** Before Promoted → Shipped on Wave A proxies, document manual or fixture-backed check on ≥2 “hard listener” clips (quiet, disfluent, or noisy) per [transcript-quality-rubric.md](../../prompts/_shared/transcript-quality-rubric.md).

**Disfluency alignment checklist:**

- G0.5 confirmed fillers flow into volley as `disfluency_catalog` — not as `missing_framing` gaps by default.
- `transcript_quality.flagged_chunks` (G0) and disfluency events (G0.5) are distinct signals in `context_volley.py`.
- Restore phase optional — [disfluency-restore.md](../../pipeline/assembly_and_mux/disfluency-restore.md); never blocks analysis.

---

## 5. Fail-open inventory per subsystem

| Subsystem | Module / stage | Missing / failure condition | Required behavior | Hard stop? | Log event / `stage` |
|-----------|----------------|----------------------------|-------------------|------------|---------------------|
| **interview_spine / CLAP** | `src/interview_mux/stages/interview_spine_stage.py`, `interview_spine/clap_index.py` | MMAudio venv missing, CLAP subprocess fail, `clap_enabled: false` | Spine ships with `retrieval.enabled: false`; no `embeddings.npz` | No (spine still required when enabled) | `CLAP retrieval unavailable; spine written without embeddings.` · `stage=interview_spine_build` |
| **interview_spine / CLAP** | `interview_spine/config.py` | `interview_spine.enabled: false` | Stage marks done; no artifact | No | `Interview spine disabled in config.` |
| **interview_spine / prosody** | `interview_spine/features.py` | librosa pyin unavailable | Windows ship without F0; DSP RMS still populated | No | (silent omit) |
| **value_analysis / stage_enrichment** | `value_analysis/extract.py`, `stage_enrichment.py` | `value_analysis.enabled: false` | No investigations from extract; stages unchanged | No | (no enqueue) |
| **value_analysis / stage_enrichment** | `stage_enrichment.py` | Missing `ingest/normalized.wav` | `energy_windows_from_path` → `None`; emphasis/quotability/trust-dip lists empty | No | Document as `value_analysis_skip_no_wav` in wave A todos |
| **value_analysis / stage_enrichment** | `value_analysis/features_audio.py` | Audio profile requested but no WAV | `FileNotFoundError` only when `--profile audio` explicitly invoked via CLI tools | Partial | Use transcript-only path in production extract |
| **coherence duration gate** | `coherence/duration_gate.py`, `coherence/analyze.py` | Interview &lt; `coherence.min_duration_ms` (default 1_800_000 = 30m) | No coherence risks; stub `topic_shift` suppressed when `replace_stub_topic_shift_hints: true` | No | `coherence_activated: false` in report gate block |
| **coherence duration gate** | `coherence/claim_contradiction.py` | Below threshold confidence | Risk omitted from blocking set | No | — |
| **coherence duration gate** | `coherence/claim_contradiction.py` | `blocking_claim_contradiction` + high confidence | Blocks `analysis_ready` | **Yes** | Cross-artifact `post_coherence` |
| **llm_specialists** | `llm_specialists.py` | `analysis.specialists.enabled: false` | Specialists skipped entirely | No | — |
| **llm_specialists** | `llm_specialists.py` | Specialist timeout / API error (post-stage) | Gap stage continues; log warning | No | `Specialist {key} failed: {exc}` |
| **llm_specialists** | `llm_specialists.py` | Pre-stage `comprehension_risk_blind` fail + hardening on | Enqueues investigation; parent may still run | Soft | `Pre-stage specialist … failed` |
| **sonic_context_build** | `stages/sonic_context_stages.py`, `sonic_context.py` | Sparse upstream (no manifest) | Best-effort bucket from `analysis_state.style`; defaults to `one_on_one` | No | `sonic_context_build: wrote understanding/sonic_context.json` |
| **sonic_context_build** | `sdp_cross_validate.py` | Invalid sonic_context vs manifest | Hard cross-artifact at `post_sonic_context` when hardening on | **Yes** | `Cross-artifact gate (post_sonic_context)` |
| **source_acoustic_profile** | `stages/understanding.py` | Missing `ingest/normalized.wav` | `FileNotFoundError` — hard prerequisite for SAP stage | **Yes** (ingest must run) | — |
| **source_acoustic_profile** | `acoustic_profile.py` | Operator overrides invalid | GUI PATCH returns validation errors | No | `acoustic_profile_override_saved` |
| **audio_preclean** | `stages/audio_preclean.py` | Operator never accepts offer (BUILD-072) | `ensure_preclean_skipped`; writes `preclean/skip.json`; marks done | No | `Audio pre-clean skipped (…)` · `stage=audio_preclean` |
| **audio_preclean** | `stages/audio_preclean.py` | DeepFilterNet fail + `local_fallback_enabled: true` | ffmpeg `afftdn` fallback | No | Provider in `preclean/provider.json` |
| **audio_preclean** | **Policy** | Any checkpoint | **Never auto-run** — operator must Accept via `POST …/preclean-offer` | N/A | [operator-gates.md](../../workflows/operator-gates.md#quality-improvement-offers-not-gates) |

**Hard gates (allowed to stop):** `analysis.flow_hardening` cross-artifact checks, blocking `claim_contradiction`, G0/G1/G2 operator gates, profile gate BUILD-081, `verify_master` / narrative QC at ship — each must cite [troubleshooting.md](../../workflows/troubleshooting.md).

---

## 6. Observability contract

### 6.1 Canonical log surface

| File | Writer | Reader |
|------|--------|--------|
| `gui_log.jsonl` | `session_log.append_log`, `RunContext.log()` in `src/interview_mux/run_context.py` | GUI `ActivityLogPanel`, `GET /api/runs/{id}/log` |
| `gui_job.json` | `src/interview_mux/web/runner.py` on `POST …/execute` | `GET /api/runs/{id}/job` |

**Entry shape** (`session_log.py`):

```json
{
  "ts": "ISO8601 UTC",
  "level": "info|success|warning|error|action",
  "message": "human-readable operator string",
  "stage": "optional stage_id",
  "detail": "optional string or JSON"
}
```

**Levels:** `info`, `success`, `warning`, `error`. GUI treats `action` as attention-worthy (checkpoint banner + optional ping). Always set `stage` when tied to a pipeline stage id.

**Do not use for operator-visible output:** bare `print()` / `logging` alone; ad-hoc `*.log` under run dir; `understanding/stage_runs/<stage>/attempt_*.json` (engineering audit only).

### 6.2 Gate panel messages

| Gate / event | GUI panel | `gui_job.json` status | Expected `gui_log` prefix / `stage` |
|--------------|-----------|----------------------|-------------------------------------|
| **G0** transcript | `TranscriptReviewPanel` | `needs_operator` / stage `action_required` | `Transcript dock: saved …` · `stage=transcript_review` |
| **G0.5** disfluency | `DisfluencyReviewPanel` | same | `disfluency_review` events |
| **Profile BUILD-081** | Story / Profile sub-tabs | `gate` | `stage=analysis_profile` · `level=action` |
| **G1** VO pickup | `g1_vo_pickup` gate | `needs_operator` | `stage=g1_vo_pickup` |
| **G2** flow select | `FlowSelectPanel` | `needs_operator` | `stage=g2_flow_select` |
| **LLM flow hardening** | Action modal / gate inset | `gate` | `LLM stage gate ({stage})` or `Stage {stage} failed hardening` |
| **Cross-artifact** | Action modal | `gate` | `Cross-artifact validation failed ({checkpoint})` |
| **Investigation** | Story Board investigations | `info` / `action` | `investigation_queue` patch lines |
| **Coherence ORC-03** | Story Board **Coherence risks** | `info` | `coherence_report` recompute lines |
| **Quality offer BUILD-072** | Non-blocking Quality offer card | — | `stage=audio_preclean` · Accept/Dismiss |
| **G1.5** prompt approval | Craft MMAudio prompts panel | `action_required` when blocked | `stage=sfx_prompt_craft` |
| **QC summaries** | Gate panel QC block | `gate` on strict fail | `narrative_qc`, `edl_narrative_qc`, `show_description_qc`, `verify_master` |

Panel map: [gui-surface-map.md](../../workflows/gui-surface-map.md).

### 6.3 Hard stop → troubleshooting.md mapping

| Hard stop symptom | troubleshooting.md section | Primary artifact |
|-------------------|------------------------------|------------------|
| `LLM stage gate (…)` | § LLM flow hardening gates | `understanding/stage_runs/<stage>/attempt_*.json` |
| `Cross-artifact gate (…)` | § LLM flow hardening gates · § Cross-validate SDP recovery | `segments/manifest.json`, producer JSON |
| `Analysis artifacts gate` | § LLM flow hardening gates | `understanding/analysis_state.json` `completion.blockers` |
| Preflight blocked | § LLM flow hardening gates | `gui_log.jsonl` preflight line |
| G0 pending | § Transcript review (G0) and dock | `transcript/review_queue.json` |
| G1 never clears | § Segmentation & gaps | `gap_report.json`, `vo_pickup/` |
| Profile gate | § LLM artifacts (operator themes) | `analysis_state.json` `meta.operator_verified` |
| `validate_narrative.py` fail | § Flow 1 ordering & narrative | `coverage_audit.json`, `selection.json` |
| `verify_master` fail | § Audio / mix | `flow_*_*/master.wav` |
| Placement QA ignored | § Cross-validate SDP recovery | `sound_design/placement_adjustments.json` |
| Pre-clean confusion | § MMAudio SFX + DeepFilterNet preclean | `run_meta.json` → `audio_preclean` |
| QC fail with no guidance | § GUI / operator shell | `run_meta.qc_summaries` |

**Gaps to fill in Wave 0 todos:** ensure every new hard stop from Waves A–E adds a troubleshooting row before promotion.

### 6.4 `ctx.log()` requirements for new operator-facing strings

When adding operator-visible status in hypothesis waves:

1. Use `RunContext.log(message, level=..., stage=..., detail=...)` — never parallel channels (see `.cursor/rules/interview-helper-mux.mdc`).
2. `message` must be actionable without opening `attempt_*.json`.
3. `detail` should cite artifact path(s) as JSON when structured.
4. Add matching row to [operator-stage-checklists.md](../../workflows/operator-stage-checklists.md) if new stage behavior.
5. Map symptom in [troubleshooting.md](../../workflows/troubleshooting.md) before marking todo done.

---

## 7. LLM flow hardening audit

**Implementation:** `src/interview_mux/llm_flow_hardening.py`, `src/interview_mux/llm_preflight.py`, `src/interview_mux/artifact_cross_validate.py`, `src/interview_mux/attempt_budget.py`  
**Architecture:** [LLM-ANALYSIS-ARCHITECTURE.md](../../LLM-ANALYSIS-ARCHITECTURE.md) §18–20  
**Config block:** `analysis.flow_hardening` in [config-keys.md](../../cross-cutting/config-keys.md)

### 7.1 Config keys (`config/app.defaults.json`)

| Key | Default | Purpose |
|-----|---------|---------|
| `enabled` | `true` | Master switch (`false` = legacy always `mark_done`) |
| `strict_critical_stages` | `true` | `SystemExit` on critical LLM stage failure |
| `preflight_enabled` | `true` | Deterministic checks before OpenAI (`llm_preflight.run_preflight`) |
| `cross_validate_enabled` | `true` | Cross-artifact checks at segmentation boundaries |
| `halt_on_schema_errors_with_accept` | `true` | Arbiter accept + schema errors → blocked |
| `investigation_dedupe` | `true` | Dedupe open investigations by kind+stage+target |
| `shard_min_success_ratio` | `0.75` | Min fraction of successful shards before collate |
| `inner_retry_require_delta` | `true` | Stop inner retries when volley/errors unchanged |
| `max_primary_attempts_per_stage` | `4` | Cap primary OpenAI calls (`attempt_budget.py`) |
| `max_arbiter_rejects_per_stage` | `3` | Cap non-accept arbiter verdicts before hard stop |
| `stuck_signature_threshold` | `2` | Identical attempt signatures → stage stuck |
| `max_investigation_reruns_per_kind` | `2` | Cap investigation-driven reruns per kind |
| `spend_block_stages` | SDP/craft/mix ids | `require_spend_prerequisites()` before MMAudio spend |
| `block_mix_without_sfx_when_enabled` | `true` | Block `mix_flow*` if SFX WAVs missing |

### 7.2 Execution path

```
pipeline.py run stage
  → maybe_require_upstream_llm_progress (upstream .stage_done + artifact complete)
  → llm_preflight.run_preflight (if preflight_enabled)
  → primary LLM volley (context_volley.py)
  → deterministic_lint.py + arbiter (attempt_budget caps)
  → complete_llm_stage_or_halt (marks .stage_done or SystemExit)
  → artifact_cross_validate.maybe_cross_validate_at_stage (if cross_validate_enabled)
```

**Critical stages** (`ALL_CRITICAL_LLM_STAGES` in `llm_flow_hardening.py`):

- Analysis: `speaker_roles`, `content_context`, `boundary_detection`, `segment_classification`, `content_brief_reanchor`, `missing_framing`, `optimal_questions`
- Flow: `topic_coverage_audit`, `narrative_arc_plan`, `full_master_ranking`, `highlight_selection`, `podcast_show_description`

### 7.3 Preflight

`llm_preflight.py` checks per stage:

- Transcript presence + G0 complete (`check_transcript_review_pending`)
- Minimum transcript length
- Upstream artifact `complete` status
- Spine preflight when `interview_spine.enabled`

Failure → no OpenAI call; `gui_log` error; job `gate` when executed via GUI.

### 7.4 Cross-validate checkpoints

`artifact_cross_validate.py` — `HARD_CHECKPOINTS` and `STAGE_CHECKPOINTS`:

| Checkpoint | Trigger stage(s) | Validator |
|------------|------------------|-----------|
| `post_segmentation` | `segment_classification` | Manifest/boundary consistency |
| `post_reanchor` | `content_brief_reanchor` | Brief topic segment_ids |
| `post_gaps` | `missing_framing` | Gap segment references |
| `post_sonic_context` | `sonic_context_build` | `sdp_cross_validate.validate_post_sonic_context` |
| `post_interview_spine` | `interview_spine_build` | Spine/manifest alignment |
| `post_coherence` | `topic_coverage_audit` | Coherence report consistency |
| `post_sound_palettes` | `sound_design_palettes` | Palette segment_ids |
| `post_sound_plan_flow1/2` | SDP flow plans | Cue anchors vs selection |
| `pre_sfx_generation` | `sfx_prompt_craft` | Craft vs SDP assets |
| `pre_mix_flow1/2` | `mmaudio_sfx_flow*` | Generated WAV presence |
| `pre_master_flow1/2` | `master_flow*` | Pre-master cross-check |
| `post_ranking` | `full_master_ranking` | Selection constraints |
| `post_edl_audit_fail` | `edl_narrative_audit` | EDL narrative verdict |

### 7.5 Attempt budget + arbiter

`attempt_budget.py` enforces `max_primary_attempts_per_stage`, `max_arbiter_rejects_per_stage`, `stuck_signature_threshold`, `max_investigation_reruns_per_kind`. Arbiter rubrics: `docs/prompts/_shared/arbiter-rubrics/*.json` — lint keys in [arbiter-stage-rubrics.md](../../prompts/_shared/arbiter-stage-rubrics.md).

### 7.6 When `enabled: false` is allowed

| Context | Risk | Documented in |
|---------|------|---------------|
| Local dev debugging single stage | Critical stages may mark done with incomplete artifacts | troubleshooting.md § LLM flow hardening |
| Legacy script reproduction | No spend blocks; no cross-artifact halt | **Dev only** — never ship to operators |
| CI fixture tests | Some tests disable hardening | `tests/test_flow_llm_integration.py` patterns |

**Production default:** `enabled: true`. Turning off hardening voids Wave 0 “no silent failure” criterion for LLM stages.

---

## 8. Operator gates audit

Full copy: [operator-gates.md](../../workflows/operator-gates.md). Implementation: `src/interview_mux/gates.py`, `src/interview_mux/web/stages.py`, `frontend/src/components/gates/*`.

| Gate | BUILD | Trigger | Blocks | Recovery |
|------|-------|---------|--------|----------|
| **G0** transcript | — | `transcript/review_queue.json` + missing `.stage_done/transcript_review` | `speaker_roles`+ (`G0_LOCKED_ANALYSIS_STAGES`) | Complete review → `POST …/transcript-review/complete` |
| **G0.5** disfluency | — | `disfluency_extract.enabled` + events + missing `.stage_done/disfluency_review` | `source_acoustic_profile`+ | Confirm/reject fillers → complete review |
| **LLM hardening** | — | Critical envelope / cross-artifact fail | Executing stage | `--from-stage <stage>` after artifact fix |
| **Analysis artifacts** | — | `require_analysis_artifacts_complete` at flow start | `run_flow.py` | Complete analysis through `optimal_questions` |
| **Profile** | BUILD-081 | `selected_flow: flow1` + `!meta.operator_verified` before `topic_coverage_audit` | Flow 1 extended stages | **Mark profile verified** → re-run from `topic_coverage_audit` |
| **G1** VO | BUILD-028 | `gap_report` `delivery: record` without `vo_pickup/*.wav` | Flow entry | Record WAVs → `--from-stage vo_ingest` |
| **G2** ship | BUILD-080 | Missing `run_meta.selected_flow` | Flow pipelines | `POST …/flow` or edit `run_meta.json` |
| **G1.5** prompts | — | `g1_5_require_prompt_approval: true` + unapproved `sfx_prompts.json` | `mmaudio_sfx_flow*` | Approve prompts in GUI |
| **Quality offer** | BUILD-072 | Checkpoint card shown | **Nothing** until Accept | Accept → `audio_preclean` + invalidation; Dismiss → continue |

**GUI mechanisms:** checkpoint banner, `OperatorActionModal`, `PendingActionBanner`, write approval (`.pending_writes/`), stage reuse offers — [gui-surface-map.md](../../workflows/gui-surface-map.md).

**Disfluency + transcript-quality alignment:**

- G0 produces `transcript_quality.flagged_chunks` per [transcript-quality-rubric.md](../../prompts/_shared/transcript-quality-rubric.md).
- G0.5 produces `disfluency_catalog` — distinct from comprehension gaps.
- `disfluency_extract.enabled: false` → auto-complete G0.5 (fail-open for operators who skip filler review).

---

## 9. Scenario atlas integration

**Atlas doc:** [interview-scenario-atlas.md](../../prompts/_shared/interview-scenario-atlas.md)  
**Sonic bridge:** [sonic-context.md](../../cross-cutting/sonic-context.md)  
**Builder:** `src/interview_mux/sonic_context.py` · stage `sonic_context_build`

### 9.1 `content_context` → format / tone classes

`content_context` LLM stage writes `memory_updates.style_patch` per [content-context.system.txt](../../prompts/understanding/content-context.system.txt):

| Field | Allowed values | Downstream use |
|-------|----------------|----------------|
| `format_class` | `one_on_one`, `panel`, `fireside`, `technical_deep_dive`, `media_profile`, `debate` | Atlas bucket selection; sonic_context inference |
| `tone_class` | `journalistic`, `conversational`, `investor`, `technical`, `human_interest` | Prompt tone; SDP `sonic_identity` |
| `format_notes` | free text | Panel/modal caveats in volley |

Persisted in `understanding/analysis_state.json` → `style` and `understanding/content_brief.json`.

### 9.2 `sonic_context`: atlas_bucket → sound_posture → sound_design plans

Pipeline: `sonic_context_build` → `sound_design_palettes` → `sound_design_plan_flow1|flow2` → `sfx_prompt_craft` → `mmaudio_sfx_flow*` → `mix_flow*`.

| `atlas_bucket` | `sound_posture` fields | SDP effect |
|----------------|------------------------|------------|
| From `SCENARIO_POSTURE` in `sonic_context.py` | `bed_density`, `stinger_cap_per_minute`, `adaptive_max_assets_flow1/2` | Caps cues; informs `coherence.sonic_identity` |
| `avoid_hard` | Scenario-specific bans | Prompt guardrails in `plan-flow1.system.txt` / `plan-flow2.system.txt` |
| `segment_flags` | trauma / overlap / jargon | Per-segment SFX suppression |
| `tag_registry` | provenance-grounded tags | Craft prompt themes |
| `cue_opportunities` | segment anchors | Placement in SDP `cues[]` |

Artifact: `understanding/sonic_context.json` — schema `docs/cross-cutting/json-schemas/sonic_context.schema.json`.  
Invalidation: `sonic_context_hash` in `understanding/sound_design_plan.json` when context changes.

### 9.3 `placement_adjustments` scenario_override schema

Path: `sound_design/placement_adjustments.json`  
Schema: `docs/cross-cutting/json-schemas/placement_adjustments.schema.json`  
Producer: `src/interview_mux/placement_qa.py` (deterministic, no OpenAI)

| Field | Purpose |
|-------|---------|
| `adjustments[].asset_id` | Target SFX asset |
| `adjustments[].cue_id` | Optional SDP cue link |
| `suggested_level_db_delta` | Duck/bed level hint |
| `suggested_crossfade_ms` | Flow 2 montage seam hint |
| `scenario_override: true` | Adjustment from atlas scenario policy (not operator) |
| `adaptive_level_source` | `sap_percentile` \| `operator` \| `default` \| `mmaudio_qa` |
| `provenance.rule_id` | Traceability to placement QA rule |

Applied at mix time via `placement_qa.apply_placement_adjustments` in `sound_design.py` — hints only unless operator edits SDP.

---

## 10. Deterministic QC chain

| QC step | When runs | Module / tool | Operator sees on fail | Strict config |
|---------|-----------|---------------|----------------------|---------------|
| **narrative_qc** | After `full_master_ranking`; before EDL persist | `gates.check_narrative_qc` → `tools/validate_narrative.py` | Gate panel errors in `run_meta.qc_summaries`; **Redo from selected stage** | `narrative_qc.strict` in config |
| **edl_narrative_qc** | After `edl_narrative_audit` / `edl_flow1` | `gates.check_edl_narrative_qc` | EDL audit findings + narrative constraint violations | `narrative_qc.strict` + `--include-edl` |
| **validate_edl** | During `edl_flow1` persist | `prompt_validation.validate_edl_flow1` | Schema/timeline errors in gate panel | Always on invalid shape |
| **verify_master** | Post `master_flow1` / `master_flow2` in `web/runner.py` | `master_qc.verify_master` / `tools/verify_master.py` | `gui_log` `stage=verify_master`; LUFS/peak lines | Hard fail on ship path |
| **placement_qa** | After SDP plan stages + post `mmaudio_sfx_flow*` | `placement_qa.maybe_run_placement_qa` | Hints in `placement_adjustments.json` + `gui_log` — **non-blocking** | `sound_design.placement_qa_enabled` |
| **show_description_qc** | After `podcast_show_description` | `show_description_qc.validate_show_description` / `gates.check_show_description_qc` | Word count / person / hype violations | `show_description_qc.strict` |

**Operator recovery recipes:**

```bash
python tools/validate_narrative.py --run-id <exec_id>
python tools/validate_narrative.py --run-id <exec_id> --include-edl
python tools/validate_edl.py --run-id <exec_id>
python tools/verify_master.py ASSETS/executions/<exec_id>/flow_1_master/master.wav
python tools/validate_show_description.py --run-id <exec_id>
```

See [smoke-test.md](../../workflows/smoke-test.md), [feedback-loops-and-reruns.md](../../workflows/feedback-loops-and-reruns.md).

---

## 11. Cross-artifact validation

**Module:** `src/interview_mux/artifact_cross_validate.py`  
**SDP-specific:** `src/interview_mux/sdp_cross_validate.py`  
**Tests:** `tests/test_artifact_cross_validate.py`, `tests/test_sdp_cross_validate.py`

### Relationship to flow_hardening

| Layer | Role |
|-------|------|
| `llm_flow_hardening` | Stage completion truth, preflight, spend blocks, critical halt |
| `artifact_cross_validate` | Post-stage consistency across **multiple** artifacts (manifest, brief, gaps, SDP) |
| `deterministic_lint.py` | Pre-merge envelope lint (single-stage) |
| `attempt_budget.py` | Retry/stuck caps before merge |

When `analysis.flow_hardening.cross_validate_enabled: true`, `maybe_cross_validate_at_stage` runs after mapped stages. Failures on `HARD_CHECKPOINTS` → `SystemExit` with `Cross-artifact gate ({checkpoint})` message.

**Soft failures:** non-hard checkpoints enqueue `cross_artifact_invalid` investigations (non-blocking).

**Analysis-ready gate:** `require_analysis_artifacts_complete` in `gates.py` calls `validate_cross_artifacts(ctx, "pre_flow1")` before Flow 1/2/3.

---

## 12. Wave blocking rules

From [h-hypothesis-wave-prompts.md](./h-hypothesis-wave-prompts.md):

| Order | Doc | Prerequisite |
|-------|-----|--------------|
| **0** | `wave-0-resilience-harness.md` (this file) | **First** — before any hypothesis code plans |
| **A** | `wave-a-early-truth.md` | Wave 0 promotion gate ([§15](#15-promotion-gate-for-wave-a)) |
| **B** | `wave-b-audio-structure.md` | Wave A promotion gates or documented exceptions |
| **C** | `wave-c-self-healing.md` | Wave B |
| **D** | `wave-d-output-resilience.md` | Wave C |
| **E** | `wave-e-big-bets.md` | Wave D — **parked only** |

**Do-no-harm rules (Wave 0 scope):**

| Wave | Risk if promoted carelessly | Guardrails |
|------|----------------------------|------------|
| **0** | Over-gating blocks all runs | Hardening on; operator gates preserved; fail-open inventory complete |
| **A** | Bad G0 order; false trust dips on noisy_room | A/B vs confidence-only; cap flags; scenario matrix noisy_room + prosody checks |
| **B** | Over-segmentation; spine/CLAP break installs | Boundary-truth tests; CLAP fail-open; ladder/spine dedupe |
| **C** | Investigation loops; false contradictions block ship | `flow_hardening` budgets; 30m gate; blocking threshold high-confidence only |
| **D** | Stingers on laughter; trauma violations; flat montage | placement QA; trauma_adjacent examples; highlight diversity |
| **E** | Heavy deps break core venv | Stay parked; isolated research venv; never block A–D |

No Wave A–E implementation PR may merge until this doc's applicable todos are checked or waived.

---

## 13. Repository touch matrix

Full harness map — include applicable rows in every wave doc PR.

| Layer | Paths / docs |
|-------|----------------|
| **Pipeline** | `src/interview_mux/pipeline.py`, [stage-registry.md](../stage-registry.md) |
| **Volley** | `src/interview_mux/context_volley.py`, [context-padding.md](../../cross-cutting/context-padding.md), [analysis-memory.md](../../cross-cutting/analysis-memory.md) |
| **LLM hardening** | `llm_flow_hardening.py`, `llm_preflight.py`, `artifact_cross_validate.py`, [LLM-ANALYSIS-ARCHITECTURE.md](../../LLM-ANALYSIS-ARCHITECTURE.md) §18–20 |
| **Orchestration** | `journey_orchestrator.py`, [analysis-orchestration-loop.md](../../workflows/analysis-orchestration-loop.md) |
| **Value analysis** | `stage_enrichment.py`, `value_analysis/extract.py`, `tools/extract_value_features.py`, `tools/run_value_spike.py` |
| **Spine / coherence** | `interview_spine/*`, `coherence/*`, `stages/interview_spine_stage.py` |
| **Scenario / sonic** | [interview-scenario-atlas.md](../../prompts/_shared/interview-scenario-atlas.md), `sonic_context.py`, `stages/sonic_context_stages.py`, [sonic-context.md](../../cross-cutting/sonic-context.md) |
| **Acoustic adapt** | `acoustic_profile.py`, `stages/understanding.py` (`run_source_acoustic_profile`), [source-derived-sonic-mix-profile.md](../../cross-cutting/source-derived-sonic-mix-profile.md) |
| **Observability** | `session_log.py`, `run_context.py`, `web/runner.py`, [troubleshooting.md](../../workflows/troubleshooting.md), [operator-journey.md](../../workflows/operator-journey.md) |
| **QA / ship** | `gates.py`, `placement_qa.py`, `master_qc.py`, `tools/verify_master.py`, `tools/validate_narrative.py`, `tools/validate_edl.py`, `tools/validate_show_description.py`, [smoke-test.md](../../workflows/smoke-test.md) |
| **Config** | `config/app.defaults.json`, [config-keys.md](../../cross-cutting/config-keys.md) |
| **GUI** | `web/stages.py`, `web/server.py`, `frontend/src/components/gates/*`, [gui-surface-map.md](../../workflows/gui-surface-map.md) |
| **Tests** | `tests/test_*` per subsystem; `tools/audit_stage_plans_doc.py` |
| **Docs index** | [june2026build/README.md](./README.md), [implementation-guide.md](../implementation-guide.md) |

---

## 14. Implementation todos

Minimum 80 checkboxes. Mark `[x]` only with evidence (test, manual sign-off, or doc PR). **No new default-on flags** without completing all 15 promotion points for that flag.

### 14.1 Fail-open path verification

- [ ] **FO-01** CLAP unavailable: run `interview_spine_build` without MMAudio venv → spine has `retrieval.enabled: false`; warning in `gui_log.jsonl`
- [ ] **FO-02** `interview_spine.enabled: false` → stage marks done; no `interview_spine.json` required downstream
- [ ] **FO-03** `energy_windows_from_path` returns `None` → `emphasis_regions_for_segments` returns `[]` (no exception)
- [ ] **FO-04** `quality_trajectory_flags` with no WAV → returns `[]`
- [ ] **FO-05** `quotability_signals` with no segments → returns `[]`
- [ ] **FO-06** `value_analysis.enabled: false` → `maybe_enqueue_orchestration_investigations` returns 0
- [ ] **FO-07** `coherence_activated` false on &lt;30m run → no risks in `coherence_report.json`
- [ ] **FO-08** `tests/test_coherence_duration_gate.py` green for short-run suppression
- [ ] **FO-09** `coherence.enabled: false` → `maybe_run_coherence_analysis` no-op
- [ ] **FO-10** `analysis.specialists.enabled: false` → no specialist subprocess calls
- [ ] **FO-11** Post-stage specialist exception → parent stage still completes (`tests/test_llm_specialists.py`)
- [ ] **FO-12** `sonic_context_build` with sparse manifest → valid `sonic_context.json` with default bucket
- [ ] **FO-13** `semantic_audio_qa` disabled → `skipped_reason: missing_wav` fail-open
- [ ] **FO-14** `audio_preclean` without operator accept → `preclean/skip.json` written (`tests/test_audio_preclean.py`)
- [ ] **FO-15** BUILD-072: confirm no code path auto-enables `run_meta.audio_preclean.enabled` without `POST …/preclean-offer` accept
- [ ] **FO-16** DeepFilterNet fail + `local_fallback_enabled: true` → `provider: ffmpeg_local` in lineage
- [ ] **FO-17** `disfluency_extract.enabled: false` → G0.5 auto-complete
- [ ] **FO-18** `spine_flow2_quotability_enabled: false` → quotability has no spine boost
- [ ] **FO-19** Low-confidence acoustic signal → omit investigation (no blocking enqueue)
- [ ] **FO-20** Document `value_analysis_skip_no_wav` log line when audio profile skipped in auto-extract path

### 14.2 Troubleshooting gap fill

- [ ] **TS-01** Map G0.5 disfluency stuck → new troubleshooting row (if missing)
- [ ] **TS-02** Map profile gate BUILD-081 → verify row in § LLM artifacts
- [ ] **TS-03** Map `coherence` blocking contradiction → troubleshooting row
- [ ] **TS-04** Map `placement_qa` hints → § Cross-validate SDP (exists — verify accuracy)
- [ ] **TS-05** Map `verify_master` GUI auto-run → § Audio / mix
- [ ] **TS-06** Map `show_description_qc` strict fail → § Flow 3
- [ ] **TS-07** Map `disfluency_review` pending → operator-gates + troubleshooting
- [ ] **TS-08** Map `investigation_queue` drain stuck → § LLM flow hardening
- [ ] **TS-09** Map `semantic_audio_qa` skip → local-audio-stack or troubleshooting appendix
- [ ] **TS-10** Map spine recompute invalidation → gui-surface-map Story Board section
- [ ] **TS-11** Every `SystemExit` in `llm_flow_hardening.complete_llm_stage_or_halt` has troubleshooting counterpart
- [ ] **TS-12** Every `HARD_CHECKPOINTS` cross-artifact fail cites recovery `--from-stage` in troubleshooting

### 14.3 Scenario fixtures → test or manual sign-off

- [ ] **SC-01** `one_on_one.json` — `pytest tests/test_sonic_context.py -k one_on_one` or manual
- [ ] **SC-02** `panel.json` — `tests/test_sound_design_scenario.py`
- [ ] **SC-03** `noisy_room.json` — manual listen + `tests/test_mix_acoustic_profile.py`
- [ ] **SC-04** `trauma_adjacent.json` — `tests/test_sfx_mmaudio.py` trauma refine skip
- [ ] **SC-05** `dense_jargon.json` — sonic_context tag inference test
- [ ] **SC-06** `fireside.json` — boundary merge bias manual spot-check doc'd
- [ ] **SC-07** `technical_deep_dive.json` — bed_density `none` in sonic_context output
- [ ] **SC-08** `media_profile.json` — Flow 2 crossfade ms from `_FLOW2_CROSSFADE_MS`
- [ ] **SC-09** `debate.json` — stinger cap ≤ 0.4/min in posture
- [ ] **SC-10** `coherence_30m_planted_drift/` — `tests/test_coherence_fixture_planted.py` green
- [ ] **SC-11** Short run (&lt;30m) — coherence risks empty (`tests/test_coherence_duration_gate.py`)
- [ ] **SC-12** Prosody diversity — manual sign-off on ≥2 hard-listener clips recorded in sign-off table

### 14.4 Observability + gates

- [ ] **OB-01** G0 complete emits `stage=transcript_review` success log
- [ ] **OB-02** G0.5 complete emits `stage=disfluency_review` log
- [ ] **OB-03** Profile verify emits `stage=analysis_profile` + `meta.operator_verified: true`
- [ ] **OB-04** G1 pickup save emits `stage=g1_vo_pickup` log per file
- [ ] **OB-05** G2 selection emits `stage=g2_flow_select` log
- [ ] **OB-06** LLM gate sets `gui_job.json` status `gate` (GUI test or manual)
- [ ] **OB-07** Quality offer Accept/Dismiss logged with `stage=audio_preclean`
- [ ] **OB-08** `sonic_context_build` detail includes `atlas_bucket` in `gui_log` JSON detail
- [ ] **OB-09** `placement_qa` logs hint count to `gui_log.jsonl`
- [ ] **OB-10** `verify_master` failure surfaces in gate panel via `run_meta.qc_summaries`
- [ ] **OB-11** No new operator string uses `print()` without `ctx.log()` in touched modules
- [ ] **OB-12** `session_log.py` levels documented in operator-stage-checklists for new stages

### 14.5 LLM hardening + volley parity

- [ ] **LH-01** `python tools/audit_stage_plans_doc.py` exits 0 in CI checklist
- [ ] **LH-02** Add `audit_stage_plans_doc.py` to [testing-and-verification.md](../testing-and-verification.md) Wave 0 row
- [ ] **LH-03** `analysis.flow_hardening.enabled: true` in shipped `app.defaults.json` verified
- [ ] **LH-04** Preflight blocks `speaker_roles` when G0 pending — manual or `tests/test_llm_preflight.py`
- [ ] **LH-05** `spend_block_stages` blocks `mix_flow1` without SFX when `block_mix_without_sfx_when_enabled: true`
- [ ] **LH-06** `attempt_budget` stuck signature stops retries — `tests/test_flow_llm_integration.py` or equivalent
- [ ] **LH-07** Cross-artifact `post_segmentation` fail message matches troubleshooting template
- [ ] **LH-08** `require_analysis_artifacts_complete` blocks flow start with actionable log
- [ ] **LH-09** Arbiter rubric `min_segment_coverage_ratio` documented per stage in arbiter JSON
- [ ] **LH-10** Dev-only `enabled: false` documented with risk callout in wave A doc

### 14.6 Deterministic QC chain

- [ ] **QC-01** `validate_narrative.py` wired at `full_master_ranking` — `gates.check_narrative_qc`
- [ ] **QC-02** `validate_narrative.py --include-edl` wired at `edl_flow1`
- [ ] **QC-03** `validate_edl.py` CLI documented in smoke-test Flow 1 section
- [ ] **QC-04** `verify_master.py` runs post-master in `web/runner.py`
- [ ] **QC-05** `placement_qa_enabled` default documented in config-keys
- [ ] **QC-06** `show_description_qc.strict` behavior verified for Flow 3
- [ ] **QC-07** `run_meta.qc_summaries` populated on QC fail for GUI panel
- [ ] **QC-08** Nine-scenario listen matrix procedure linked from definition-of-done §6

### 14.7 Disfluency + transcript-quality-rubric alignment

- [ ] **DQ-01** `transcript_quality.flagged_chunks` cap 25 verified in `context_volley.py`
- [ ] **DQ-02** `disfluency_catalog` injected separately from flagged_chunks
- [ ] **DQ-03** `content_context` prompt respects `transcript_quality` block per rubric
- [ ] **DQ-04** Fillers in G0.5 do not auto-create `missing_framing` gaps
- [ ] **DQ-05** `disfluency_restore` per-run toggle via `PATCH …/disfluency-restore` documented
- [ ] **DQ-06** High disfluency interview manual test — comprehension stages do not over-flag

### 14.8 Promotion checklist template (15 points → todos)

- [ ] **P-01** Spike stability process documented for Wave A hypotheses
- [ ] **P-02** MEC-A / MEC-D mechanism scores template in wave A doc
- [ ] **P-03** `tools/run_value_spike.py` baseline fixture pinned
- [ ] **P-04** `pytest tests/` green before any wave promotion PR
- [ ] **P-05** Schema/codegen drift check when artifacts change
- [ ] **P-06** Every new config key in `config-keys.md` + `app.defaults.json`
- [ ] **P-07** `audit_stage_plans_doc.py` in PR checklist for volley changes
- [ ] **P-08** GUI surface map updated for new operator panels
- [ ] **P-09** Final product validator named per hypothesis (Flow + tool)
- [ ] **P-10** `doc-maintenance.md` checklist run per PR
- [ ] **P-11** Do-not-promote-until blockers section in each wave doc
- [ ] **P-12** Observability todo per new gate string
- [ ] **P-13** Scenario matrix rows ticked per wave scope
- [ ] **P-14** Fail-open table updated per new signal path
- [ ] **P-15** Recovery `--from-stage` documented per new halt

### 14.9 CI + definition-of-done

- [ ] **CI-01** `./tools/check_prerequisites.sh` in Wave 0 verification block
- [ ] **CI-02** `pytest tests/test_stage_parity.py` — pipeline ↔ GUI order
- [ ] **CI-03** `pytest tests/test_artifact_cross_validate.py`
- [ ] **CI-04** `pytest tests/test_interview_spine_clap.py` for CLAP fail-open
- [ ] **CI-05** `pytest tests/test_preclean_offer.py` for BUILD-072
- [ ] **CI-06** `pytest tests/test_gates.py` for G0/G1/G2/profile
- [ ] **CI-07** Nine-scenario listen matrix procedure executed once — record in [definition-of-done-signoff.md](../definition-of-done-signoff.md) §6
- [ ] **CI-08** No hypothesis flag default-on in `app.defaults.json` without 15-point sign-off table

### 14.10 Cross-artifact + orchestration

- [ ] **CA-01** `post_sonic_context` validate path tested (`tests/test_sdp_cross_validate.py`)
- [ ] **CA-02** `pre_flow1` gate tested at flow entry
- [ ] **CA-03** `post_coherence` runs only when coherence active
- [ ] **CA-04** Investigation dedupe when `investigation_dedupe: true`
- [ ] **CA-05** `journey_orchestrator.py` respects `placement_qa_ready` milestone
- [ ] **CA-06** `execution_invalidation.py` clears downstream on SAP/spine recompute

### 14.11 Wave 0 doc hygiene

- [ ] **DOC-01** Link this file from [june2026build/README.md](./README.md) (already listed — verify)
- [ ] **DOC-02** Link from [implementation-guide.md](../implementation-guide.md) Wave 0 section
- [ ] **DOC-03** [INDEX.md](../../INDEX.md) entry for june2026build folder
- [ ] **DOC-04** No `.cursor/plans/*` edits in Wave 0 PRs

---

## 15. Promotion gate for Wave A

Wave A hypothesis implementation (`wave-a-early-truth.md`, seq 01–04: H-ING-03, H-G0-02, H-G0-01, H-GAP-01) **must not begin** until:

1. This document exists and is linked from [june2026build/README.md](./README.md).
2. All **applicable** §14 todos are `[x]` **OR** explicitly waived below.
3. Fail-open inventory (§5) reviewed for Wave A touch points: `stage_enrichment.py`, `value_analysis/*`, G0 ordering, `noisy_room` + prosody guardrails.
4. Scenario matrix rows for Wave A (`noisy_room`, `panel`, `debate`, `dense_jargon`, prosody diversity) have test or manual sign-off.
5. No Wave A config flag ships `default-on` in `app.defaults.json` without 15-point checklist (§2) for that hypothesis.

### Waived todo rationale table

| Todo ID | Waived? | Rationale | Sign-off (initials / date) |
|---------|---------|-----------|----------------------------|
| *(example)* FO-20 | ☐ | — | — |
| | | | |

**Approver:** Maintainer or operator lead before first Wave A code PR.

**Wave A entry command:** [h-hypothesis-wave-prompts.md](./h-hypothesis-wave-prompts.md) Command 1 — requires Wave 0 promotion status referenced in generated `wave-a-early-truth.md`.

---

## Related

- [h-hypothesis-wave-prompts.md](./h-hypothesis-wave-prompts.md) — Command 0 source
- [podcast-quality-roadmap.md](../../cross-cutting/podcast-quality-roadmap.md) — v1 vs target master
- [llm-guidance-program.md](../../cross-cutting/llm-guidance-program.md) — quality-first program index
- [stage-quality-scorecard.md](../../cross-cutting/stage-quality-scorecard.md) — per-stage shipped status
- [definition-of-done-signoff.md](../definition-of-done-signoff.md) — release candidate checklist
- [testing-and-verification.md](../testing-and-verification.md) — verify each wave
- [repository-map.md](../repository-map.md) — known doc ↔ code gaps
