# Decisions — mastering_plan_synthesize

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | Preserve soft_gate never complete (B1)? | Wave 2 yes | MPS-B1 docstring pins on claim_plan_complete / synthesize; A-03 tests |
| 2026-09-17 | L2/L3 | consumers_bind flip criteria (B2)? | Wave 2 skip — needs_you + FULL_AUTO_REGRESSION_RISK | keep consumers_bind=false |
| 2026-09-18 | L3 | MPS-B2 consumers_bind flip? | **3A** KEEP false | no Full-auto flip |
