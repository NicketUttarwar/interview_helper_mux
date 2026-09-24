# Decisions — wrong_pin

Append-only. Do not rewrite history.

| timestamp | event | operator text | implication |
|-----------|-------|---------------|-------------|
| 2026-09-22T10:54:00Z | verdict E | `/heal-clinic-answer CLASS=wrong_pin VERDICT=E` | Refuse-by-default + narrow allowlist + prereq checklist + one `resolve_heal_from_stage` SSOT. Pin rewrite rare. Shared Partial + all-modes. Wave 2 may implement on explicit `/heal-clinic-implement`. |
| 2026-09-22T18:00:00Z | implement started | `/heal-clinic-implement CLASS=wrong_pin` | Land `heal_pin_authority.py`; wire `heal_navigate` + `resolve_premature_cap_pin`. |
| 2026-09-22T18:30:00Z | implement done | Wave 2 E | Authority default ON (`HEAL_PIN_AUTHORITY=0` escape). Tests: `tests/test_heal_pin_authority.py` + related pin suites green `MUX_FORENSICS=0`. Residual: wire `stage_minimum_run_checklist` into agenda scheduler (happy-path) in a follow-on if soak shows schedule thrash. |
