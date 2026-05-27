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
| Run workspace exists | `run_meta.json` + `ASSETS/executions/…` or `data/run_NNN/` | Re-run ingest / fix paths in config |
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
| `understanding/content_brief.json` | `thesis`, `topics`, sensible `key_claims` | Edit profile + `--from-stage content_context` |
| `understanding/speakers.json` | Roles match who asks vs answers | Edit + `--from-stage speaker_roles` or fix in profile |
| `understanding/analysis_state.json` | Themes / questions roughly match interview | [analysis-memory.md](../cross-cutting/analysis-memory.md) |
| Investigations | `investigation_queue.json` not full of stale blockers | Resolve or dismiss; orchestrator may re-run |

**Before Flow 1 extended (recommended guard):** set `meta.operator_verified: true` when themes, `major_questions`, and `style` are right — see [operator-gates.md](./operator-gates.md#interview-profile-review-recommended-blocking-before-flow-1-extended--planned).

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
| `run_meta.json` | `selected_flow` is `flow1`, `flow2`, or `flow3` | Set flow before `run_flow.py` |

---

## Flow 1 — extended analysis + assembly prep

| Check | Pass | If fail |
|-------|------|--------|
| `coverage_audit.json` | `coverage_score` sane; `missing_coverage` empty or triaged | `--from-stage topic_coverage_audit`; fix manifest/topics |
| `narrative_plan.json` | Chapters + `ordering_constraints` achievable | `--from-stage narrative_arc_plan` |
| `selection.json` | `ordered_segment_ids` unique; constraints satisfied | `--from-stage full_master_ranking` |
| `transitions.json` | No duplicate gap VO; short lines | `--from-stage transitions` |
| `podcast_sfx_brief.json` | Ducking / levels described | `--from-stage podcast_sfx_brief` |
| **v1 reality** | `master.wav` is speech reorder until BUILD-065/067 — [assembly_and_mux](../pipeline/assembly_and_mux/README.md) | Expectation only; track [podcast-quality-roadmap](../cross-cutting/podcast-quality-roadmap.md) |
| Ordering deadlocks | No `ordering_constraints` cycle; each id in manifest | Edit `narrative_plan.json` or re-run narrative stage |

---

## ElevenLabs (SFX + isolation)

**Canonical guide:** [elevenlabs-integration-guide.md](../cross-cutting/elevenlabs-integration-guide.md). **v1:** per-cue `sfx/*.wav`, fixed ~2s, speech-only mux may ignore SFX. **Target:** per-`asset_id` under `sound_design/assets/`.

### Pre-spend (before any generation API call)

| Check | Pass | If fail |
|-------|------|--------|
| Flow selected | G2 done; `run_meta.selected_flow` set | Complete G2 |
| Preview first | `assembly_preview.wav` listened when BUILD-069 exists | Generate preview before SFX spend |
| Plan exists | v1: `podcast_sfx_brief.json` / `sfx_brief.json`; target: SDP + craft | Re-run brief/plan stages |
| **G1.5** (if `require_operator_prompt_approval`) | Operator approved `elevenlabs_prompts.json` or craft in GUI | Edit prompts; approve in GUI — [operator-gates.md](./operator-gates.md) |
| Craft quality | No vocals/lyrics in prompts; durations match role bands | [sound-design.examples.md](../prompts/_shared/examples/sound-design.examples.md); regression: [elevenlabs-prompt-regression.md](../prompts/_shared/examples/elevenlabs-prompt-regression.md) |
| Post-listen regression | Golden fixtures pass must-not-hear | [influence tuning](../cross-cutting/elevenlabs-prompt-influence-tuning.md); log `elevenlabs_post_listen_pass` / `fail` |
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

### Post-generation (target / manual until automated)

| Check | Pass | If fail |
|-------|------|--------|
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

| Check | Pass | If fail |
|-------|------|--------|
| Profile | `meta.operator_verified: true` recommended | Verify interview profile before `podcast_show_description` |
| `show_description.json` | `word_count` 150–250; third person in `description_markdown` | `--from-stage podcast_show_description`; edit profile/brief |
| Evidence | `evidence_segment_ids` populated; no unsupported claims | Re-run `content_context` or fix brief |
| `show_description.md` | Plain export readable *(when BUILD-046 ships)* | Re-run export stage |
| No audio | Do not expect `master.wav` under `flow_3_description/` | Select flow1/flow2 for audio deliverables |

---

## Sound design & mix (when BUILD-060+ ships)

| Check | Pass | If fail |
|-------|------|--------|
| SDP file | `understanding/sound_design_plan.json` validates; palettes present before flow plans | See [guardrails-and-edge-cases.md](../prompts/sound_design/guardrails-and-edge-cases.md) |
| G1.5 (optional) | Operator approved prompt craft when `require_operator_prompt_approval` | Approve or edit plan JSON — [ElevenLabs pre-spend](#elevenlabs-sfx--isolation) |
| Post-gen placement | Beds/stingers placed after listen + theme check | [elevenlabs-integration-guide.md](../cross-cutting/elevenlabs-integration-guide.md) |
| Mix vs speech-only | Know whether this build muxes VO/SFX or concat-only | [assembly_and_mux](../pipeline/assembly_and_mux/README.md) |

---

## Flow 2 — highlights

| Check | Pass | If fail |
|-------|------|--------|
| `selection.json` | ≤5 clips; non-overlapping `start_ms`/`end_ms` | `--from-stage highlight_selection` |
| Self-contained | Each clip or ≤8s setup VO per spec | Edit selection or gap VO |
| `sfx_brief.json` | Matches clip count / ranks | `--from-stage sfx_brief` |

---

## Post-export QA

| Check | Pass | If fail |
|-------|------|--------|
| `verify_master.py` | Exits 0; duration > 0 | [mastering_and_export](../pipeline/mastering_and_export/README.md) |
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
