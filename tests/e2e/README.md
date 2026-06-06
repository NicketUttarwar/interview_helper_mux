# End-to-end (E2E) testing

Autonomous journey-driven full-application tests: **Prepare → Ship** for **flow1**, **flow2**, and **flow3** using `ASSETS/input/interview.wav`.

**Entry point (repo root):** `./scripts/e2e.sh`

Related: [smoke-test.md](../../docs/workflows/smoke-test.md) · [operator-journey.md](../../docs/workflows/operator-journey.md) · [definition-of-done-signoff.md](../../docs/build-out/definition-of-done-signoff.md)

---

## Layout

```text
tests/e2e/
  README.md              ← this file
  bootstrap_venv.sh      ← isolated E2E venv (Playwright + cursor-sdk)
  requirements.txt
  pyproject.toml
  conftest.py            ← pytest path for e2e_runner
  e2e_runner/            ← orchestrator, browser driver, heal loop, …
  test_journey_driver.py ← unit tests (state machine)
  test_gate_handlers.py
  test_final_report.py
  test_live.py           ← skipped unless E2E_LIVE=1
  logs/session_*/        ← session logs + failure bundles (gitignored)
  reports/               ← final-report markdown archives
```

`scripts/e2e.sh` is a thin wrapper; all implementation lives here.

---

## Prerequisites

1. [SETUP.md](../../SETUP.md) — repo `.venv`, secrets, toolchain
2. `ASSETS/input/interview.wav`
3. `CURSOR_API_KEY` in `config/secrets/secrets.env` when heal mode is enabled (default). Use `--no-heal` to skip.

First run bootstraps `tests/e2e/.venv` and installs Playwright Chromium.

---

## Quick start

```bash
# Add CURSOR_API_KEY to config/secrets/secrets.env (see config/templates/secrets.env.example)
./scripts/e2e.sh
```

### Flags (passed through to `python -m e2e_runner`)

| Flag | Effect |
|------|--------|
| `--flows flow1,flow2,flow3` | Flows to run sequentially (default: all three) |
| `--until-stage STAGE` | Stop each flow after stage completes |
| `--resume-run-id exec_*` | Resume an in-progress execution |
| `--no-heal` | Do not invoke Cursor Agent on failures |
| `--headed` | Show browser window |

```bash
./scripts/e2e.sh --flows flow1 --until-stage assembly_preview --no-heal
./scripts/e2e.sh --resume-run-id exec_001_20260101T000000Z
```

You do **not** need `source .venv/bin/activate` before `./scripts/e2e.sh` — the script activates `tests/e2e/.venv` (and repo `.venv` for pytest preflight).

---

## What `./scripts/e2e.sh` does

1. Verifies `ASSETS/input/interview.wav`
2. Bootstraps repo `.venv` if missing (`scripts/bootstrap_venv.sh`)
3. Bootstraps / refreshes `tests/e2e/.venv` (Playwright + cursor-sdk)
4. Builds GUI static bundle if missing (`scripts/build_gui.sh`)
5. Runs `tools/check_prerequisites.sh` and validates required secrets + AWS auth
6. Runs E2E helper `pytest` (must pass)
7. Starts `./scripts/run.sh --no-browser`
8. Playwright drives `http://127.0.0.1:8765` + REST API for gates
9. Runs **flow1 → flow2 → flow3** by default (dismisses optional pre-clean offers; uses `interview.wav` via API)
10. On failure: failure bundle → Cursor Agent heal → restart → resume
11. Verifies masters / show description per flow
12. Writes `tests/e2e/reports/<session>_final-report.md`

---

## Unit tests only (seconds)

```bash
source .venv/bin/activate
pytest tests/e2e/test_journey_driver.py tests/e2e/test_gate_handlers.py tests/e2e/test_final_report.py -q
```

Live full run (hours, real APIs):

```bash
E2E_LIVE=1 pytest tests/e2e/test_live.py -q
```

Prefer `./scripts/e2e.sh` for the full autonomous path.

---

## Logs and reports

| Path | Contents |
|------|----------|
| `tests/e2e/logs/session_<id>/` | Session root |
| `…/failures/*.json` | Journey snapshot, job, log tail, screenshot |
| `…/heal/*_transcript.txt` | Cursor Agent heal output |
| `tests/e2e/reports/<session>_final-report.md` | Final report (root cause, fixes, files changed) |

---

## Environment

| Variable / key | Default | Purpose |
|----------------|---------|---------|
| `CURSOR_API_KEY` in `config/secrets/secrets.env` | — | Cursor Agent self-heal (`export CURSOR_API_KEY` still overrides) |
| `E2E_MAX_HEAL_ATTEMPTS` | `5` | Per failure-site heal cap |

---

## Manual bootstrap (optional)

```bash
bash tests/e2e/bootstrap_venv.sh
source tests/e2e/.venv/bin/activate
python -m e2e_runner --help
```
