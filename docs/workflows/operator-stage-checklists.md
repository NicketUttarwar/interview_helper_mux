# Operator stage checklists

Use these after each automated stage (or before a gate) so the run stays **correct before expensive steps** (Flow 1 extended analysis, MMAudio SFX, long re-runs). Gates (G0–G2) remain authoritative — see [operator-gates.md](./operator-gates.md).

**Coverage rule:** Any **new pipeline stage, gate, GUI panel, or quality offer** should add or extend a subsection here (Pass / If fail table or edge-case bullets). If it is not in this file, operators lack a single checklist source — update in the same PR as the feature.

**Live GUI:** Operator checklists are rendered in-app via `stages[].guidance` and **StepActionHeader** (mode + headline + primary). Checkpoint work is **modal-first** — see [ux-operator-model.md](./ux-operator-model.md). Sidebar substeps are navigation-only (`data-testid="substep-{id}"`). **Feedback contract** (toasts, spinners, `guardBusy`, `advanceFromCheckpoint`): [ui-truth-invariants.md](./ui-truth-invariants.md). This markdown file remains the engineering source; `src/interview_mux/stage_guidance.py` must stay in sync.

### UX smoke scripts (Pipeline simplification)

**Prepare — ingest → transcribe**

1. Run ingest; confirm **Running** badge on StepActionHeader while job polls.
2. When ingest completes, confirm **Needs you** + modal auto-opens with write approval.
3. Click **Save & continue** (`write-approval-save-continue`); modal closes; transcribe reuse modal opens if candidates exist.
4. Sidebar row for ingest collapses; transcribe row gets `sidebar-step--focus` when blocked.

**Write / reuse / handoff**

1. Write approval: only one Save CTA (panel, not modal footer Continue).
2. Reuse: modal shows reuse cards only; **Run fresh instead** advances.
3. Handoff: acknowledge in modal; pipeline continues to next runnable stage.

**Analyze — understanding phase**

1. Job `complete` → toast **Step finished — {next_action}**; activity log switches to Live.
2. Job `gate` / `needs_operator` → toast **Paused for your review**; modal auto-opens on Pipeline tab.
5. Resolve investigations — per-item spinner + toast; open count drops in sidebar when `refreshRun` completes.
6. Coherence / spine / SAP recompute buttons show spinner + start toast.

**Gates — G0 / G1**

1. Each gate: StepActionHeader shows **Needs you**; modal shows single gate panel (no guidance embed).
2. Complete gate in modal; modal closes via `closeActionModalAfterSuccess`; `advanceFromCheckpoint` advances without duplicate navigation toasts.

**E2E selectors:** prefer `step-action-primary` → modal panel buttons → sidebar substeps.

**`stage_guidance.py` parity (GUI bullets):** G0 transcript lock · G1 gate · stage reuse (`needs_stage_reuse`) · LLM upstream progress · cross-artifact checkpoint names (`post_segmentation`, `post_reanchor`, `post_gaps`, `pre_delivery`) · placement QA on mix stages · post-listen QA on MMAudio SFX stages · QC card reminder on ranking/EDL stages.

**GUI ↔ disk mapping:** [gui-surface-map.md](./gui-surface-map.md) (panels, APIs, artifacts).

**Operator status and logs (policy):** `.cursor/rules/interview-helper-mux.mdc` → **Centralized operator status and logs** — all operator-visible output goes to `gui_log.jsonl` and/or `gui_job.json` via `RunContext.log()`; do not duplicate that policy here. In the GUI, use the **Pipeline activity panel** (Live / This step / All) for per-step filtering; the **Logs** tab remains the full archive.

**Long interviews / caps:** [long-interview-chunking.md](./long-interview-chunking.md).

**LLM smart routing:** per-stage tiers in [llm-stage-model-matrix.md](../cross-cutting/llm-stage-model-matrix.md).

