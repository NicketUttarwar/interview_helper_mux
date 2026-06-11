# Artifact layout

All run artifacts live under `ASSETS/executions/exec_NNN_<hash12>_TIMESTAMP/` (filesystem-only state). The 12-character segment is `source_audio_hash_short` from the canonical pipeline WAV. Legacy ids `exec_NNN_TIMESTAMP` and `data/run_NNN/` runs are still readable.

**ASSETS model (source audio + resume):** [assets-and-executions.md](./assets-and-executions.md) — operators pick input WAVs from `ASSETS/` in the GUI; every execution folder holds full run state for relaunch via `./scripts/run.sh`.

See also: [json-schema-coverage.md](./json-schema-coverage.md) and [json-schemas/README.md](./json-schemas/README.md) for which artifacts are schema-backed vs planned. **Generation, gap-fill, validation:** [artifact-generation-and-validation.md](./artifact-generation-and-validation.md). **GUI:** [workflows/gui-surface-map.md](../workflows/gui-surface-map.md).

## ASSETS top level

```
ASSETS/
  input/                    # operator source WAVs (recommended; any name)
  executions/exec_* /       # per-run workspace (tree below)
  .gui/                     # active run pointer, server session (not stage artifacts)
```

## Run root

```
ASSETS/executions/exec_001_a1b2c3d4e5f6_20260523T120000Z/
  run_meta.json                 # execution_number, input path, source_audio_hash, selected_flow, stage_reuse, timestamps ([run_meta.schema.json](./json-schemas/run_meta.schema.json))
  gui_log.jsonl                 # centralized operator log (policy: .cursor/rules/interview-helper-mux.mdc)
  gui_job.json                  # last background execute job status (GUI job panel)
  segments/nle_edits.json       # non-linear editor state
  analysis_complete.json        # set when Wave 2 finishes
  .stage_done/                  # one empty marker file per completed stage (deferred until write approval when enabled)
  .pending_writes/<stage_id>/   # staged outputs awaiting operator approve/discard (when journey_ui.require_write_approval_per_stage)
  .archived/<timestamp>/        # downstream artifacts moved here on invalidate/redo (see run_meta.invalidation_archive)
  .run.lock                      # cross-process mutex for CLI + GUI jobs + mutating API calls
  vo_pickup/                    # operator-recorded WAVs (G1 gate)
  vo_pickup/clean/              # optional; after pickup-scoped pre-clean (BUILD-019/072)
  preclean/                     # optional; full-source or lineage for pre-clean runs
  ingest/
  transcript/
  understanding/
  segments/
  flow_1_master/                # only when flow1 selected
  flow_2_highlights/            # only when flow2 selected
  flow_3_description/           # only when flow3 selected
```

## Shared analysis (Wave 2)

### Operator-editable profile (verify and adjust per interview)

| Path | Editable | Purpose |
|------|----------|---------|
| `understanding/analysis_state.json` | **Yes** | Themes, major questions, style, narrative — main interview profile ([analysis_state.schema.json](./json-schemas/analysis_state.schema.json)) |
| `understanding/investigation_queue.json` | Yes | Open investigations / rerun hints |
| `understanding/content_brief.json` | Yes | Content brief — thesis, topics, typed `key_claims`, `topic_relationships` (synced to memory) |
| `understanding/sound_design_plan.json` | Yes | Coherent sound design plan shell (BUILD-060 baseline; schema: [sound_design_plan.schema.json](./json-schemas/sound_design_plan.schema.json); expanded by Wave 5 stages) |
| `understanding/source_acoustic_profile.json` | Yes | Per-interview pacing, energy, mix contract — [source_acoustic_profile.schema.json](./json-schemas/source_acoustic_profile.schema.json); [source-derived-sonic-mix-profile.md](./source-derived-sonic-mix-profile.md) |
| `understanding/speakers.json` | Yes | Speaker roles |
| `segments/manifest.json` | Yes | Segment timeline |

See [analysis-memory.md](./analysis-memory.md). Edit in GUI **Interview profile** or stage JSON editor. All LLM JSON paths listed here are validated on write (`ARTIFACT_WRITE_VALIDATORS`) and may show **partial** / **complete** in Stage outputs — [artifact-generation-and-validation.md](./artifact-generation-and-validation.md).

### Machine + stage artifacts

