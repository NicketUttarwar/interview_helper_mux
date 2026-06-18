# Step 03 — FIX blocker

**When:** Driver exits with code **2** and writes `blockers/BLOCKER-NNN-*.md`.

---

## Agent directive (E2E-03)

1. Read the latest open blocker file and attached screenshot
2. Read `gui_log.jsonl` tail for the `run_id`
3. Fix root cause in app code/UI (not config bypasses for gates)
4. Add `data-testid` if selector was fragile
5. Run targeted `pytest` for touched areas
6. Rebuild GUI if `frontend/` changed: `./scripts/build_gui.sh`
7. Fill **Root cause**, **Fix**, and **Fix comment** in blocker file; set **Status: fixed**

---

## Blocker markdown schema

```markdown
# BLOCKER-NNN — slug

- **Status:** open | fixed | waived
- **Detected at:** ISO timestamp
- **run_id:** exec_…
- **stage:** stage_id
- **job_status:** gate | error | stuck
- **Screenshot:** logs/session_…/screenshots/NNN.png

## Symptom

## Root cause

## Fix

## Fix comment

## Resume
./CURSOR_EXECUTE/flow1-gui-e2e/run.sh --resume
```

---

## Resume protocol

After **Status: fixed**, operator or `run.sh --resume` restarts driver from `driver/state.json` without creating a new execution (same `run_id`).
