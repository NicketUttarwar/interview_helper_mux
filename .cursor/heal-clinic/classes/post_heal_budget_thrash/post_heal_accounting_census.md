# Post-Heal Accounting census — post_heal_budget_thrash B+

status: shipped_with_B+  
updated: 2026-09-22  
code_is_king: true  
P3_choice: **ship** predicate-progress reclaim (not named exception)

## Exception tables (`heal_post_accounting.py`)

| Table | Value |
|-------|-------|
| `POST_HEAL_EPOCH_ALLOW` | empty — anti-C; BUD-1 owns product epoch |
| `POST_HEAL_COUNT_RECOVERED_ATTEMPTS` | False — recovered never fuels attempt budget |

## P11 caller census

| Caller | Path to `finalize_post_heal_accounting` | Second path? |
|--------|------------------------------------------|--------------|
| `recovery_controller._append_action` | Direct call after log write | No |
| `handle_stage_failure` | → `_append_action` | No |
| `pipeline` recovered branch | → `handle_stage_failure` only; comment DENY local bump/epoch | No |
| `homunculus/runtime` recover | → `handle_stage_failure` only | No |
| `tools/full_auto_driver._try_recovery` | → `handle_stage_failure` only | No |

## Residual closure

| ID | Status |
|----|--------|
| P1 | ✅ recovered no R12c mirror |
| P2 | ✅ recovered excluded from `attempt_count` |
| P3 | ✅ `reclaim_class_signature_on_predicate_progress` on flip |
| P4 | ✅ accounting does not clear sticky |
| P5 | ✅ admit resume unchanged; no nested accounting |
| P6 | **named exception** — walk `count_identity` / `count_attempts` not reset on recovered (anti-C); BUD-1 product flip remains sole global epoch |
| P7 | ✅ recovered×N no longer mirrors toward identical halt |
| P8 | ✅ Partial = Full-auto (no mode branch) |
| P9 | ✅ unstick test — identical unchanged |
| P10 | ✅ matrix in `test_heal_post_accounting.py` |
| P11 | ✅ census above |

## Tests (`MUX_FORENSICS=0`)

- `tests/test_heal_post_accounting.py`
- adapted `test_unified_recovery_counters_r12c` / `test_recovery_transient_retry_budget`
- BUD-1 + heal_success still green
