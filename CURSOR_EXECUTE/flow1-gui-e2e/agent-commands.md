# Flow 1 GUI E2E — CURSOR_EXECUTE command queue

**Run:**

```bash
./CURSOR_EXECUTE/flow1-gui-e2e/run.sh
```

---

## Command 1 — E2E-01: SETUP preflight

```text
Read:
@CURSOR_EXECUTE/flow1-gui-e2e/01-SETUP-preflight.md
@CURSOR_EXECUTE/flow1-gui-e2e/00-INDEX.md
@.cursor/rules/interview-helper-mux.mdc
@docs/cross-cutting/anchored-toolchain.md

Run Flow 1 GUI E2E preflight per 01-SETUP-preflight.md.
Fix any failing checks that block automation (deps, playwright, dummy VO).
Update 00-INDEX.md step 01 to [x] when done.
```

---

## Command 2 — E2E-02: Driver readiness review

```text
Read:
@CURSOR_EXECUTE/flow1-gui-e2e/02-GUI-JOURNEY.md
@CURSOR_EXECUTE/flow1-gui-e2e/driver/gui_driver.py
@docs/workflows/operator-gates.md
@docs/workflows/gui-surface-map.md

Review GUI E2E driver coverage vs 02-GUI-JOURNEY.md.
Add missing data-testid hooks if handlers lack stable selectors.
Do not run the full pipeline in this command unless operator asked.
```

---

## Command 3 — E2E-03: FIX blocker

```text
Read:
@CURSOR_EXECUTE/flow1-gui-e2e/03-FIX-blocker.md
@CURSOR_EXECUTE/flow1-gui-e2e/blockers/
@docs/workflows/troubleshooting.md
@docs/build-out/stage-registry.md
@.cursor/rules/interview-helper-mux.mdc

Fix the latest open BLOCKER ticket under CURSOR_EXECUTE/flow1-gui-e2e/blockers/.
Read gui_log.jsonl for the cited run_id.
Fill Root cause, Fix, and Fix comment in the blocker file; set Status: fixed.
Run targeted pytest; rebuild GUI if frontend changed.
```

---

## Command 4 — E2E-04: FINISH verify

```text
Read:
@CURSOR_EXECUTE/flow1-gui-e2e/04-FINISH-verify.md
@CURSOR_EXECUTE/flow1-gui-e2e/00-INDEX.md
@docs/build-out/definition-of-done-signoff.md

Run FINISH verification per 04-FINISH-verify.md for the completed run_id.
Update 00-INDEX.md success criteria and step 04 when master.wav passes.
```
