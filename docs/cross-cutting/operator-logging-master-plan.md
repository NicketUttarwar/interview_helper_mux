# Operator logging master plan (shipped)

Implementation of LOG-00 … LOG-07: unified operator logging, action trace sidecar, global Activity dock, dump-last-step forensics.

## Architecture

- **Canonical stream:** `gui_log.jsonl` via `operator_log()` (Python) and `traceAction()` (GUI).
- **Forensics index:** `operator/action_trace.jsonl` via `operator_action_trace.py`.
- **Catalog:** `docs/cross-cutting/operator_action_catalog.json` + [operator-action-catalog.md](./operator-action-catalog.md).

## Key code

| Component | Path |
|-----------|------|
| Python log entry | `src/interview_mux/operator_log.py` |
| Action trace | `src/interview_mux/operator_action_trace.py` |
| GUI trace | `frontend/src/operator/traceAction.ts` |
| Global dock | `frontend/src/components/activity/GlobalActivityDock.tsx` |
| Dump API | `POST /api/runs/{id}/action-trace/dump-last` |

## Verify

```bash
python tools/audit_operator_action_catalog.py
python tools/audit_operator_logging.py
.venv/bin/python -m pytest tests/test_operator_action_trace.py tests/test_ingest.py -q
```

See [operator-logging-verification.md](../workflows/operator-logging-verification.md).