| Path | Stage |
|------|-------|
| `preclean/isolated.wav` | audio_preclean (optional) |
| `preclean/provider.json` | audio_preclean |
| `preclean/lineage.json` | audio_preclean |
| `ingest/normalized.wav` | ingest |
| `ingest/checksums.json` | ingest ([ingest_checksums.schema.json](./json-schemas/ingest_checksums.schema.json)) |
| `transcript/full.json` | transcription; dock word edits set `words[].corrected`; `review_applied_at` on G0 complete |
| `transcript/speakers.json` | transcription (AWS diarization) |
| `transcript/review_queue.json` | transcript_review_build |
| `transcript/review_clips/*.wav` | transcript_review_build |
| `transcript/disfluencies.json` | disfluency_extract |
| `transcript/disfluency_clips/*.wav` | disfluency_extract |
| `transcript/disfluency_review.json` | disfluency_review (gate) |
| `flow_1_master/disfluency_restore_plan.json` | edl_flow1 |
| `transcript/corrections.json` | transcript_review (operator) ([transcript_corrections.schema.json](./json-schemas/transcript_corrections.schema.json)) |
| `operator/manifest.json` | Index of operator-authored snapshots (GUI edits, settings) |
| `operator/transcript_corrected.json` | Independent operator-corrected transcript per execution; refreshed on each dock word edit (`source: dock_edit`) and chunk save / G0 complete |
| `operator/transcript_corrected.txt` | Plain-text export of corrected transcript (same refresh cadence) |
| `operator/transcript_corrections.json` | Copy of chunk corrections at save time |
| `operator/analysis_profile.json` | Interview profile as edited by operator |
| `operator/nle_edits.json` | Timeline / NLE operator edits |
| `operator/acoustic_profile_overrides.json` | Pacing / mix overrides |
| `operator/flow_selection.json` | G2 flow choice |
| `operator/preclean_decisions.json` | Pre-clean accept/dismiss history |
| `operator/stage_reuse_decisions.json` | Stage reuse accept/decline log |
| `operator/elevenlabs_prompts.json` | ElevenLabs prompt review edits |
| `operator/elevenlabs_listen_results.json` | Post-listen pass/fail results |
| `operator/investigation_queue.json` | Investigation status edits |
| `operator/artifacts/*.json` | Mirrors of other GUI-edited artifacts |
| `understanding/analysis_orchestration.json` | orchestrator config / attempts |
| `understanding/context_index.json` | context padding index |
| `understanding/stage_runs/<stage>/attempt_*.json` | LLM envelope audit trail |
| `understanding/llm_calls/index.jsonl` | Index of every OpenAI call (label, path) — [llm-call-record-framework.md](./llm-call-record-framework.md) |
| `understanding/llm_calls/<stage>/attempt_NNN/<seq>_<task_kind>.json` | Full request/response + volley per API call |
| `understanding/llm_calls/<stage>/attempt_NNN/<seq>_<task_kind>.md` | Optional copy-paste markdown sidecar |
| `understanding/speakers.json` | speaker roles (LLM) |
| `understanding/content_brief.json` | `content_context` (pass 1) + `content_brief_reanchor` (patch) |
| `understanding/sound_design_plan.json` | shared analysis init (BUILD-060 baseline) |
| `understanding/source_acoustic_profile.json` | source_acoustic_profile |
| `understanding/gap_evaluations.json` | missing framing |
| `understanding/gap_report.json` | optimal questions aggregate |
| `understanding/interviewer_script.txt` | human-readable VO script |
| `understanding/value_features.json` | optional; value-analysis extractor (`tools/extract_value_features.py` or auto after `content_context`) |
| `segments/boundaries.json` | boundary detection |
| `segments/manifest.json` | segment classification |

## Sound design — `sound_design/` (run root; Flow 1 + Flow 2 SDP path)

| Path | Stage |
|------|-------|
| `sound_design/elevenlabs_prompts.json` | `elevenlabs_prompt_craft` (canonical; operator mirror at `operator/elevenlabs_prompts.json`) |
| `sound_design/placement_adjustments.json` | post-SFX placement QA hints; applied at mix via `apply_placement_adjustments` |
| `sound_design/assets/{asset_id}.wav` | ElevenLabs generated beds/stingers (canonical SDP path) |

## Flow 1 — `flow_1_master/`

| Path | Stage |
|------|-------|
| `coverage_audit.json` | topic coverage audit |
| `narrative_plan.json` | narrative arc plan |
| `selection.json` | ordered segments, chapters |
| `transitions.json` | interviewer bridges |
| `edl_narrative_audit.json` | flagship semantic audit before final EDL ([edl_narrative_audit_artifact.schema.json](./json-schemas/artifacts/edl_narrative_audit_artifact.schema.json)) |
| `podcast_sfx_brief.json` | subtle SFX spec (v1 legacy brief) |
| `sfx/*.wav` | legacy per-flow SFX folder when SDP assets absent (copies from run-root `sound_design/assets/` when present) |
| `edl.json` | edit decision list — speech + `vo_pickup` + transition timeline ([edl_flow1.schema.json](./json-schemas/artifacts/edl_flow1.schema.json)); consumed by `mix_flow1` |
| `assembly_preview.wav` | speech + VO preview before SFX (BUILD-069, shipped) |
| `assembly.wav` | pre-master mix (`mix_flow1`) |
| `master.wav` | final export |
| `understanding/sound_design_plan.json` | coherent SFX plan root (initialized in shared analysis, expanded in Wave 5) |

## Flow 2 — `flow_2_highlights/`

| Path | Stage |
|------|-------|
| `selection.json` | ≤5 clips |
| `sfx_brief.json` | montage SFX spec |
| `sfx/*.wav` | ElevenLabs generated |
| `assembly.wav` | pre-master mix (`mix_flow2`) |
| `master.wav` | final export |

## Flow 3 — `flow_3_description/`

| Path | Stage |
|------|-------|
| `show_description.json` | podcast show description (LLM artifact) |
| `show_description.md` | plain-text export for paste into hosts (BUILD-046) |

No audio artifacts. See [pipeline/publishing/README.md](../pipeline/publishing/README.md).

## VO pickup naming

Place files in `vo_pickup/` as `{line_id}.wav` or `{targets_segment_id}.wav` matching `gap_report.json` entries with `delivery: record`.
