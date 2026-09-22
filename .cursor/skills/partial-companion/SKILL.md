---
name: partial-companion
description: >-
  Watch a partially_accelerated Partial Zero proof run. Classify stalls; emit
  Decision Packets for code intervenes; never patch without decision_log verdict.
  Invoke with /partial-companion RUN=<exec_id>.
disable-model-invocation: true
---

# Partial Companion — Partial Zero

Campaign: [`.cursor/plans/partial_zero/`](../../plans/partial_zero/)  
Law: error-free **partially_accelerated** without forensics. Code is SSOT.

## Invoke

```
/partial-companion RUN=<exec_id> STAGE=<id> PHASE=<phase_id>
Mode=partially_accelerated. Same run only.
Read STEP_OFF.md + decision_queue.md + maps/<stage> if present + cousin_matrix.md.
Classify: expected_gate | open_route | unmapped | honesty_cousin | cut_revisit.
If code fix needed: Decision Packet + STEP_OFF; no patch until verdict.
Max 1 family per stall. Cap ~5 code families → go/no-go STEP_OFF (operator decides).
Do not browse other exec_* unless operator names them as HINT.
Do not start forensics.
```

## Classify → action

| Class | Action |
|-------|--------|
| expected_gate | Instruct human (G0 / framing / G1 / G-Publish); no code |
| open_route | Packet + cousin list; close family after verdict |
| honesty_cousin | Root SSOT/junction packet; never surface-only test_iNN |
| unmapped | Map delta + family entry + packet |
| cut_revisit | Pause for CUT economics Decision Packet |

## Always end with

YOUR NEXT ACTIONS + COPY-PASTE `PROGRESS_NOW` / `DIG_DEEPER` / (after verdict) `IMPLEMENT_NEXT` from STEP_OFF.md.

## Observability (active run only)

- `ASSETS/executions/<run>/gui_job.json`
- `operator/execution_status.json`
- logs / incompleteness
- phase scorecard row for current phase
