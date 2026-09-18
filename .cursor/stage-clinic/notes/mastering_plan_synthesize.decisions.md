# Decisions — mastering_plan_synthesize

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | Preserve soft_gate never complete (B1)? | Wave 2 yes | MPS-B1 docstring pins on claim_plan_complete / synthesize; A-03 tests |
| 2026-09-17 | L2/L3 | consumers_bind flip criteria (B2)? | Wave 2 skip — needs_you + FULL_AUTO_REGRESSION_RISK | keep consumers_bind=false |
| 2026-09-18 | L3 | MPS-B2 consumers_bind flip? | **3A** KEEP false | no Full-auto flip |
| 2026-09-18 | optional revisit | Q7 MPS consumers_bind | **SKIP / defer** to next ask net | see `next_questions_deferred.md` (full forms MPS/MSC/MSA…) |
| 2026-09-18 | optional revisit | Q7 MPS consumers_bind (re-ask) | **A KEEP false** | hybrid bind for complete only; deferred net closed |
| 2026-09-18 | honesty pass | Shape/MPS pack+lint | plan ingest lint; slim evidence inlines; soft-degrade `llm_failed`; precedence needs complete (incl. air_ids fallback) | `_lint_shape_plan_llm` + payload slim + `plan_is_authoritative` gate |
