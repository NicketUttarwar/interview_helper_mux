# Heal Success census — heal_validate_stage_fail B+

status: shipped_with_B+  
updated: 2026-09-22  
code_is_king: true

## Exception tables (`heal_success.py`)

| Table | Purpose |
|-------|---------|
| `RECOVER_PLAYBOOK_ALLOW` | Only listed playbooks may attempt recovered |
| `RECOVER_ALLOW_WITHOUT_SEED` | Default empty |
| `SOFT_PRE_FLUSH_ALLOW` | Default empty — soft pre-flush does not unlock done |
| `SAME_STAGE_RETRY_ALLOW` | Playbooks that may re-run failed stage |

## Recover census

| Site | Gate |
|------|------|
| `recovery_controller.handle_stage_failure` | `finalize_heal_success` before status=recovered |
| Unconditional recovered removed | sdp themes / musicgen / incomplete_cut / pending barrier |

## Flush / mark census

| Site | Gate |
|------|------|
| `approve_stage_writes` post-flush | `may_mark_after_flush` |
| `validate_staged_before_flush` | `may_soft_pre_flush_pass` (default refuse) |
| `heal_or_raise` | seed-complete (V10) |
| Driver `_heal_mark_or_resume` | seed-complete |

## Caller matrix

| Caller | Uses finalize / admit |
|--------|----------------------|
| recovery_controller | finalize_heal_success |
| pipeline recovered | admit_resume + producer pin raise |
| homunculus runtime | admit_resume on resume |
| full_auto_driver `_try_recovery` | handle_stage_failure (gated) |

## V checklist

| ID | Status |
|----|--------|
| V1–V2 | done |
| V3–V4 | done |
| V5–V7 | done |
| V8 | tests |
| V9 | may_mark_after_flush vo path |
| V10 | heal_or_raise + driver |
| V11 | soft cross-validate comment + not recovered |
