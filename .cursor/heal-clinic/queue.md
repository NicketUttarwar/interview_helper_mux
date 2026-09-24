# Queue — Heal Clinic

Order for `/heal-clinic-next` (operator may override by naming CLASS=).

| # | class_id | plain name | why this order |
|---|----------|------------|----------------|
| 1 | wrong_pin | Wrong pin | Breaks resume honesty for every mode |
| 2 | leapfrog_resume | Leapfrog resume | Closely related to pins; VO/order thrash |
| 3 | hollow_pass | Hollow “pass” | Lies about done → poisons Partial + Full-auto |
| 4 | heal_validate_stage_fail | Heal-validate then stage-fail | Identical loops / false heal success |
| 5 | post_heal_budget_thrash | Budget thrash after “successful” heal | Burns unattended runs after “ok” |

**Next rule:** first row in [`ledger.md`](ledger.md) where `L1_map` ≠ complete, or `L2_options` ≠ complete, or `verdict` = awaiting_operator (surface for answer, do not re-discover). Skipping implemented/deferred rows.
