# Operator stage checklists

Use these after each automated stage (or before a gate) so the run stays **correct before expensive steps** (Flow 1 extended analysis, ElevenLabs, long re-runs). Gates (G0–G2) remain authoritative — see [operator-gates.md](./operator-gates.md).

**Coverage rule:** Any **new pipeline stage, gate, GUI panel, or quality offer** should add or extend a subsection here (Pass / If fail table or edge-case bullets). If it is not in this file, operators lack a single checklist source — update in the same PR as the feature.

**GUI ↔ disk mapping:** [gui-surface-map.md](./gui-surface-map.md) (panels, APIs, artifacts).

**Operator status and logs (policy):** `.cursor/rules/interview-helper-mux.mdc` → **Centralized operator status and logs** — all operator-visible output goes to `gui_log.jsonl` and/or `gui_job.json` via `RunContext.log()`; do not duplicate that policy here.

**Long interviews / caps:** [long-interview-chunking.md](./long-interview-chunking.md).

**LLM smart routing (spec):** [llm-orchestration.md](../cross-cutting/llm-orchestration.md) · per-stage tiers: [llm-stage-model-matrix.md](../cross-cutting/llm-stage-model-matrix.md).

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
| Secrets loaded | App sees `OPENAI_*`, `AWS_*`, `ELEVENLABS_*` as required by stage | [smoke-test.md](./smoke-test.md) |
| Toolchain lock | `./tools/check_prerequisites.sh` OK; `pip-audit` clean on lock | [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md); refresh lock or accepted advisory |

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
| Arbiter verdict (when implemented) | `arbiter_result.verdict` is `accept` before trusting artifacts | See `attempt_*.json`; `decompose` → check `shard_count`; `enqueue_investigation` → queue |

---

## Long interviews & context limits

| Check | Pass | If fail |
|-------|------|--------|
| Transcript in volley | Within `analysis.context` caps — see [context-padding.md](../cross-cutting/context-padding.md) | Truncate risk: verify themes still grounded; target shard/collate per [llm-orchestration.md](../cross-cutting/llm-orchestration.md) (not v1) |
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
| Review queue | `transcript/review_queue.json` chunks have clips | `transcript_review_build` |
| **G0** | `.stage_done/transcript_review` after sign-off | Complete GUI review or CLI sign-off — [transcript-review.md](../pipeline/transcription/transcript-review.md) |
| Corrections applied | Spot-check: edited chunk text appears in `full.json` after complete | Re-complete review |
| Partial review | “Accept remaining” used deliberately; know uncorrected chunks remain | Spot-listen high-error regions later |

**Guard:** Do not start `speaker_roles` until G0 is done — downstream LLM stages assume reviewed text.

---

## Understanding + memory

| Check | Pass | If fail |
|-------|------|--------|
| `understanding/content_brief.json` | Stage outputs **complete** (not partial); `thesis`, `topics`, sensible `key_claims` | **Fill gaps** or `--from-stage content_context`; edit in Files tab — [artifact-generation-and-validation.md](../cross-cutting/artifact-generation-and-validation.md) |
| `understanding/speakers.json` | Roles match who asks vs answers | Edit + `--from-stage speaker_roles` or fix in profile |
| `understanding/source_acoustic_profile.json` | `pacing.pace_class` and `mix_contract` look plausible for the interview cadence | Re-run `--from-stage source_acoustic_profile`; verify transcript timing + ingest WAV |
| **Recompute SAP** (GUI) | **Recompute profile** on `source_acoustic_profile` stage re-derives from current ingest/transcript; invalidates downstream when pace class changes | Use after G0 corrections or preclean; check `gui_log.jsonl` for `acoustic_profile_recomputed` |
| **SAP overrides** (GUI) | Optional `operator_overrides.pace_class` / `underscore_policy` saved without re-running DSP | Clear overrides to restore derived values — [source-derived-sonic-mix-profile.md](../cross-cutting/source-derived-sonic-mix-profile.md) |
| `understanding/analysis_state.json` | Themes / questions roughly match interview | [analysis-memory.md](../cross-cutting/analysis-memory.md) |
| Investigations | `investigation_queue.json` not full of stale blockers | Resolve or dismiss; orchestrator may re-run |

---

## Profile gate — Flow 1 extended (BUILD-081)

**When:** `run_meta.json` has `selected_flow: flow1` and the next run would execute `topic_coverage_audit`. **Not blocking** for Flow 2 or Flow 3 (Flow 3 logs a warning only).

