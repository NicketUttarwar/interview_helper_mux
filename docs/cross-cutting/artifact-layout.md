# Artifact layout

All run artifacts live under `ASSETS/executions/exec_NNN_TIMESTAMP/` (filesystem-only state). Legacy `data/run_NNN/` runs are still readable.

## Run root

```
ASSETS/executions/exec_001_20260523T120000Z/
  run_meta.json                 # execution_number, input path, selected_flow, timestamps
  gui_log.jsonl                 # append-only prompt log (survives browser refresh)
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
```

## Shared analysis (Wave 2)

### Operator-editable profile (verify and adjust per interview)

| Path | Editable | Purpose |
|------|----------|---------|
| `understanding/analysis_state.json` | **Yes** | Themes, major questions, style, narrative — main interview profile |
| `understanding/investigation_queue.json` | Yes | Open investigations / rerun hints |
| `understanding/content_brief.json` | Yes | Content brief artifact (synced to memory) |
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
| `ingest/checksums.json` | ingest |
| `transcript/full.json` | transcription |
| `transcript/speakers.json` | transcription (AWS diarization) |
| `transcript/review_queue.json` | transcript_review_build |
| `transcript/review_clips/*.wav` | transcript_review_build |
| `transcript/corrections.json` | transcript_review (operator) |
| `understanding/analysis_orchestration.json` | orchestrator config / attempts |
| `understanding/context_index.json` | context padding index |
| `understanding/stage_runs/<stage>/attempt_*.json` | LLM envelope audit trail |
| `understanding/speakers.json` | speaker roles (LLM) |
| `understanding/content_brief.json` | content context |
| `understanding/gap_evaluations.json` | missing framing |
| `understanding/gap_report.json` | optimal questions aggregate |
| `understanding/interviewer_script.txt` | human-readable VO script |
| `segments/boundaries.json` | boundary detection |
| `segments/manifest.json` | segment classification |

## Flow 1 — `flow_1_master/`

| Path | Stage |
|------|-------|
| `coverage_audit.json` | topic coverage audit |
| `narrative_plan.json` | narrative arc plan |
| `selection.json` | ordered segments, chapters |
| `transitions.json` | interviewer bridges |
| `podcast_sfx_brief.json` | subtle SFX spec |
| `sfx/*.wav` | ElevenLabs generated |
| `edl.json` | edit decision list (target: speech + VO placements, BUILD-067) |
| `assembly_preview.wav` | speech + VO preview before SFX (planned, BUILD-069) |
| `assembly.wav` | pre-master mux |
| `master.wav` | final export |
| `understanding/sound_design_plan.json` | coherent SFX plan (planned, BUILD-060) |

## Flow 2 — `flow_2_highlights/`

| Path | Stage |
|------|-------|
| `selection.json` | ≤5 clips |
| `sfx_brief.json` | montage SFX spec |
| `sfx/*.wav` | ElevenLabs generated |
| `assembly.wav` | micro-assembly |
| `master.wav` | final export |

## VO pickup naming

Place files in `vo_pickup/` as `{line_id}.wav` or `{targets_segment_id}.wav` matching `gap_report.json` entries with `delivery: record`.
