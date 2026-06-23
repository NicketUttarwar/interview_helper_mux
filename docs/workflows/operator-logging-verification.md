# Operator logging verification

Manual and automated checks after checkpoint-continuation hardening.

## Automated

```bash
./tools/check_prerequisites.sh
python tools/audit_operator_action_catalog.py
python tools/audit_operator_logging.py
.venv/bin/python -m pytest tests/test_operator_action_trace.py tests/test_ingest.py tests/test_operator_trace.py tests/test_write_staging.py tests/test_operator_checkpoint_continuation.py tests/test_ui_truth_invariants.py -q
cd frontend && npm test -- --run src/utils/operatorActionTrace.test.ts src/utils/checkpointContinuation.test.ts src/utils/gateAdvance.test.ts src/utils/attentionQueue.test.ts src/utils/stageSubsteps.test.ts
```

## Manual verification matrix (M1–M16)

| # | Flow | Steps | Pass criteria |
|---|------|-------|---------------|
| M1 | preclean → save | Accept preclean, save 3 files | ingest starts; modal closes; no 409 on single click |
| M2 | ingest → save | Complete ingest, save | transcribe or reuse gate; not stuck on save |
| M3 | transcribe → save | If staged outputs | save → next stage |
| M4 | stage_reuse | Transcribe with prior run | accept/decline → never stuck without CTA |
| M5 | handoff | Any LLM stage with handoff paths | ack → next stage runs or next gate focused |
| M6 | G0 transcript | Complete review | modal closes; pipeline advances |
| M7 | G0.5 disfluency | Complete review | same |
| M8 | G1 VO pickup | Record all lines | continue → G2 or next |
| M9 | G2 flow select | Pick flow | modal closes; flow stages unlock |
| M10 | analysis profile | Verify profile | advance to flow |
| M11 | preclean dismiss | Dismiss before ingest | ingest offered / runs |
| M12 | long audio ingest hash | After save | Activity shows hash %; Save disabled; no double-save 409 |
| M13 | server restart mid-save | Kill during flush | reconcile → interrupted job; Retry works |
| M14 | dismiss modal mid-checkpoint | Close modal | StepActionHeader reopens checkpoint |
| M15 | LiveStatusBar save CTA | From Logs tab | same as panel save |
| M16 | Dump last step | After M1 | `write_approval.approve` → `pipeline.execute` → `ingest.hash` |

## Dump last step

1. Click **Dump last step** in Activity dock or Logs tab.
2. Confirm new log block lists `action_id`, `stage`, `command`/`http`, `description`.
3. After preclean save, expect `write_approval.approve` → `pipeline.execute_stage` / `ingest.hash`.

## Global dock

Activity panel visible on Start/Executions/Logs when run active.
