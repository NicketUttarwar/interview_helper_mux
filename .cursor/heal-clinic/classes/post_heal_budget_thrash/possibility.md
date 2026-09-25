# Possibility Map — post_heal_budget_thrash

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: hint_only_if_named  
written: 2026-09-22

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## Plain-language summary (for the operator)

- In one sentence, what is broken: After heal says **recovered**, the run still treats that attempt as thrash fuel (R12c identical bump + recovery attempt count + no budget-epoch / sticky clear), so the same product fingerprint can hit max_invokes / identical×N / sticky halt.
- In one sentence, what “fixed” looks like: Honest heal success either **does not burn** the same accounts as a failed heal, or **progress-gates a reclaim** (like BUD-1 does on fingerprint flip) — without reopening false-recovered (HC-HEAL-SUCCESS stays).

---

## 1. Mechanism census (HEAD)

| Surface / function | Role in this class | Tag | Path:line |
|--------------------|--------------------|-----|-----------|
| `finalize_heal_success` | Sole gate for `recovered=True`; **does not** reset budget / identical / sticky | `IN_CODE` | `heal_success.py:216-280` |
| `handle_stage_failure` → `_append_action` | Always logs action; recovered and escalate both append | `IN_CODE` | `recovery_controller.py:1950-1986` |
| `_mirror_recovery_to_identical_failures` (R12c) | Every recovery log row for classified playbooks bumps identical class count to match log — **including recovered** | `IN_CODE` | `recovery_controller.py:469-503` |
| `attempt_count` / `budget_exhausted` | `max(log_count, identical_count)`; default recovery budget **1**, transient **3**; recovered rows count | `IN_CODE` | `recovery_controller.py:539-569` |
| Escalate-only `record_identical_failure` | Extra reason-sig when **not** recovered; classified path relies on R12c | `IN_CODE` | `recovery_controller.py:1962-1983` |
| Pipeline `status=="recovered"` | Re-run or raise `Complete {resume} before {stage}` → more invokes | `IN_CODE` | `pipeline.py` recovered branch (~655-702) |
| Homunculus `dispatch_stage` recover | Recursive resume (depth≤2) on recovered | `IN_CODE` | `homunculus/runtime.py` recover path |
| Driver `_try_recovery` | Same `handle_stage_failure`; resume on recovered | `IN_CODE` | `tools/full_auto_driver.py` |
| `count_identity` / `check_dispatch` | Invoke cap; ledger is declared source of counts | `IN_CODE` | `homunculus/budget.py`, `homunculus/ledger.py` |
| `count_attempts` / `dispatch_cap_refusal` | Walk door: started rows after epoch burn | `IN_CODE` | `homunculus/budget.py:152+` |
| `stamp_budget_epoch` | Only honest invoke reset; **not** tied to heal success | `IN_CODE` | `homunculus/ledger.py` |
| `reclaim_budget_on_product_flip` / BUD-1 | Fingerprint/memo-stale → epoch + memo clear; Partial does **not** wipe ×3 | `IN_CODE` | `identical_failures.py:963-1036` |
| `evaluate_dispatch` once-per-ctx reclaim | Door side-effect before cap check | `IN_CODE` | `dispatch_door.py:94-119` |
| `record_failure` / `record_class_failure` | Sole identical increment writers | `IN_CODE` | `identical_failures.py:355+` |
| Clear/zero identical | Predicate flip / forensics / EDL chain on product flip — **not** on recovered | `IN_CODE` | `identical_failures.py:747+`, `:1010-1013` |
| `note_sticky_heal_attempt` | Sticky×N same pin+predicate; clear if sealed / token flips — **no recovered hook** | `IN_CODE` | `thrash_hardening.py:1290+` |
| `record_thrash_hit` | Soft thrash_report; ESR softens | `IN_CODE` | `thrash_hardening.py:2550+` |
| `run_delivery_unstick` | Clears thrash; **never** zeros identical (RC6/O8) | `IN_CODE` | `delivery_unstick.py:98-99`, `:151-157` |
| `escalate_stage_failure` | Post-fail path → another identical reason bump | `IN_CODE` | `stage_resilience.py` |
| `hang_escalation.budget_for_work` | ML hang timeout — cousin only | `IN_CODE` | `hang_escalation.py` |

---

## 2. Failure permutations

| Case | What happens now | Honest outcome should be | Tag | Pointer |
|------|------------------|--------------------------|-----|---------|
| Clean recover, hole gone, pin sealed | recovered; sticky may clear if sealed; log+R12c still bumped | Advance; success should not set up next identical halt | `IN_CODE` | R12c + sticky sealed |
| Clean recover, then same class fails again | attempt_count ≥ budget → `budget_exhausted` escalate | One honest escalate / halt — not storm | `IN_CODE` | `budget_exhausted` |
| False recover (cousin) | Mostly refused by HC-HEAL-SUCCESS | Stay refused | cousin closed | `heal_success.py` |
| Recovered + resume ≠ failed stage | Pipeline `Complete X before Y` → nested fail/recover | Admit pin without multi-budget burn | `IN_CODE` | pipeline recovered |
| Transient class recovered×3 | R12c identical climbs toward halt | Halt or progress-gated reset | `IN_CODE` | `TRANSIENT_ERROR_CLASSES` budget=3 |
| Product patch mid-run | BUD-1 epoch reclaim; Partial ×3 stay | Retry incomplete producers | `IN_CODE` | DP-BUD1 |
| Sticky same pin post-heal | Sticky×N; unstick clears thrash not identical | Clear sticky on true progress only | `IN_CODE` | sticky + unstick |
| Same fingerprint, no product flip | No reclaim; max_invokes / identical storm | Options: don’t fuel thrash on recovered, or reclaim on **predicate** progress | `IN_CODE` | residual = this class |
| Partial must-act open | Same counters (no Partial soft wipe) | Mode-wide law | `IN_CODE` | V8 parity upstream |
| Full-auto defaults | Driver reclaim + auto-unstick once; identical untouched by unstick | Same | `IN_CODE` | driver + delivery_unstick |
| Forensics restart | Identical wipe (preserve open seed_order) | Out of scope for clinic proof | `IN_CODE` | `sync(..., forensics=True)` |

