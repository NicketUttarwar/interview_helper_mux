# E2E automation

Autonomous full-application E2E tests live under **[tests/e2e/README.md](../../tests/e2e/README.md)**.

**Entry point:** `./scripts/e2e.sh`

That script bootstraps `tests/e2e/.venv`, runs the journey orchestrator in `tests/e2e/e2e_runner/`, and writes reports to `tests/e2e/reports/`.

See also: [smoke-test.md](./smoke-test.md) · [operator-journey.md](./operator-journey.md)
