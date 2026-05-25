# Feedback loops and reruns

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

Check AWS S3 upload and `aws transcribe` job status in logs.

## Re-segment

When boundaries are wrong:

```bash
python tools/run_analysis.py --from-stage boundary_detection
```

## Re-rank (Flow 1)

```bash
python tools/run_flow.py --flow flow1 --from-stage full_master_ranking
```

Requires `coverage_audit.json` and `narrative_plan.json` unless `--from-stage topic_coverage_audit`.

## Re-pick highlights (Flow 2)

```bash
python tools/run_flow.py --flow flow2 --from-stage highlight_selection
```

## Edit interview profile (themes, questions, style)

Primary file: `understanding/analysis_state.json`

- **GUI:** Interview profile panel (workspace) or stage JSON editor
- Set `meta.operator_verified: true` when themes / major_questions / style are correct
- Re-run from the first stage that should see your edits, e.g. `--from-stage segment_classification`

Also editable: `investigation_queue.json`, `content_brief.json`, `speakers.json`, `segments/manifest.json`.

## NLE timeline edits

`segments/nle_edits.json` — exclude, split, reorder in GUI.

**Target (BUILD-068):** Re-run from `full_master_ranking` or `edl_flow1` after **Save timeline** so overrides affect export.

**v1:** Edits persist on disk but may not affect pipeline until BUILD-068.

## Human override (v1)

Edit JSON artifacts directly:

- `understanding/analysis_state.json` — themes, major questions, style, narrative
- `segments/manifest.json` — force-include segment
- `flow_1_master/selection.json` — lock order
- `flow_2_highlights/selection.json` — pin clip ids

Re-run assembly from `edl` or `micro_assembly` stage after edits.
