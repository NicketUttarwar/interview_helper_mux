# Operator action catalog

Machine-readable export: [operator_action_catalog.json](./operator_action_catalog.json) (105+ entries).

## Naming convention

| Field | Rule | Example |
|-------|------|---------|
| `action_id` | `<domain>.<verb>` lowercase snake | `write_approval.approve` |
| `description` | One operator-readable line | Flush staged files to disk and mark stage complete |
| `implementation` | `module.function` or route | `write_staging.approve_stage_writes` |
| `stage` | Pipeline stage id or `*` | `audio_preclean` |
| `origin` | `gui`, `api`, `cli`, `subprocess`, `pipeline` | `gui` |

GUI buttons use `data-action-id` matching catalog entries. AppShell captures clicks as a safety net.

## Forbidden logging patterns (do not use)

| Pattern | Why | Use instead |
|---------|-----|-------------|
| `print()` for operator status | Not in `gui_log.jsonl` | `operator_log()` / `RunContext.log()` |
| Bare `logging.info` without `ctx.log` | Invisible in GUI | `operator_log()` when run workspace exists |
| Second parallel status file | Policy violation | `gui_log.jsonl` only (+ `operator/action_trace.jsonl` index) |
| `appendClientLog` 30s message dedupe | Hides legitimate repeats | Dedupe on `action_id` only (5s); never dedupe `error`/`action` |
| Raw `subprocess.run` in `stages/` | No streamed operator log | `operator_subprocess.run_command` |

## Audit

```bash
python tools/audit_operator_action_catalog.py
python tools/audit_operator_logging.py
```

## Related

- [operator-logging-master-plan.md](./operator-logging-master-plan.md)
- [gui-surface-map.md](../workflows/gui-surface-map.md) — global Activity dock + dump button
