# Idempotent runs

Each stage marks completion:

```
ASSETS/executions/exec_NNN_TIMESTAMP/.stage_done/<stage_name>
```

Legacy runs use `data/run_NNN/.stage_done/<stage_name>` instead.

**Run discovery and resume:** [assets-and-executions.md](../cross-cutting/assets-and-executions.md).

## Re-run from a stage

```bash
python tools/run_analysis.py --run-id exec_001_20260523T120000Z --from-stage segmentation
python tools/run_flow.py --run-id exec_001_20260523T120000Z --flow flow1 --from-stage full_master_ranking
```

`--from-stage` deletes that stage's marker and downstream markers, then re-executes.

## Run allocation

**GUI (normative):** Home → **Input audio** → start execution → server allocates `exec_NNN_<UTC timestamp>` under `ASSETS/executions/`.

**CLI:** Omit `--run-id` to allocate a new execution id, or pass `--run-id exec_001_…` to continue an existing workspace.

Legacy auto-increment `run_001`, `run_002`, … under `data/` remains for old runs only.

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
| Switched flow | New `selected_flow` in `run_meta.json`; do not mix `flow_1_master/`, `flow_2_highlights/`, and `flow_3_description/` artifacts in one run without clearing |
| Relaunch app mid-run | `./scripts/run.sh` → **Previous executions** → same `run_id`; then `--from-stage` or GUI execute as needed |