**Flow hardening (preflight):** [`analysis.flow_hardening`](../cross-cutting/config-keys.md#analysisflow_hardening) — deterministic prerequisites before flagship OpenAI calls.

**Cross-artifact checkpoints (after stage run):** `post_segmentation` (segment_classification) · `post_reanchor` (content_brief_reanchor) · `post_gaps` (missing_framing) · `post_optimal_questions` · `post_delivery_brief` · `post_narrative` · `post_ranking` · `post_sound_plan` · `pre_delivery` (analysis complete). GUI shows checkpoint name in stage guidance when hardening is enabled.

**Toolchain:** [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md) — venv from `requirements.lock`, `check_prerequisites.sh` + `pip-audit`.

**Support bundle:** `gui_log.jsonl` tail (what the operator saw) + latest `understanding/stage_runs/<stage>/attempt_*.json` (what the model returned).

---

## Global (every run)

| Check | Pass | If fail |
|-------|------|--------|
| Run workspace exists | `run_meta.json` + `ASSETS/executions/exec_*` (or legacy `data/run_NNN/`) | Start from GUI **Input audio** or resume **Previous executions** — [assets-and-executions.md](../cross-cutting/assets-and-executions.md) |
| Source audio on disk | `run_meta.input_audio_path` file exists under repo | Re-pick asset or copy WAV into `ASSETS/` |
| Input audio | `ingest/normalized.wav` duration > 0, `ffprobe` sane | [ingest](../pipeline/ingest/README.md) |
| Stage markers | `.stage_done/` matches what you think ran | [idempotent-runs.md](./idempotent-runs.md) |
| Disk space | Enough room for `normalized.wav`, clips, SFX, masters | Free space check before long runs |
| Secrets loaded | App sees `OPENAI_*` (and podcast `AWS_*` / `PODCAST_*` only if publishing RSS) | [smoke-test.md](./smoke-test.md); [podcast-rss-hosting.md](../cross-cutting/podcast-rss-hosting.md) |
| Toolchain lock | `./tools/check_prerequisites.sh` OK; `pip-audit` clean on lock | [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md); refresh lock or accepted advisory |
| Source audio hash | `run_meta.source_audio_hash` and `_short` set after run create; matches canonical pipeline WAV | Re-create run if hash missing on new-format id; compare **Executions** tab **Same audio** pill |
| Stage reuse decision | When offers appear: accept (copy) or decline (run fresh) before execute proceeds | [stage-execution-reuse.md](./stage-execution-reuse.md); `run_meta.stage_reuse[stage_id]` |
| Write approval | When enabled: review `.pending_writes/<stage>/` before **Save & continue** | [gui-surface-map.md](./gui-surface-map.md); set `journey_ui.require_write_approval_per_stage: false` for unattended runs |

---

## Stage execution reuse (every automated stage)

| Check | Pass | If fail |
|-------|------|--------|
| Candidates listed | Prior `exec_*` with same `source_audio_hash` and `.stage_done/<stage>` | No offer — run fresh; verify prior run completed that stage |
| Hash match banner | **Same source audio as this run** when hashes align | Different source — do not reuse unless paths intentionally match |
| Reuse accept | Files copied (staged or final per config); pipeline continues or opens write review | Check `gui_log.jsonl` `stage_reuse_applied`; verify source run artifacts exist |
| Reuse decline | `stage_reuse[stage_id].action === "decline"`; stage runs normally | Stuck on `needs_stage_reuse` — open action modal, choose **Run fresh instead** |

---

## Per-stage write approval

| Check | Pass | If fail |
|-------|------|--------|
| Artifact clarification | No open blocking issues in **Resolve artifact issues** step (`needs_clarification` cleared) | Open clarification panel; pick options or run auto-repair + re-check |
| Downstream propagation | After segment/boundary fix: propagation wizard clear or upstream rerun complete | Use **Downstream propagation required** panel; **Invalidate & re-run from …** before **Save & continue** |
| Staging folder | `.pending_writes/<stage_id>/` contains expected outputs after stage run | Stage may have failed before persist; check `gui_log.jsonl` |
| Empty staging (P0 LLM) | Write approval step shows staged paths; **Save** enabled | Backend sets LLM gate when P0 stage finishes with zero staged files — **Discard & re-run**; do not treat volley summary as success |
| Preview | JSON/text editable; WAV plays via pending audio URL | Path typo — refresh panel; re-run stage if staging empty |
| Approve | Files at final artifact paths; `.stage_done/<stage>` written | Approve failed — validation error in toast; fix JSON in staging editor |
| Discard | Staging cleared; stage invalidated for re-run | Use **Discard & re-run** then **Run step N** |

---

## Ingest & checksums

| Check | Pass | If fail |
|-------|------|--------|
| `ingest/checksums.json` | `source_sha256` / `normalized` consistent with files on disk | Re-`ingest`; verify no editor changed WAV under pipeline |
| Sample rate / channels | Matches project expectation (see ingest README) | Re-export source; re-ingest |
| Peak / silence | Not a flat zero file; duration matches source | Re-capture or fix input path |

---

## Orchestrator (`needs`, retries)

| Check | Pass | If fail |
|-------|------|--------|
| Envelope `status` | `complete` or acceptable `partial` before advancing | Read `attempt_*.json`; fix `needs` of type `operator` |
| `blocked` | Rare; has explicit reason | Unblock per envelope or edit profile and `--from-stage` |
| Iteration cap | `analysis_orchestration.json` not stuck maxing every stage | Widen input or simplify profile; check OpenAI errors in logs |
| Arbiter verdict | `arbiter_result.verdict` is `accept` before merge | `retry_uptier` / `reject` → read rubric in `docs/prompts/_shared/arbiter-rubrics/<stage>.json` |
| Deterministic lint | `deterministic_lint_errors` empty in latest `attempt_*.json` | Fix listed keys (schema, caps, ID grounding) before re-run — [arbiter-stage-rubrics.md](../prompts/_shared/arbiter-stage-rubrics.md) |
| Attempt cap | `attempt_signature` not repeating across the 2 allowed attempts | No budget to raise — fix the root cause and re-run `--from-stage <stage>` |
| Stuck signature | Same `attempt_signature` &lt; `stuck_signature_threshold` | Investigation enqueued; do not infinite uptier — check `gui_log.jsonl` |

**Program index:** [llm-guidance-program.md](../cross-cutting/llm-guidance-program.md) · **Export audit:** `python tools/export_llm_calls.py --run-id <exec_id> --format markdown` includes stage-run lint/arbiter appendix.

---

## LLM quality hardening (per stage)

Cross-artifact gates run when `analysis.flow_hardening.cross_validate_enabled` is true. **Hard** checkpoints block the pipeline with `SystemExit`.

| Stage | Pass | If fail |
|-------|------|--------|
| `sound_design_palettes` | Palettes grounded to manifest `segment_id`s; `coherence.sonic_identity` set | `--from-stage sound_design_palettes`; fix orphan palette segments |
| `sound_design_plan` | SDP `assets[]` ≤ cap; flow1 cues reference `selection` ids | `--from-stage sound_design_plan` |
| `REMOVED_sdp_flow2` | flow2 cues match highlight ranks; asset cap | `--from-stage REMOVED_sdp_flow2` |
| `full_master_ranking` | Ordered ids ⊆ manifest; chapter membership valid | `--from-stage full_master_ranking` |
| `transitions` | Transition targets valid; no fuzzy duplicate of `gap_report` VO | `--from-stage transitions` |
| `edl_narrative_audit` | `verdict` not `fail` before `edl` | Re-run ranking/transitions/audit per recommendations |
| `sfx_prompt_craft` | SDP `assets[]` non-empty; `sfx_prompts.json` on disk (**pre-spend hard**) | Complete plan stages; approve G1.5 when enabled |
| `mmaudio_sfx` / `_flow2` | One WAV per `asset_id` before mix (**pre-mix hard**) | Re-run craft + SFX; check `sound_design/assets/` |
| `mix` / `REMOVED_mix_flow2` | Spend gate satisfied; optional `placement_adjustments.json` reviewed | Listen preview first; fix SDP levels — [post-generation-placement.md](../cross-cutting/post-generation-placement.md) |

---

## LLM preflight (before OpenAI)

| Stage | Prerequisite | If fail |
|-------|--------------|--------|
| `speaker_roles` | `transcript/full.json` populated; G0 complete | Finish transcript review |
| `content_context` | Transcript length ≥ ~80 chars; G0 complete | Extend transcript or complete G0 |
| `boundary_detection` | `speakers.json` with ≥1 `interviewer`; `pause_ladder_hints` + SAP `pace_class` in volley | Re-run `speaker_roles` or edit speakers; `--from-stage boundary_detection` after G0 timestamp fix |
| `interview_spine_build` | `understanding/interview_spine.json` when enabled; CLAP optional (`retrieval.enabled: false` fail-open) | `--from-stage interview_spine_build` or **Recompute spine**; complete G0 + SAP first |
| `source_topology_build` (TBIY) | `source_topology.json` + `flow_adaptation.json`; when `production_style=tbiy_narrative`, the stage panel shows conformance score / acts / moat / VO-bridge modes | Confirm topology + pickup speaker; see [mastering-process.md](../cross-cutting/mastering-process.md) |
| `segment_classification` | `boundaries.json` non-empty | Re-run `boundary_detection` |
| `content_brief_reanchor` | Brief thesis+topics; `manifest.json` exists | Complete segmentation + `content_context` |
| Coherence (30m+) | `understanding/coherence_report.json` when duration ≥ 30m; review the coherence panel | `POST …/recompute-coherence` or `--from-stage content_brief_reanchor` |
| `value_features.json` | Trust-dip flags optional; `quality_trajectory_flags` when WAV present | `extract_value_features.py` or auto-extract after `content_context` |
| `missing_framing` | Pre-stage `comprehension_risk_blind` fail-open; risks in volley when present | Re-run `--from-stage missing_framing` |
| `optimal_questions` | `gap_evaluations.json` exists | Re-run `missing_framing` |
| `delivery_brief_build` | `understanding/delivery_brief.json` has duration + question + chapter budgets | `--from-stage delivery_brief_build`; edit overrides on Story board |
| `episode_structure_compose` | `understanding/episode_structure.json` present; sparse `slot_plan` OK without payoff/outro; `integrity.ok` true; occupancy clean | `--from-stage episode_structure_compose`; omitted STD phases are valid (not a failure) |
| Flow LLM stages | Analysis-ready artifacts all `complete` | Finish analysis; **Fill gaps** |

**Note:** `gap_report.json` with `"interviewer_lines": []` is valid when no VO lines are needed — the report is still `complete`.

---

## Long interviews & context limits

| Check | Pass | If fail |
|-------|------|--------|
| Transcript in volley | Within [`analysis.context`](../cross-cutting/config-keys.md#analysiscontext) caps | Truncate risk: verify themes still grounded; target shard/collate on eligible stages |
| `max_segments_in_context` | Ranking/coverage not blind to tail segments | Re-segment or run Flow stages with manifest subset if tooling supports |

---

## Optional — audio pre-clean

| Check | Pass | If fail |
|-------|------|--------|
| Offer only | You chose accept or dismiss; `run_meta.json` / log reflects choice | [audio_preclean](../pipeline/audio_preclean/README.md) |
| Lineage | `preclean/lineage.json` matches scope (`full_source` vs `vo_pickup`) | Re-run from `audio_preclean` with correct scope |

---

## Transcription + G0 (transcript review)

| Check | Pass | If fail |
|-------|------|--------|
| `transcript/full.json` | Words + timestamps; speakers present | [transcription](../pipeline/transcription/README.md), re-`transcribe` |
| Review queue | `transcript/review_queue.json` chunks have clips; `sort_mode=salience` (default) | `transcript_review_build` |
| G0 salience | Top ranks combine low confidence + stress — not confidence-only | `gui_log.jsonl` `G0 review queue built` |
| Dock word edits | `words[].corrected: true` after inline edits; `operator/transcript_corrected.json` updates (`source: dock_edit`) | Re-edit in dock; check `PATCH …/transcript/words` in network log |
| Fuzzy bulk replace | Repeated mishearings updated in one action; toast “Updated N words” when N &gt; 1 | Lower match strictness; confirm **Also replace similar matches** — [transcript-review.md](../pipeline/transcription/transcript-review.md#fuzzy-find-and-replace-similar-words) |
| **G0** | `.stage_done/transcript_review` after sign-off | Complete GUI review or CLI sign-off — [transcript-review.md](../pipeline/transcription/transcript-review.md) |
| Corrections applied | Spot-check: edited chunk text appears in `full.json` after complete | Re-complete review |
| Partial review | “Accept remaining” used deliberately; know uncorrected chunks remain | Spot-listen high-error regions later |

**Guard:** Do not start `speaker_roles` until G0 is done — downstream LLM stages assume reviewed text.

---

## Understanding + memory

| Check | Pass | If fail |
|-------|------|--------|
| `understanding/content_brief.json` (pass 1) | After `content_context`: **complete** for `thesis`, `topics`, sensible typed `key_claims` | **Fill gaps** or `--from-stage content_context`; edit in Files tab — [artifact-generation-and-validation.md](../cross-cutting/artifact-generation-and-validation.md) |
| `understanding/content_brief.json` (pass 2) | After `content_brief_reanchor`: `topics[].segment_ids` populated; `topic_relationships` present; claims have `evidence_segment_ids` where possible | `--from-stage content_brief_reanchor` after manifest stable |
| `analysis_state.hypotheses` | Open hypotheses from pass 1 confirmed/rejected after reanchor | Re-run `content_brief_reanchor` or edit profile |
| `understanding/speakers.json` | Roles match who asks vs answers; confirm `conversation_hypotheses` at handoff when listed | Edit + `--from-stage speaker_roles` or **Confirm interpretation** in handoff panel (`gui.speaker_roles.confirm_hypothesis`) |
| `understanding/source_acoustic_profile.json` | `pacing.pace_class` and `mix_contract` look plausible for the interview cadence | Re-run `--from-stage source_acoustic_profile`; verify transcript timing + ingest WAV |
| **Recompute SAP** (GUI) | **Recompute profile** on `source_acoustic_profile` stage re-derives from current ingest/transcript; invalidates downstream when pace class changes | Use after G0 corrections or preclean; check `gui_log.jsonl` for `acoustic_profile_recomputed` |
| **SAP overrides** (GUI) | Optional `operator_overrides.pace_class` / `underscore_policy` saved without re-running DSP | Clear overrides to restore derived values — [source-derived-sonic-mix-profile.md](../cross-cutting/source-derived-sonic-mix-profile.md) |
| `understanding/analysis_state.json` | Themes / questions / `style.tone_class` / `style.format_class` match interview | [analysis-memory.md](../cross-cutting/analysis-memory.md) |
| Investigations | `investigation_queue.json` not full of stale blockers | Resolve or dismiss; orchestrator may re-run |

---

## Profile gate — Flow 1 extended (BUILD-081)

**When:** `run_meta.json` has `REMOVED_selected_flow: flow1` and the next run would execute `topic_coverage_audit`. **Not blocking** for Flow 2 or Flow 3 (Flow 3 logs a warning only).

| Check | Pass | If fail |
|-------|------|--------|
| `understanding/analysis_state.json` | `meta.operator_verified: true`; `style.tone`, `style.tone_class`, `style.format_class` populated | GUI **Interview profile** → **Mark verified** — [artifact-layout](../cross-cutting/artifact-layout.md#shared-analysis-wave-2) |
| Before `topic_coverage_audit` | `.stage_done/topic_coverage_audit` absent and profile verified, or re-run from a later Flow 1 stage | Pipeline blocks with `ctx.log` at `level=action`; check `gui_log.jsonl` — [operator-gates.md](./operator-gates.md#profile-gate--flow-1-extended-build-081) |
| Flow 1 stage list (GUI) | Extended Flow 1 stages unlocked after verify | **Story** or **Profile** sub-tabs, or profile-lock CTAs on `topic_coverage_audit` — [gui-click-flow-matrix.md](./gui-click-flow-matrix.md) |

---

## Segmentation

| Check | Pass | If fail |
|-------|------|--------|
| `segments/boundaries.json` | No overlapping ranges; sorted by `start_ms` | `--from-stage boundary_detection` |
| `segments/manifest.json` | Every `segment_id` from boundaries has type + role + tags | `--from-stage segment_classification` |
| **Re-anchor** | `.stage_done/content_brief_reanchor` after classification | `--from-stage content_brief_reanchor` if topics lack segment anchors |
| Types | Not all `interviewee_answer`; asides / setup exist where audible | Re-classify or hand-edit manifest |
| Flags | Only known `flags` tokens — [segment-schema.md](../cross-cutting/segment-schema.md) | Fix JSON; invalid flags fail schema validation |
| `segment_id` alignment | Every manifest `segment_id` exists in `boundaries.json` | Re-run classification or fix merge bug |
| Downstream propagation | After manifest/boundary edit: revalidate shows no stale stages (`content_brief_reanchor` … `optimal_questions`) | Propagation wizard → invalidate & re-run from earliest stale stage |
| Empty `boundaries` / one giant segment | Pipeline still “valid” but useless | Re-run boundary_detection with pause ladder hints (400/700/1200 ms); check `pause_ladder_oversplit_risk` in log for fireside |
| Too many segments / fireside over-split | `pause_ladder_oversplit_risk` warning; hundreds of boundaries | Prefer 700/1200 ms tiers; SAP `pace_class: calm`; `--from-stage boundary_detection` |
| Crosstalk flagged | `heavy_crosstalk` segments correlated with STT garbage | Fix G0 in those ranges first |

---

## Interviewer gap + G1

| Check | Pass | If fail |
|-------|------|--------|
| `gap_evaluations.json` | High-severity rows have plausible `gap_type` | `--from-stage missing_framing` |
| `gap_report.json` | Each `delivery: record` has `line_id` / target segment | `--from-stage optimal_questions` |
| TBIY VO bridges | When `vo_bridge_priority` is `high`/`normal`, expect `reaction_line` / `chapter_hook` / `transition_banter` toward least-spoken pickup — do **not** expect documentary fallback | Confirm pickup speaker; re-run `optimal_questions` |
| `interviewer_script.txt` | Readable script matches report | Edit gap_report + regenerate script if tooling supports |
| **G1** | Every required line has `vo_pickup/{line_id}.wav` | Record pickups; optional pickup pre-clean — [operator-gates.md](./operator-gates.md#g1--human-vo-pickup) |
| Clone consent | When Chatterbox delivery is chosen: reference approved **and** clone consent granted with the scopes the plan needs (`cold_open` / `bridges` / `outro`). Guest cloning is never allowed. | GUI G-VoiceRef → Grant clone consent; audit in `mastering/voice_clone_audit.json` — [mastering-voice-clone-policy.md](../cross-cutting/mastering-voice-clone-policy.md) |
| `delivery: synthesize` | v1 **does not** trigger G1 — do not wait for TTS | Expect `record` only until product ships synthesize |

---

## G2 — flow pick

| Check | Pass | If fail |
|-------|------|--------|
| `run_meta.json` | `REMOVED_selected_flow` is `flow1`, `flow2`, or `flow3`; `selected_at` set | GUI G2 (**Use planned choice** if `REMOVED_flow_intent` set) or `python tools/run_delivery.py --flow flow1` — [operator-gates.md](./operator-gates.md#g2--flow-selection) |
| Flow match intent | `flow1` → expect `master/`; `flow2` → `REMOVED_flow2/`; `flow3` → `show_notes/` only (no audio) | Re-select G2; see [artifact-layout](../cross-cutting/artifact-layout.md) |

---

## Timeline (NLE) — Pipeline → Timeline tab

| Check | Pass | If fail |
|-------|------|--------|
| Smart actions | Use **Remove tangents**, **Tighten all pauses**, or **Review flagged** before hand-trimming every segment | Open **Review queue** for step-through |
| QC checklist | Resolve VO/chapter conflicts shown in timeline QC before Apply | **Jump** to segment → **Restore** or adjust trim |
| Apply mode | **Trims only** when only in/out edits changed; **Structural** when excluding/reordering; **Full narrative refresh** when transitions may be stale | Re-apply with correct `nle_apply_mode` — [api-reference.md](./api-reference.md) |
| Assembly preview | After Apply, listen in **Assembly** view; compare before/after preview players when present | Re-run `edl` + `assembly_preview` via Apply |
| Undo | Use **Edit history** or **Undo** if a batch preset over-trimmed | Restore prior `nle_edits.json` state from history panel |

---

## Flow 1 — extended analysis + assembly prep

| Check | Pass | If fail |
|-------|------|--------|
| **Profile gate** | See [Profile gate](#profile-gate--flow-1-extended-build-081) before `topic_coverage_audit` | — |
| `topic_coverage_audit` | `master/coverage_audit.json`; `coverage_score` sane; `missing_coverage` empty or triaged | `--from-stage topic_coverage_audit`; fix `segments/manifest.json` / profile topics — [artifact-layout](../cross-cutting/artifact-layout.md#flow-1--master) |
| `narrative_arc_plan` | `master/narrative_plan.json`; chapters + `ordering_constraints` achievable | `--from-stage narrative_arc_plan` |
| `full_master_ranking` | `master/selection.json`; `ordered_segment_ids` unique; constraints satisfied; after NLE **Save timeline**, re-run so `nle_edits.json` merges (`nle_applied` when overrides present) | `--from-stage full_master_ranking` |
| `validate_narrative.py` | Exits 0; every brief topic mapped or documented exclude; no empty selection chapters | [evaluation-metrics.md](../cross-cutting/evaluation-metrics.md); `--require-selection` before EDL |
| `transitions` | `master/transitions.json`; no duplicate gap VO; short lines | `--from-stage transitions` |
| `sound_design_plan` | G2 `REMOVED_selected_flow` is `flow1`; SDP has `assets[]` (3–6 unique `asset_id`s) and `flow_plans.podcast.cues[]`; every cue `asset_id` appears in `assets[]`; chapter stinger reused across chapters | `--from-stage sound_design_plan`; re-run `sound_design_palettes` if `coherence` / `palettes` empty — [sound-design.md](../cross-cutting/sound-design.md#flow-1-plan) |
| `sound_design_vo_finalize` | VO bridge cues have `measured_duration_ms` matching `vo_pickup/{line_id}.wav`; skipped cues logged when pickup missing | `--from-stage sound_design_vo_finalize` after G1 pickups; fix filenames before `edl` |
| `edl_narrative_audit` | `master/edl_narrative_audit.json`; local LLM framed the volley and flagship review has no blocking issues | Re-run `full_master_ranking`, `transitions`, or `edl_narrative_audit` based on recommendations |
| `edl` | `master/edl.json`; `vo_pickup` clips with `placement` + `timeline_start_ms`; `gap_placements` matches `gap_report`; NLE exclude/split/reorder/trim in clip bounds when `nle_edits.json` present; `edl_narrative_qc` card passes | `--from-stage edl`; fix `vo_pickup/` filenames or run `python tools/validate_narrative.py --run-id <exec_id> --include-edl` — [artifact-layout](../cross-cutting/artifact-layout.md) |
| `assembly_preview` | `master/assembly_preview.wav` listened; speech + VO (+ restored fillers when `disfluency_restore` enabled) | `--from-stage assembly_preview`; fix EDL / `vo_pickup/` before MMAudio SFX generation |
| `mix` | `master/assembly.wav` includes speech + VO + SDP beds/stingers; `master.wav` audible mix | `--from-stage mix`; verify SDP `assets[]`, `sound_design/assets/*.wav`, EDL — [assembly_and_mux](../pipeline/assembly_and_mux/README.md) · [stage-contracts](../cross-cutting/stage-contracts/00-INDEX.md) |
| `podcast_sfx_brief` | v1 legacy only (not in default `DELIVERY_ORDER`); optional single-stage rerun | `--from-stage podcast_sfx_brief` if bypassing SDP path |
| Ordering deadlocks | No `ordering_constraints` cycle; each id in manifest | Edit `narrative_plan.json` or re-run narrative stage |

---

## MMAudio SFX + DeepFilterNet preclean

**Canonical guide:** [local-audio-stack.md](../cross-cutting/local-audio-stack.md). Default path: SDP `assets[]` → `sound_design/assets/{asset_id}.wav` → `mix` / `REMOVED_mix_flow2`. Legacy v1: per-cue `sfx/*.wav` and `podcast_sfx_brief` / `sfx_brief` (single-stage rerun only).

### Pre-spend (before any generation API call)

| Check | Pass | If fail |
|-------|------|--------|
| Flow selected | G2 done; `run_meta.REMOVED_selected_flow` set | Complete G2 |
| Preview first | `assembly_preview.wav` listened before SFX spend | `--from-stage assembly_preview`; fix EDL / VO before craft |
| Plan exists | Flow 1: SDP `flow_plans.podcast` + `assets[]` (`sound_design_plan`); Flow 2: SDP `REMOVED_flow_plans_flow2` or v1 `sfx_brief.json`; craft follows plan | Re-run `sound_design_plan` / `_flow2` or v1 brief stages |
| **G1.5** (shipped; if `g1_5_require_prompt_approval`) | Operator approved `sfx_prompts.json` in GUI | Edit prompts; approve in GUI — [operator-gates.md](./operator-gates.md) |
| Craft quality | No vocals/lyrics in prompts; durations match role bands | [sound-design.examples.md](../prompts/_shared/examples/sound-design.examples.md); regression: [sfx-prompt-regression.md](../prompts/_shared/examples/sfx-prompt-regression.md) |
| Post-listen regression | Golden fixtures pass must-not-hear | [influence tuning](../cross-cutting/local-audio-stack.md); GUI **Pass** on craft/SFX panel or log `sfx_post_listen_pass` |
| Asset count | Target: ≤6 Flow 1 / ≤4 Flow 2 unique `asset_id`s | Trim SDP plan |
| Cost sanity | # API calls = unique assets (target), not # cues | Fix plan reuse |

### Generation

| Check | Pass | If fail |
|-------|------|--------|
| API key | Non-401 on generation | Rotate `` in `secrets.env` |
| Quota / rate limit | 429 → backoff; serial or ≤2 parallel | [troubleshooting.md](./troubleshooting.md) |
| Output files | v1: `sfx/*.wav`; target: `sound_design/assets/{asset_id}.wav` | Re-run SFX stage; check paths |
| Idempotency | Unchanged plan hash → skip regen | Delete asset only if plan changed |
| Audit | Target: `sound_design/sfx_prompts.json` present | Re-run craft stage |

### Post-generation (advisory post-listen GUI)

| Check | Pass | If fail |
|-------|------|--------|
| Listen each asset | Play `sound_design/assets/{asset_id}.wav` (or flow `sfx/` mirror) in GUI | Re-run **Generate SFX** after craft edits |
| Post-listen QA | Click **Pass** in **Post-listen QA** panel; optional note | Click **Fail** + note; regen via craft/SFX or [influence tuning](../cross-cutting/local-audio-stack.md) |
| Audit trail | `run_meta.sfx_listen_results[]` and `gui_log.jsonl` (`sfx_post_listen_pass` / `fail`) | Re-submit from GUI; does not block pipeline |
| Theme fit | Asset matches palette / `sonic_identity` | Regen asset (≤2 retries) — [sound-design.md § Post-generation](../cross-cutting/sound-design.md#post-generation-analysis-and-adaptive-placement) |
| Speech mask | Bed does not bury words in densest segment | Lower `level_db`; increase duck |
| Transitions | Flow 2 cuts feel connected | Adjust crossfade 80–200 ms or transition level |
| Operator log | Decision in `gui_log.jsonl` | Document approve / regen / level change |

### Audio isolation (pre-clean, BUILD-019)

| Check | Pass | If fail |
|-------|------|--------|
| Scope | `run_meta.audio_preclean.scope` matches intent (`full_source` vs `vo_pickup`) | Re-run with correct scope — [audio_preclean](../pipeline/audio_preclean/README.md) |
| A/B listen | Speech clearer without underwater tone | Disable pre-clean; use original |
| Lineage | `preclean/lineage.json` SHA matches source | Re-run `audio_preclean` |

---

## vo_ingest (after G1 recordings)

| Check | Pass | If fail |
|-------|------|--------|
| Pickup WAV format | Sample rate / channels compatible with mux expectations | Re-export pickups from DAW |
| Filenames | Match `gap_report` line ids | Rename files; re-`vo_ingest` |
| Clean lineage | If pickup pre-clean ran, mux reads `vo_pickup/clean/` per spec | [audio_preclean](../pipeline/audio_preclean/README.md) |

---

## Flow hygiene (switching `flow1` / `flow2` / `flow3`)

| Check | Pass | If fail |
|-------|------|--------|
| Artifacts | No accidental mixing of `master/`, `REMOVED_flow2/`, and `show_notes/` in one logical export | Use clean run or clear flow-specific dir per [feedback-loops-and-reruns.md](./feedback-loops-and-reruns.md) |
| `run_meta.json` | `REMOVED_selected_flow` matches the flow you are about to export | Fix before `run_flow.py` |

---

## Flow 3 — show description (REMOVED)

> **Heritage only.** Flow 3 and G2 are deleted. Live Ship packaging is [publishing/README.md](../pipeline/publishing/README.md) (G-Publish). Do not run these checks on current builds.

**Artifacts (historical):** `show_notes/` — [artifact-layout](../cross-cutting/artifact-layout.md#flow-3--flow_3_description).

| Check | Pass | If fail |
|-------|------|--------|
| G2 | `run_meta.json` → `REMOVED_selected_flow: flow3` | N/A — gate removed |
| `REMOVED_podcast_show_description` | Historical `show_notes/show_description.json` | Use `episode_meta_build` under G-Publish instead |

---

## Flow 2 — highlights (REMOVED)

> **Heritage only.** Highlight reel path deleted. Live path is full-master ranking → mix → `master_finalize`.

---

## Sound design & mix

| Check | Pass | If fail |
|-------|------|--------|
| `sound_design_palettes` | Stage done marker exists and SDP has non-empty `coherence.sonic_identity` + `palettes[]` | Re-run `python tools/run_analysis.py --run-id <id> --from-stage sound_design_palettes`; then inspect `understanding/sound_design_plan.json` |
| SDP file | `understanding/sound_design_plan.json` validates; palettes present before flow plans | See [guardrails-and-edge-cases.md](../prompts/sound_design/guardrails-and-edge-cases.md) |
| G1.5 (shipped; optional) | Operator approved prompt craft when `g1_5_require_prompt_approval` | Approve or edit prompts in GUI — [MMAudio pre-generation](#mmaudio-sfx--preclean) |
| Post-gen placement | Beds/stingers placed after listen + theme check; review **Placement QA** panel on mix/SFX stages (`PlacementAdjustmentsPanel`) | [local-audio-stack.md](../cross-cutting/local-audio-stack.md) · `sound_design/placement_adjustments.json` |
| Mix path | `mix` ran; VO + SFX audible in `master.wav` | `--from-stage mix`; see [assembly_and_mux](../pipeline/assembly_and_mux/README.md) · [stage-contracts](../cross-cutting/stage-contracts/00-INDEX.md) |

---

## QC summary cards (GUI + `run_meta.qc_summaries`)

Pipeline gates write pass/fail summaries to `run_meta.qc_summaries` and `gui_log.jsonl`. **GUI cards** render on these stage panels only:

| Stage panel | GUI card | `qc_summaries` key | Source |
|-------------|----------|-------------------|--------|
| `full_master_ranking`, `edl`, `edl_narrative_audit` | Yes | `narrative_qc` / audit card | `gates.check_narrative_qc`, `edl_narrative_audit` |
| `REMOVED_podcast_show_description` | Yes | `show_notes_qc` | `gates.check_show_notes_qc` |

**Log-only summaries** (inspect `run_meta.json` or `gui_log.jsonl`):

| Key | Written at | Source |
|-----|------------|--------|
| `edl_qc` | `edl`, `mix` | `gates.check_edl_qc` |
| `mix_intelligibility` | `mix` | `master_qc.maybe_check_mix_intelligibility` (when `mix.intelligibility_qc.enabled`) |

### Strict-gate recovery

| Key | If fail (strict) |
|-----|------------------|
| `narrative_qc` | Fix `coverage_audit.json` / `selection.json`; `python tools/validate_narrative.py --run-id <id>`; or `narrative_qc.strict: false` |
| `edl_qc` | Fix `master/edl.json`; `python tools/validate_edl.py --run-id <id>`; `--from-stage edl`; or `edl_qc.strict: false` |
| `edl_narrative_qc` | Fix coverage/order/transition/gap placement issue; `python tools/validate_narrative.py --run-id <id> --include-edl`; re-run `edl_narrative_audit` or `edl`; or `edl_narrative_qc.strict: false` |
| `show_notes_qc` | Fix JSON evidence / word count; re-run stage; or `show_notes_qc.strict: false` |
| `mix_intelligibility` | Lower bed levels / increase duck; re-run mix; or disable `mix.intelligibility_qc.enabled` |

**General:** Read error lists on the card or in `gui_log.jsonl` (`*_qc_fail` details). Fix artifacts, then `--from-stage <stage>`. With `nle_edits.strict: true`, fix `segments/nle_edits.json` before re-running ranking or EDL.

---

## Error tracing

| Layer | Where to look | What you get |
|-------|----------------|--------------|
| GUI header / Steps | `job.status: error`, `job.last_error` on `GET /api/runs/{id}` | Human message, stage id, **Retry** CTA |
| Activity log | `gui_log.jsonl` filtered by stage | `substep_fail` detail with traceback on stage wrapper failures |
| Background job file | `gui_job.json` | `last_error.message`, `error_class`, full `traceback` on disk |
| API (run-scoped) | `gui_log.jsonl` `stage: api` | Unhandled **5xx** on `/api/runs/{id}/*` — global FastAPI handler in `server.py` |
| LLM / cloud | `gui_log.jsonl` `level: error` on stage | OpenAI (or podcast boto3) failures via `operator_trace.log_failure` / `log_api_call` |
| Local stacks | MMAudio / preclean stages | Retry warnings then hard-fail error lines before job `status: error` |

**Tests:** `tests/test_stage_error_logging.py`, `tests/test_api_error_logging.py`, `tests/test_llm_runner_errors.py`, `tests/test_sfx_mmaudio_hard_fail.py`.

---

## Post-export QA

| Check | Pass | If fail |
|-------|------|--------|
| `verify_master.py` | Exits 0; LUFS/peak per flow; duration > 0; 44.1/48 kHz | [evaluation-metrics.md](../cross-cutting/evaluation-metrics.md), [mastering_and_export](../pipeline/mastering_and_export/README.md) |
| Listen | No clipped silence, wrong order, missing pickups (when mux wired) | [troubleshooting.md](./troubleshooting.md) |

---

## Mastering & `ffmpeg` (host toolchain)

| Check | Pass | If fail |
|-------|------|--------|
| `ffmpeg` / `ffprobe` on PATH | Ingest + verify_master succeed | Install host deps; see [smoke-test.md](./smoke-test.md) prerequisites |
| Master artifact | `master.wav` readable in DAW / `ffprobe` | Re-run mastering; check `assembly.wav` exists |

---

## Related

- [operator-gates.md](./operator-gates.md) — mandatory stops
- [gui-surface-map.md](./gui-surface-map.md) — GUI / API / logs map
- [long-interview-chunking.md](./long-interview-chunking.md) — context caps policy
- [feedback-loops-and-reruns.md](./feedback-loops-and-reruns.md) — `--from-stage` recipes
- [troubleshooting.md](./troubleshooting.md) — symptom playbook
- [evaluation-metrics.md](../cross-cutting/evaluation-metrics.md) — numeric targets
- [config-keys.md](../cross-cutting/config-keys.md) — defaults + secrets keys
- [pipeline/transcription/stt-and-diarization.md](../pipeline/transcription/stt-and-diarization.md) — STT options catalog
- [prompts/sound_design/guardrails-and-edge-cases.md](../prompts/sound_design/guardrails-and-edge-cases.md) — Wave 5 SDP/mix rails
