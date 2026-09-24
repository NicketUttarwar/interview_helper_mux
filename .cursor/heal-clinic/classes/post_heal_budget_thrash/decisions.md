# Decisions — post_heal_budget_thrash

Append-only. Do not rewrite history.

| timestamp | event | operator text | implication |
|-----------|-------|---------------|-------------|
| 2026-09-22T19:33:00Z | verdict B+ | `/heal-clinic-answer CLASS=post_heal_budget_thrash VERDICT=B+` Notes: P3=ship predicate-progress reclaim (not defer); P11=mandatory caller census. | Footgun-complete Post-Heal Accounting (HC-POST-HEAL-BUDGET): P1–P11 mandatory; success ≠ thrash fuel (no R12c bump / no attempt-budget burn on recovered); **P3 ship** predicate-progress reclaim (clear/epoch that signature on token flip — not “don’t bump” alone); **P11** one `finalize_post_heal_accounting` entrypoint + caller census (pipeline / runtime / driver / `_append_action`); Partial=Full-auto; plug BUD-1 + Heal Success not a fifth brand; anti-C (recovered alone never epochs). Wave 2 on explicit `/heal-clinic-implement` only. |
| 2026-09-22T19:45:00Z | L3 implemented | `/heal-clinic-implement CLASS=post_heal_budget_thrash` | Shipped `heal_post_accounting.py`: finalize + P3 predicate reclaim; `_append_action` sole wire; P2 attempt_count excludes recovered; P6 named exception (no global epoch on recovered — BUD-1 only); census + `tests/test_heal_post_accounting.py` (MUX_FORENSICS=0). |
| 2026-09-22T19:45:00Z | P3 choice | implement | **Ship** `reclaim_class_signature_on_predicate_progress` (not named-exception defer). |
| 2026-09-22T19:45:00Z | P6 exception | implement | Dual invoke laws (`count_identity` / `count_attempts`) **not** reset on recovered (anti-C). BUD-1 product fingerprint reclaim remains sole global `stamp_budget_epoch`. Success≠fuel closes identical/recovery-attempt thrash; walk caps still require real work or product flip. |
