# Artifact layout

All run artifacts live under `ASSETS/executions/exec_NNN_TIMESTAMP/` (filesystem-only state). Legacy `data/run_NNN/` runs are still readable.

**ASSETS model (source audio + resume):** [assets-and-executions.md](./assets-and-executions.md) — operators pick input WAVs from `ASSETS/` in the GUI; every execution folder holds full run state for relaunch via `./scripts/run.sh`.

See also: [json-schema-coverage.md](./json-schema-coverage.md) and [json-schemas/README.md](./json-schemas/README.md) for which artifacts are schema-backed vs planned. **GUI:** [workflows/gui-surface-map.md](../workflows/gui-surface-map.md).

## ASSETS top level

```
ASSETS/
  input/                    # operator source WAVs (recommended; any name)
  executions/exec_* /       # per-run workspace (tree below)
  .gui/                     # active run pointer, server session (not stage artifacts)
```

## Run root

```
ASSETS/executions/exec_001_20260523T120000Z/
  run_meta.json                 # execution_number, input path, selected_flow, timestamps ([run_meta.schema.json](./json-schemas/run_meta.schema.json))
  gui_log.jsonl                 # centralized operator log (policy: .cursor/rules/interview-helper-mux.mdc)
  gui_job.json                  # last background execute job status (GUI job panel)
  segments/nle_edits.json       # non-linear editor state
  analysis_complete.json        # set when Wave 2 finishes
  .stage_done/                  # one empty marker file per completed stage
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
| `understanding/content_brief.json` | Yes | Content brief artifact (synced to memory) |
| `understanding/sound_design_plan.json` | Yes | Coherent sound design plan shell (BUILD-060 baseline; schema: [sound_design_plan.schema.json](./json-schemas/sound_design_plan.schema.json); expanded by Wave 5 stages) |
| `understanding/source_acoustic_profile.json` | Yes | Per-interview pacing, energy, mix contract — [source_acoustic_profile.schema.json](./json-schemas/source_acoustic_profile.schema.json); [source-derived-sonic-mix-profile.md](./source-derived-sonic-mix-profile.md) |
| `understanding/speakers.json` | Yes | Speaker roles |
| `segments/manifest.json` | Yes | Segment timeline |

See [analysis-memory.md](./analysis-memory.md). Edit in GUI **Interview profile** or stage JSON editor.

### Machine + stage artifacts

| Path | Stage |
|------|-------|
| `preclean/isolated.wav` | audio_preclean (optional) |
| `preclean/provider.json` | audio_preclean |
| `preclean/lineage.json` | audio_preclean |
| `ingest/normalized.wav` | ingest |
| `ingest/checksums.json` | ingest ([ingest_checksums.schema.json](./json-schemas/ingest_checksums.schema.json)) |
| `transcript/full.json` | transcription |
| `transcript/speakers.json` | transcription (AWS diarization) |
| `transcript/review_queue.json` | transcript_review_build |
| `transcript/review_clips/*.wav` | transcript_review_build |
| `transcript/corrections.json` | transcript_review (operator) ([transcript_corrections.schema.json](./json-schemas/transcript_corrections.schema.json)) |
| `understanding/analysis_orchestration.json` | orchestrator config / attempts |
| `understanding/context_index.json` | context padding index |
| `understanding/stage_runs/<stage>/attempt_*.json` | LLM envelope audit trail |
| `understanding/llm_calls/index.jsonl` | Index of every OpenAI call (label, path) — [llm-call-record-framework.md](./llm-call-record-framework.md) |
| `understanding/llm_calls/<stage>/attempt_NNN/<seq>_<task_kind>.json` | Full request/response + volley per API call |
| `understanding/llm_calls/<stage>/attempt_NNN/<seq>_<task_kind>.md` | Optional copy-paste markdown sidecar |
| `understanding/speakers.json` | speaker roles (LLM) |
| `understanding/content_brief.json` | content context |
| `understanding/sound_design_plan.json` | shared analysis init (BUILD-060 baseline) |
| `understanding/source_acoustic_profile.json` | source_acoustic_profile |
| `understanding/gap_evaluations.json` | missing framing |
| `understanding/gap_report.json` | optimal questions aggregate |
| `understanding/interviewer_script.txt` | human-readable VO script |
| `understanding/value_features.json` | optional; value-analysis extractor (`tools/extract_value_features.py` or auto after `content_context`) |
| `segments/boundaries.json` | boundary detection |
| `segments/manifest.json` | segment classification |

## Flow 1 — `flow_1_master/`

| Path | Stage |
|------|-------|
| `coverage_audit.json` | topic coverage audit |
| `narrative_plan.json` | narrative arc plan |
| `selection.json` | ordered segments, chapters |
| `transitions.json` | interviewer bridges |
| `podcast_sfx_brief.json` | subtle SFX spec (v1 legacy brief) |
| `sound_design/assets/{asset_id}.wav` | ElevenLabs generated (canonical SDP path) |
| `sfx/*.wav` | legacy per-flow SFX folder when SDP assets absent |
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
