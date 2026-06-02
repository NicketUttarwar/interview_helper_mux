# E2E automation

Autonomous journey-driven end-to-end runner for the full operator path (Prepare → Ship) across **flow1**, **flow2**, and **flow3**.

**Entry point:** `./scripts/e2e.sh`  
**Package:** [`E2E_RUN/`](../E2E_RUN/) (isolated venv, mirrors [`CURSOR_EXECUTE/`](../CURSOR_EXECUTE/))

Related: [smoke-test.md](./smoke-test.md) · [operator-journey.md](./operator-journey.md) · [definition-of-done-signoff.md](../build-out/definition-of-done-signoff.md)

---

## Prerequisites

1. [SETUP.md](../../SETUP.md) — venv, secrets, toolchain
2. `ASSETS/input/interview.wav` (or pass `--input`)
3. `./tools/check_prerequisites.sh` (run automatically by `e2e.sh`)
4. `CURSOR_API_KEY` when heal mode is enabled (default). Use `--no-heal` to skip agent fixes.

First run bootstraps `E2E_RUN/.venv` and installs Playwright Chromium.

---

## Quick start

```bash
export CURSOR_API_KEY="cursor_..."   # optional if --no-heal
./scripts/e2e.sh
```

### Common flags

| Flag | Effect |
|------|--------|
| `--flows flow1,flow2,flow3` | Flows to run sequentially (default: all three) |
| `--until-stage STAGE` | Stop each flow after stage completes (dev smoke) |
| `--resume-run-id exec_*` | Resume an in-progress execution |
| `--no-heal` | Do not invoke Cursor Agent on failures |
| `--headed` | Show browser window |

Examples:

```bash
./scripts/e2e.sh --flows flow1 --until-stage assembly_preview --no-heal
./scripts/e2e.sh --resume-run-id exec_001_20260101T000000Z
```

---

## What it does

1. Runs `pytest tests/` (fast preflight, ignores live E2E)
2. Starts `./scripts/run.sh --no-browser`
3. Opens `http://127.0.0.1:8765` (Playwright)
4. For each flow: creates `exec_*` from `interview.wav`, drives journey via API + browser
5. Resolves gates (G0, G1, G2, profile, pre-clean dismiss, handoffs) via REST first
6. On stall/error: failure bundle → Cursor Agent heal → restart server → resume
7. Verifies artifacts (`verify_master.py`, `validate_show_description.py`)
8. Writes **final report** to `docs/e2e-reports/<session>_final-report.md`

---

## Logs and reports

| Path | Contents |
|------|----------|
| `E2E_RUN/logs/session_<id>/` | Session root |
| `…/failures/*.json` | Failure bundles (journey, job, log tail, screenshot) |
| `…/heal/*_transcript.txt` | Cursor Agent heal output |
| `…/final-report.md` | Session copy of final report |
| `docs/e2e-reports/<session>_final-report.md` | Human-readable archive |

The final report lists every heal incident with **root cause**, **severity**, **fix applied**, and **files changed**. Clean runs still get a summary report.

---

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `CURSOR_API_KEY` | — | Cursor Agent heal |
| `E2E_MAX_HEAL_ATTEMPTS` | `5` | Per failure-site heal cap (orchestrator) |
| `MUX_FRESH_SESSION` | `1` on new session | Clears GUI session files |

---

## Automated tests (runner itself)

```bash
pytest tests/test_e2e_journey_driver.py tests/test_e2e_gate_handlers.py tests/test_e2e_final_report.py -q
```

Live full run (hours, real APIs):

```bash
E2E_LIVE=1 pytest tests/test_e2e_live.py -q   # placeholder; prefer ./scripts/e2e.sh
```

---

## Architecture notes

- **API is source of truth** for `journey.next_action`, `blocking`, `job.status`
- **Browser** clicks journey CTA and checkpoint modals (`data-testid` on key controls)
- **Three flows** = three separate `exec_*` runs (same WAV), one browser session
- Heal loop reuses `cursor-sdk` patterns from `CURSOR_EXECUTE`

See plan: autonomous E2E runner (implementation complete in `E2E_RUN/src/e2e_runner/`).
