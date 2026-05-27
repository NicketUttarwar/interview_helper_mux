# Idempotent runs

Each stage marks completion:

```
data/run_NNN/.stage_done/<stage_name>
```

## Re-run from a stage

```bash
python tools/run_analysis.py --run-id run_001 --from-stage segmentation
python tools/run_flow.py --run-id run_001 --flow flow1 --from-stage full_master_ranking
```

`--from-stage` deletes that stage's marker and downstream markers, then re-executes.

## Run allocation

New runs auto-increment: `run_001`, `run_002`, … under `data/`.

Override with `--run-id run_001` to continue an existing workspace.

## Safe partial runs

| Scenario | Action |
|----------|--------|
| Re-run optional pre-clean (full source) | `--from-stage audio_preclean` (then ingest + downstream) |
| Re-run pickup-only pre-clean | `audio_preclean` with `scope: vo_pickup` (then `vo_ingest`; does not invalidate transcript) |
| Operator dismissed pre-clean offer | No marker change; continue current lineage |
| Transcribe failed | `--from-stage transcribe` |
| STT corrections changed | `--from-stage transcript_review` (re-sign-off) or `transcript_review_build` to rebuild clips |
| Changed prompts only | `--from-stage <llm_stage>` |
| New VO files added | `--from-stage vo_ingest` |
| Switched flow | New `run_meta.json`; do not mix `flow_1_master/`, `flow_2_highlights/`, and `flow_3_description/` artifacts in one run without clearing |
