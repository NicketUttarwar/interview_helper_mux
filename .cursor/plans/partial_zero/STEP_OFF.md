# STEP_OFF — Partial Zero

updated: 2026-09-21T23:21:00Z  
campaign_status: companion_watching  
run_id: exec_13168_d19c15b58ab4_20260921T211330Z  
blocked_on:
  - none (healthy advance; fill_gaps proved after DP-BUD1 A)
last_batch: DP-BUD1 = A (implemented; gap_report landed)  
what_you_can_do_now: Let delivery continue; paste PROGRESS_NOW on stall / G1

decided:
  - DP-BUD1 = A (implemented — fingerprint reclaim + refuse≠Finished)
  - DP-GAP-PICKUP-CONFIRM = A (implemented)
  - DP-A2 = A (implemented)
  - DP-A1 = custom → Mix–Junction Seat Authority (implemented; footguns 1–9 hardened)
  - DP-B4 custom → DP-DONE-AUTHORITY 1A+2A+3A (implemented; footguns 1–9)
  - DP-SOUND-SDP-CUE = custom A+ (implemented)
  - DP-LOCAL-ML-RETRY = A (implemented; footguns 1–9 hardened)
  - DP-A3 = custom A′′ Global Freeze (implemented)
  - DP-A4 = A thorough (implemented; footguns 1–7 hardened)
  - DP-A5 = A (retained HEAD; pin test)
  - DP-VO1 = A+ (implemented; footguns 1–5)
  - DP-B1+B2+B3+B6 = A batch PIN_PREMATURE (implemented)
  - DP-NESTED-SYNTH = A + residuals 1–3 (implemented)
  - DP-LAYUP-ADJ = A (implemented)
  - DP-C1+C2+C3+C4 = A ESR_POST_MASTER batch (implemented)
  - DP-C5 = A (implemented)
  - DP-BUILD-ASSEMBLY-FRESHNESS = custom HAU (implemented + footguns ×6)
  - DP-PRE-PARTIAL = A (launch unlocked)

soak_gates (stop → new DP; do not silent-ignore):
  - BUDGET_THRASH residual after reclaim (infinite thrash on same fp) → new DP
  - Premix commitment diverge → incomplete_cut storms → premix residual DP
  - Dual-render / seating surprise beyond HAU → new MIX packet

do_not_do:
  - do not start forensics
  - do not reuse an old exec_* (fresh only for new campaigns)
  - do not patch mid-run without a logged verdict

## COPY-PASTE INTO CURSOR AGENT

### LAUNCH (operator / you)
1. Fresh assets run — **new** `exec_*` (do not continue a forensics folder).
2. Mode: **partially-accelerated** (Partial).
3. Brain / homunculus: **0.2.0**.
4. `MUX_FORENSICS` unset or `0`.
5. Start via GUI Start tab (Partial) or your usual Partial driver; note the run id under `ASSETS/executions/`.
6. Human gates as they appear: **G0** → framing → **G1** (as needed) → later **G-Publish** if you reach ship.

### COMPANION_NEXT (after you have exec_id)
```
/partial-companion RUN=<exec_id>
Mode=partially_accelerated. Same run only.
Read .cursor/plans/partial_zero/STEP_OFF.md and decision_queue.md.
Soak-gates: BUDGET_THRASH residual, premix→incomplete_cut, dual-render surprises.
Classify stalls; Decision Packet if code fix needed; no patch until verdict.
Do not start forensics. Goal: error-free partially_accelerated.
```

### PROGRESS_NOW
```
/partial-zero-progress
Read .cursor/plans/partial_zero/STEP_OFF.md and decision_queue.md.
Next unit: companion watch exec_13168 delivery (topic_coverage → VO / G1 if offered).
Goal: error-free partially_accelerated without forensics.
Do not patch unless implementing a logged verdict. Do not start forensics.
```