---

## 3. Already closed vs residual

| Prior DP / cousin_matrix row | Claimed closed? | Verified on HEAD? | Residual? |
|------------------------------|-----------------|-------------------|-----------|
| **DP-BUD1 A** — fingerprint reclaim + refuse≠Finished | Yes (cousin_matrix BUDGET_THRASH closed as soak residual) | Yes — `reclaim_budget_on_product_flip`, `test_bud1_product_reclaim.py` | Soak residual: thrash on **same** fp after “ok” → **this class** |
| **HC-HEAL-SUCCESS** — refuse false recovered | Yes (clinic verdict B+) | Yes — `finalize_heal_success` | Does **not** reset post-success counters |
| **HC-HOLLOW-DONE** | Yes | Done Constitution | Fake done → re-enter → feeds this class |
| **HC-LEAP-ADMIT** / **HC-PIN-NAV** | Yes | Admit + pin authority | Wrong land → sticky/identical storms |
| R12c unified recovery↔identical counters | Intentional (`test_unified_recovery_counters_r12c`) | Yes | Intentional design becomes thrash fuel when recovered is true |
| Unstick never zeros identical (RC6/O8) | Intentional | Yes | Correct for unstick; leaves post-heal identical climb |

HINT only (not proof): residual same-fingerprint thrash after reclaim maps to this clinic class. Do not browse `exec_*`.

---

## 4. Complexity traps

- **Duplicate budget laws:** `count_identity` (check_dispatch) vs `count_attempts` (dispatch door) — dual SSOT for “how many invokes.” `CODE_DOC_CONFLICT` / dual-SSOT risk if options touch only one.
- **R12c intentional vs this class:** Mirroring recovered into identical was meant for unified halt honesty; options must not silently delete that without a replacement progress rule.
- **Mode-special branches:** Forensics clears identical aggressively; Partial/Full-auto only epoch on product flip — do not invent Partial-only soft clear (`FULL_AUTO_REGRESSION_RISK`).
- **Heal that hides quality failure:** Already narrowed by Heal Success; residual here is **honest recover that still spends the thrash budget** so the next failure looks like “we already tried.”

---

## 5. TEST_GAP

| Behavior | Covered? | Suggested matrix test |
|----------|----------|------------------------|
| recovered append → identical class +1 (R12c) | Yes | `test_execution_flow_hardening.py::test_unified_recovery_counters_r12c` |
| recovered rows count toward recovery budget | Partial | Assert default budget=1 → next failure `budget_exhausted` without second playbook |
| `finalize_heal_success` does **not** stamp epoch / clear identical | No | Counters unchanged across finalize ok |
| Post-recovered resume≠stage burns second dispatch | No | Pipeline mock: recovered → Complete raise → no infinite recover |
| Sticky unchanged after recovered with unsealed pin | No | sticky before/after recovered=True |
| Unstick does not zero identical | Comment/RC6 | Explicit assert counts stable across `run_delivery_unstick` |
| BUD-1 fingerprint reclaim | Yes | `test_bud1_product_reclaim.py` |
| HC-HEAL-SUCCESS gate | Yes | `test_heal_success.py` |
| Identical ×3 / sticky / thrash detector | Yes | `test_hc2_*`, thrash hardening suites |
| **E2E: recovered then max_invokes / identical storm same fp** | **No** | Matrix: one recover → N starts → `dispatch_cap_refusal` / identical halt **without** product flip |

---

## 6. Cousin hints (suggestions only)

- Related heal-clinic classes:
  - **heal_validate_stage_fail** — false recovered closed; leftover accounting = here
  - **hollow_pass** — fake done → re-enter → budget burn
  - **leapfrog_resume** / **wrong_pin** — wrong land → sticky + identical storms
- Possible bigger deterministic shared rule: **Post-heal accounting constitution** beside BUD-1 + Heal Success — e.g. recovered rows do not mirror into identical / do not burn attempt budget unless predicate unchanged on next fail; or predicate-progress reclaim (not fingerprint-only). Prefer **one** law for Partial + Full-auto; do **not** invent a second thrash counter brand.

---

## 7. Ready for options?

- [x] Census complete enough for A/B/C
- [x] At least one surgical and one SSOT-shaped approach imaginable
  - **Surgical sketch:** Skip R12c mirror when `status=recovered`; and/or don’t count recovered toward `recovery_attempt_budget`
  - **SSOT sketch:** Explicit post-heal accounting rule (progress/predicate reclaim or “success ≠ thrash fuel”) plugged into BUD-1 + Heal Success — not a fourth unrelated brand
- Next paste: `/heal-clinic-options CLASS=post_heal_budget_thrash`
