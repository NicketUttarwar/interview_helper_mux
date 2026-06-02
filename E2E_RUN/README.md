# E2E_RUN

Isolated runner for autonomous full-application E2E tests. Uses Playwright + HTTP API against `./scripts/run.sh`.

From repo root:

```bash
export CURSOR_API_KEY="cursor_..."   # required when heal mode is on (default)
./scripts/e2e.sh
./scripts/e2e.sh --flows flow1 --until-stage assembly_preview
./scripts/e2e.sh --resume-run-id exec_001_20260101T000000Z --no-heal
```

First run creates `E2E_RUN/.venv` via `bootstrap_venv.sh`.

Logs: `E2E_RUN/logs/session_<timestamp>/`  
Final report: `docs/e2e-reports/<session>_final-report.md`

See [docs/workflows/e2e-automation.md](../docs/workflows/e2e-automation.md).