| Check | Pass | If fail |
|-------|------|--------|
| `understanding/analysis_state.json` | `meta.operator_verified: true` | GUI **Interview profile** → **Mark verified**; or edit JSON on disk — [artifact-layout](../cross-cutting/artifact-layout.md#shared-analysis-wave-2) |
| Before `topic_coverage_audit` | `.stage_done/topic_coverage_audit` absent and profile verified, or re-run from a later Flow 1 stage | Pipeline blocks with `ctx.log` at `level=action`; check `gui_log.jsonl` — [operator-gates.md](./operator-gates.md#profile-gate--flow-1-extended-build-081) |
| Flow 1 stage list (GUI) | Extended Flow 1 stages unlocked after verify | **Story** or **Profile** sub-tabs, or profile-lock CTAs on `topic_coverage_audit` — [operator-flow-audit.md](./operator-flow-audit.md) |

---

## Segmentation

| Check | Pass | If fail |
|-------|------|--------|
| `segments/boundaries.json` | No overlapping ranges; sorted by `start_ms` | `--from-stage boundary_detection` |
| `segments/manifest.json` | Every `segment_id` from boundaries has type + role + tags | `--from-stage segment_classification` |
| Types | Not all `interviewee_answer`; asides / setup exist where audible | Re-classify or hand-edit manifest |
| Flags | Only known `flags` tokens — [segment-schema.md](../cross-cutting/segment-schema.md) | Fix JSON; invalid flags fail schema validation |
| `segment_id` alignment | Every manifest `segment_id` exists in `boundaries.json` | Re-run classification or fix merge bug |
| Empty `boundaries` / one giant segment | Pipeline still “valid” but useless | Re-run boundary_detection with pause thresholds from config |
| Crosstalk flagged | `heavy_crosstalk` segments correlated with STT garbage | Fix G0 in those ranges first |

---

## Interviewer gap + G1

| Check | Pass | If fail |
|-------|------|--------|
| `gap_evaluations.json` | High-severity rows have plausible `gap_type` | `--from-stage missing_framing` |
| `gap_report.json` | Each `delivery: record` has `line_id` / target segment | `--from-stage optimal_questions` |
| `interviewer_script.txt` | Readable script matches report | Edit gap_report + regenerate script if tooling supports |
| **G1** | Every required line has `vo_pickup/{line_id}.wav` | Record pickups; optional pickup pre-clean — [operator-gates.md](./operator-gates.md#g1--human-vo-pickup) |
| `delivery: synthesize` | v1 **does not** trigger G1 — do not wait for TTS | Expect `record` only until product ships synthesize |

---

## G2 — flow pick

| Check | Pass | If fail |
|-------|------|--------|
| `run_meta.json` | `selected_flow` is `flow1`, `flow2`, or `flow3`; `selected_at` set | GUI G2 (**Use planned choice** if `flow_intent` set) or `python tools/run_flow.py --flow flow1` — [operator-gates.md](./operator-gates.md#g2--flow-selection) |
| Flow match intent | `flow1` → expect `flow_1_master/`; `flow2` → `flow_2_highlights/`; `flow3` → `flow_3_description/` only (no audio) | Re-select G2; see [artifact-layout](../cross-cutting/artifact-layout.md) |

---

## Timeline (NLE) — Pipeline → Timeline tab

| Check | Pass | If fail |
|-------|------|--------|
| Smart actions | Use **Remove tangents**, **Tighten all pauses**, or **Review flagged** before hand-trimming every segment | Open **Review queue** for step-through |
| QC checklist | Resolve VO/chapter conflicts shown in timeline QC before Apply | **Jump** to segment → **Restore** or adjust trim |
| Apply mode | **Trims only** when only in/out edits changed; **Structural** when excluding/reordering; **Full narrative refresh** when transitions may be stale | Re-apply with correct `nle_apply_mode` — [api-reference.md](./api-reference.md) |
| Assembly preview | After Apply, listen in **Assembly** view; compare before/after preview players when present | Re-run `edl_flow1` + `assembly_preview` via Apply |
| Undo | Use **Edit history** or **Undo** if a batch preset over-trimmed | Restore prior `nle_edits.json` state from history panel |

---

## Flow 1 — extended analysis + assembly prep

| Check | Pass | If fail |
|-------|------|--------|
| **Profile gate** | See [Profile gate](#profile-gate--flow-1-extended-build-081) before `topic_coverage_audit` | — |
| `topic_coverage_audit` | `flow_1_master/coverage_audit.json`; `coverage_score` sane; `missing_coverage` empty or triaged | `--from-stage topic_coverage_audit`; fix `segments/manifest.json` / profile topics — [artifact-layout](../cross-cutting/artifact-layout.md#flow-1--flow_1_master) |
| `narrative_arc_plan` | `flow_1_master/narrative_plan.json`; chapters + `ordering_constraints` achievable | `--from-stage narrative_arc_plan` |
| `full_master_ranking` | `flow_1_master/selection.json`; `ordered_segment_ids` unique; constraints satisfied; after NLE **Save timeline**, re-run so `nle_edits.json` merges (`nle_applied` when overrides present) | `--from-stage full_master_ranking` |
| `validate_narrative.py` | Exits 0; every brief topic mapped or documented exclude; no empty selection chapters | [evaluation-metrics.md](../cross-cutting/evaluation-metrics.md); `--require-selection` before EDL |
| `transitions` | `flow_1_master/transitions.json`; no duplicate gap VO; short lines | `--from-stage transitions` |
| `sound_design_plan_flow1` | G2 `selected_flow` is `flow1`; SDP has `assets[]` (3–6 unique `asset_id`s) and `flow_plans.flow1.cues[]`; every cue `asset_id` appears in `assets[]`; chapter stinger reused across chapters | `--from-stage sound_design_plan_flow1`; re-run `sound_design_palettes` if `coherence` / `palettes` empty — [sound-design.md](../cross-cutting/sound-design.md#flow-1-plan) |
| `sound_design_vo_finalize` | VO bridge cues have `measured_duration_ms` matching `vo_pickup/{line_id}.wav`; skipped cues logged when pickup missing | `--from-stage sound_design_vo_finalize` after G1 pickups; fix filenames before `edl_flow1` |
| `edl_narrative_audit` | `flow_1_master/edl_narrative_audit.json`; local LLM framed the volley and flagship review has no blocking issues | Re-run `full_master_ranking`, `transitions`, or `edl_narrative_audit` based on recommendations |
| `edl_flow1` | `flow_1_master/edl.json`; `vo_pickup` clips with `placement` + `timeline_start_ms`; `gap_placements` matches `gap_report`; NLE exclude/split/reorder/trim in clip bounds when `nle_edits.json` present; `edl_narrative_qc` card passes | `--from-stage edl_flow1`; fix `vo_pickup/` filenames or run `python tools/validate_narrative.py --run-id <exec_id> --include-edl` — [artifact-layout](../cross-cutting/artifact-layout.md) |
| `assembly_preview` | `flow_1_master/assembly_preview.wav` listened; speech + VO only (no SFX spend yet) | `--from-stage assembly_preview`; fix EDL / `vo_pickup/` before ElevenLabs |
| **before_sfx_spend** (quality offer) | After preview listen, Accept/Dismiss pre-clean offer on `assembly_preview` panel if shown; checkpoint logged in `run_meta.audio_preclean.offered_at` | Accept → invalidate ingest path and re-run from `audio_preclean`; Dismiss → proceed to craft/generate — [operator-gates.md](./operator-gates.md#quality-improvement-offers-not-gates) |
| `mix_flow1` | `flow_1_master/assembly.wav` includes speech + VO + SDP beds/stingers; `master.wav` audible mix | `--from-stage mix_flow1`; verify SDP `assets[]`, `sound_design/assets/*.wav`, EDL — [assembly_and_mux](../pipeline/assembly_and_mux/README.md) · [stage-registry](../build-out/stage-registry.md) |
| `podcast_sfx_brief` | v1 legacy only (not in default `FLOW1_ORDER`); optional single-stage rerun | `--from-stage podcast_sfx_brief` if bypassing SDP path |
| Ordering deadlocks | No `ordering_constraints` cycle; each id in manifest | Edit `narrative_plan.json` or re-run narrative stage |

---

## ElevenLabs (SFX + isolation)

**Canonical guide:** [elevenlabs-integration-guide.md](../cross-cutting/elevenlabs-integration-guide.md). Default path: SDP `assets[]` → `sound_design/assets/{asset_id}.wav` → `mix_flow1` / `mix_flow2`. Legacy v1: per-cue `sfx/*.wav` and `podcast_sfx_brief` / `sfx_brief` (single-stage rerun only).

### Pre-spend (before any generation API call)

| Check | Pass | If fail |
|-------|------|--------|
| Flow selected | G2 done; `run_meta.selected_flow` set | Complete G2 |
| Preview first | `assembly_preview.wav` listened before SFX spend | `--from-stage assembly_preview`; fix EDL / VO before craft |
| Plan exists | Flow 1: SDP `flow_plans.flow1` + `assets[]` (`sound_design_plan_flow1`); Flow 2: SDP `flow_plans.flow2` or v1 `sfx_brief.json`; craft follows plan | Re-run `sound_design_plan_flow1` / `_flow2` or v1 brief stages |
| **G1.5** (shipped; if `g1_5_require_prompt_approval`) | Operator approved `elevenlabs_prompts.json` in GUI | Edit prompts; approve in GUI — [operator-gates.md](./operator-gates.md) |
| Craft quality | No vocals/lyrics in prompts; durations match role bands | [sound-design.examples.md](../prompts/_shared/examples/sound-design.examples.md); regression: [elevenlabs-prompt-regression.md](../prompts/_shared/examples/elevenlabs-prompt-regression.md) |
| Post-listen regression | Golden fixtures pass must-not-hear | [influence tuning](../cross-cutting/elevenlabs-prompt-influence-tuning.md); GUI **Pass** on craft/SFX panel or log `elevenlabs_post_listen_pass` |
| Asset count | Target: ≤6 Flow 1 / ≤4 Flow 2 unique `asset_id`s | Trim SDP plan |
| Cost sanity | # API calls = unique assets (target), not # cues | Fix plan reuse |

### Generation

| Check | Pass | If fail |
|-------|------|--------|
| API key | Non-401 on generation | Rotate `ELEVENLABS_API_KEY` in `secrets.env` |
| Quota / rate limit | 429 → backoff; serial or ≤2 parallel | [troubleshooting.md](./troubleshooting.md) |
| Output files | v1: `sfx/*.wav`; target: `sound_design/assets/{asset_id}.wav` | Re-run SFX stage; check paths |
| Idempotency | Unchanged plan hash → skip regen | Delete asset only if plan changed |
| Audit | Target: `sound_design/elevenlabs_prompts.json` present | Re-run craft stage |

### Post-generation (advisory post-listen GUI)

| Check | Pass | If fail |
|-------|------|--------|
| Listen each asset | Play `sound_design/assets/{asset_id}.wav` (or flow `sfx/` mirror) in GUI | Re-run **Generate SFX** after craft edits |
| Post-listen QA | Click **Pass** in **Post-listen QA** panel; optional note | Click **Fail** + note; regen via craft/SFX or [influence tuning](../cross-cutting/elevenlabs-prompt-influence-tuning.md) |
| Audit trail | `run_meta.elevenlabs_listen_results[]` and `gui_log.jsonl` (`elevenlabs_post_listen_pass` / `fail`) | Re-submit from GUI; does not block pipeline |
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
| Artifacts | No accidental mixing of `flow_1_master/`, `flow_2_highlights/`, and `flow_3_description/` in one logical export | Use clean run or clear flow-specific dir per [feedback-loops-and-reruns.md](./feedback-loops-and-reruns.md) |
| `run_meta.json` | `selected_flow` matches the flow you are about to export | Fix before `run_flow.py` |

---

## Flow 3 — show description

**Artifacts:** `flow_3_description/` — [artifact-layout](../cross-cutting/artifact-layout.md#flow-3--flow_3_description). **After G2** with `selected_flow: flow3`. Shared analysis complete; no Flow 1 ranking or Flow 2 highlights required.

| Check | Pass | If fail |
|-------|------|--------|
| G2 | `run_meta.json` → `selected_flow: flow3` | Complete [G2](#g2--flow-pick); `python tools/run_flow.py --flow flow3` |
| Profile (recommended) | `understanding/analysis_state.json` → `meta.operator_verified: true`, or you accept the unverified warning in `gui_log.jsonl` | [Profile gate](#profile-gate--flow-1-extended-build-081) (warn-only for Flow 3) |
| `podcast_show_description` | `flow_3_description/show_description.json` exists; `word_count` 150–250; third person in `description_markdown` | `--from-stage podcast_show_description`; edit profile / `understanding/content_brief.json` |
| Evidence | `evidence_segment_ids` populated; claims traceable to brief / manifest | Re-run `content_context` or fix brief |
| `export_show_description` | `flow_3_description/show_description.md` exists; plain text (no `**` / `*` left from markdown strip) | `--from-stage export_show_description` after JSON stage |
| No audio | No `master.wav` or `assembly.wav` under `flow_3_description/` | Select flow1/flow2 for audio deliverables — [publishing](../pipeline/publishing/README.md) |

---

## Sound design & mix

| Check | Pass | If fail |
|-------|------|--------|
| `sound_design_palettes` | Stage done marker exists and SDP has non-empty `coherence.sonic_identity` + `palettes[]` | Re-run `python tools/run_analysis.py --run-id <id> --from-stage sound_design_palettes`; then inspect `understanding/sound_design_plan.json` |
| SDP file | `understanding/sound_design_plan.json` validates; palettes present before flow plans | See [guardrails-and-edge-cases.md](../prompts/sound_design/guardrails-and-edge-cases.md) |
| G1.5 (shipped; optional) | Operator approved prompt craft when `g1_5_require_prompt_approval` | Approve or edit prompts in GUI — [ElevenLabs pre-spend](#elevenlabs-sfx--isolation) |
| Post-gen placement | Beds/stingers placed after listen + theme check | [elevenlabs-integration-guide.md](../cross-cutting/elevenlabs-integration-guide.md) |
| Mix path | `mix_flow1` / `mix_flow2` ran; VO + SFX audible in `master.wav` | `--from-stage mix_flow1` or `mix_flow2`; see [assembly_and_mux](../pipeline/assembly_and_mux/README.md) · [stage-registry](../build-out/stage-registry.md) |

---

## Flow 2 — highlights

| Check | Pass | If fail |
|-------|------|--------|
| `selection.json` | ≤5 clips; non-overlapping `start_ms`/`end_ms` | `--from-stage highlight_selection` |
| Self-contained | Each clip or ≤8s setup VO per spec | Edit selection or gap VO |
| `sound_design_plan_flow2` | G2 `selected_flow` is `flow2`; SDP has `assets[]` (2–4 unique `asset_id`s) and `flow_plans.flow2.cues[]`; every cue `asset_id` appears in `assets[]`; one `transition_stinger` reused for all `between_clips` | `--from-stage sound_design_plan_flow2`; re-run `sound_design_palettes` if `coherence` / `palettes` empty — [sound-design.md](../cross-cutting/sound-design.md#flow-2-plan) |
| `sfx_brief.json` | v1 montage brief (optional if SDP flow2 plan used) | `--from-stage sfx_brief` |

---

## QC summary cards (GUI + `run_meta.qc_summaries`)

Pipeline gates write pass/fail summaries to `run_meta.qc_summaries` and `gui_log.jsonl`. **GUI cards** render on these stage panels only:

| Stage panel | GUI card | `qc_summaries` key | Source |
|-------------|----------|-------------------|--------|
| `full_master_ranking`, `edl_flow1` | Yes | `narrative_qc` | `gates.check_narrative_qc` |
| `podcast_show_description` | Yes | `show_description_qc` | `gates.check_show_description_qc` |

**Log-only summaries** (inspect `run_meta.json` or `gui_log.jsonl`):

| Key | Written at | Source |
|-----|------------|--------|
| `edl_qc` | `edl_flow1`, `mix_flow1` | `gates.check_edl_qc` |
| `mix_intelligibility` | `mix_flow1`, `mix_flow2` | `master_qc.maybe_check_mix_intelligibility` (when `mix.intelligibility_qc.enabled`) |

### Strict-gate recovery

| Key | If fail (strict) |
|-----|------------------|
| `narrative_qc` | Fix `coverage_audit.json` / `selection.json`; `python tools/validate_narrative.py --run-id <id>`; or `narrative_qc.strict: false` |
| `edl_qc` | Fix `flow_1_master/edl.json`; `python tools/validate_edl.py --run-id <id>`; `--from-stage edl_flow1`; or `edl_qc.strict: false` |
| `edl_narrative_qc` | Fix coverage/order/transition/gap placement issue; `python tools/validate_narrative.py --run-id <id> --include-edl`; re-run `edl_narrative_audit` or `edl_flow1`; or `edl_narrative_qc.strict: false` |
| `show_description_qc` | Fix JSON evidence / word count; re-run stage; or `show_description_qc.strict: false` |
| `mix_intelligibility` | Lower bed levels / increase duck; re-run mix; or disable `mix.intelligibility_qc.enabled` |

**General:** Read error lists on the card or in `gui_log.jsonl` (`*_qc_fail` details). Fix artifacts, then `--from-stage <stage>`. With `nle_edits.strict: true`, fix `segments/nle_edits.json` before re-running ranking or EDL.

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
