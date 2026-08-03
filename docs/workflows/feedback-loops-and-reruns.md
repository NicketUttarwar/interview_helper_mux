# Feedback loops and reruns

See also: [troubleshooting.md](./troubleshooting.md) when a re-run does not fix the issue.

## Reuse prior execution (same source audio)

When starting a new `exec_*` on the same WAV, the GUI can **reuse** completed stage outputs from an earlier run (matched by `source_audio_hash`) instead of re-running — [stage-execution-reuse.md](./stage-execution-reuse.md).

CLI auto-accept all reusable stages:

```bash
interview-mux analysis --run-id exec_002_… --reuse-from exec_001_…
```

To clear a reuse decision and run fresh: open the stage in GUI → **Run fresh instead**, or invalidate with `--from-stage <stage_id>`.

**Invalidate / redo from stage** also: archives downstream artifact files to `.archived/<timestamp>/` (recorded in `run_meta.invalidation_archive`), discards `.pending_writes/` from that stage onward, and clears `pending_write_approval` so execute is not blocked.

## Re-run pre-clean (quality)

When the operator accepts a background-noise offer:

| Scope | Re-run from |
|-------|-------------|
| Full source | `audio_preclean` then `ingest` (invalidates transcript + analysis) |
| VO pickup only (typical after G1) | `audio_preclean` with `scope: vo_pickup` then `vo_ingest` |
| Before mix only | `normalized_rebuild` or full source per operator choice |

See [audio_preclean/README.md](../pipeline/audio_preclean/README.md).

## Re-transcribe

When transcript QC fails (no speakers, broken timestamps):

```bash
python tools/run_analysis.py --from-stage transcribe
```

Check local STT logs under the run (`transcript/`) and `ASSETS/local_speech` runtime health — cloud `aws transcribe` / S3 upload for STT were removed.

## Word-level STT fixes (G0 dock)

For localized mishearings (not full re-transcribe): open **Transcript review**, use the synced dock or **Fix similar words** batch replace, then complete G0. Dock edits write `transcript/full.json` immediately via `PATCH …/transcript/words`. See [transcript-review.md](../pipeline/transcription/transcript-review.md).

## Re-segment

When boundaries are wrong:

```bash
python tools/run_analysis.py --from-stage boundary_detection
```

## Re-rank (Flow 1)

```bash
python tools/run_delivery.py --flow flow1 --from-stage full_master_ranking
```

Requires `coverage_audit.json` and `narrative_plan.json` unless `--from-stage topic_coverage_audit`.

## Re-pick highlights (Flow 2)

```bash
python tools/run_delivery.py --flow flow2 --from-stage REMOVED_highlight_selection
```

## Edit interview profile (themes, questions, style)

Primary file: `understanding/analysis_state.json`

- **GUI:** Interview profile panel (workspace) or stage JSON editor
- Set `meta.operator_verified: true` when themes / major_questions / style are correct
- Re-run from the first stage that should see your edits, e.g. `--from-stage segment_classification`

Also editable: `investigation_queue.json`, `content_brief.json`, `speakers.json`, `segments/manifest.json`.

Saves validate against JSON Schema (server) and Zod (GUI). See [artifact-generation-and-validation.md](../cross-cutting/artifact-generation-and-validation.md).

## Fill incomplete LLM artifacts (gap-fill)

When Stage outputs shows **partial** for a JSON file:

1. **GUI:** Click **Fill gaps** on that row (`POST …/fill-artifact-gaps`).
2. **CLI:** Re-run the producing stage, e.g. `python tools/run_analysis.py --run-id <id> --from-stage content_context`.

The pipeline also re-runs a done LLM stage automatically when `should_run_stage_for_artifact()` is true (missing file, schema errors, or semantic gaps). Spec: [artifact-generation-and-validation.md](../cross-cutting/artifact-generation-and-validation.md).

## NLE timeline edits

`segments/nle_edits.json` — exclude, split, reorder, trim in the Timeline tab.

**Apply timeline edits** (`POST …/execute` with `mode: nle_apply`) runs a light cascade by default:

1. `full_master_ranking` — only when order, exclude, or split changed
2. `edl` — always when operator edits exist
3. `assembly_preview` — listen-before-SFX preview after EDL rebuild

Optional `nle_full_refresh: true` or `nle_apply_mode: full_refresh` also runs `transitions` and `edl_narrative_audit` before EDL build. Use `nle_apply_mode: trim_only` to rebuild EDL + `assembly_preview.wav` without re-running `full_master_ranking`.

Manual stage reruns (`full_master_ranking`, `edl`) remain available from the pipeline sidebar.

## Human override (v1)

Edit JSON artifacts directly:

- `understanding/analysis_state.json` — themes, major questions, style, narrative
- `segments/manifest.json` — force-include segment
- `master/selection.json` — lock order
- `REMOVED_flow2/selection.json` — pin clip ids

Re-run assembly from `edl` or `micro_assembly` stage after edits.
