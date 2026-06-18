# Flow 1 GUI E2E — execution index

**Start here.** Automated end-to-end Flow 1 (full podcast) through the **real React GUI** using Playwright clicks and dummy gate values.

**Input asset:** `ASSETS/notebooklm_original_interview_2024.wav`

**One command:**

```bash
./CURSOR_EXECUTE/flow1-gui-e2e/run.sh
```

---

## Operator kill-switch

The terminal prints **STEP / ACTION / WAIT / GATE** lines in real time. If you dislike what automation is doing, press **Ctrl+C**. The harness stops the browser and GUI server, saves `driver/state.json`, and prints a `--resume` one-liner.

Use `--headed` to watch clicks in a visible browser while logs print alongside.

## Execution screenshots (ASSETS)

During a real run (not `--dry-run`), full-page PNG captures are saved under `ASSETS/flow1-gui-e2e-screenshots/sessions/<session_id>/`. That folder is gitignored at the repo root and runs as its **own local git repo**. Screenshots are taken after button clicks, at most **once every 2 minutes**. `run.sh` commits the archive at the end (and on Ctrl+C).

---

## Sequence

| Step | File | What | Status |
|------|------|------|--------|
| **00** | [00-INDEX.md](./00-INDEX.md) | This index | — |
| **01** | [01-SETUP-preflight.md](./01-SETUP-preflight.md) | Environment baseline | [x] |
| **02** | [02-GUI-JOURNEY.md](./02-GUI-JOURNEY.md) | Stage map + auto-actions | [x] |
| **03** | [03-FIX-blocker.md](./03-FIX-blocker.md) | Blocker fix directive | [x] |
| **04** | [04-FINISH-verify.md](./04-FINISH-verify.md) | master.wav verification | [x] |

**Queue:** [agent-commands.md](./agent-commands.md) · **Runner:** [CURSOR_EXECUTE/run.sh](../run.sh)

---

## Success criteria

- [ ] `./CURSOR_EXECUTE/flow1-gui-e2e/run.sh` completes with `flow_1_master/master.wav` verified
- [ ] Pipeline progressed via GUI clicks only (driver never calls `POST /execute`)
- [ ] Terminal showed continuous STEP/ACTION/WAIT/GATE lines; Ctrl+C saves resume state
- [ ] Blockers in [blockers/](./blockers/) have fix comments when encountered
- [ ] Resume works after intentional kill mid-run

---

## Standard companions

| Path | Role |
|------|------|
| [docs/workflows/operator-gates.md](../../docs/workflows/operator-gates.md) | G0–G2, profile, G1.5 |
| [docs/workflows/gui-surface-map.md](../../docs/workflows/gui-surface-map.md) | UI ↔ API |
| [docs/workflows/api-reference.md](../../docs/workflows/api-reference.md) | `/api/*` |
| [docs/build-out/stage-registry.md](../../docs/build-out/stage-registry.md) | Stage ids |
| [docs/workflows/troubleshooting.md](../../docs/workflows/troubleshooting.md) | Symptom playbook |
| `.cursor/rules/interview-helper-mux.mdc` | Repo constraints |

---

## Flags

| Flag | Purpose |
|------|---------|
| `--dry-run` | Print planned steps; no server/browser |
| `--resume` | Continue from `driver/state.json` |
| `--no-fix` | Driver only; skip E2E-03 agent on blocker |
| `--headed` | Visible Chromium |
| `--verbose` | WAIT line every poll |
| `--max-fix-rounds N` | Agent fix iterations (default 10) |

## Driver config (`driver/config.yaml`)

| Key | Default | Purpose |
|-----|---------|---------|
| `api_poll_max_consecutive_failures` | 3 | Consecutive `/api/runs/{id}` or `/job` failures before blocker exit |
| `api_request_timeout_s` | 30 | Per-request HTTP timeout for driver API client |
