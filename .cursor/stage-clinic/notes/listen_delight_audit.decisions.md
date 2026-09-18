# Decisions — listen_delight_audit

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | B1 Keep fail_early=false default? | skipped | FULL_AUTO_REGRESSION_RISK=yes — leave false (already default) |
| 2026-09-17 | L3 | B2 Keep authoritative ship re-run? | skipped | FULL_AUTO_REGRESSION_RISK=yes — leave master_finalize ship path |
| 2026-09-17 | L3 | B3 Remutate cap / contract invalidates honesty? | skipped | needs_you + FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 CONTINUE | B3 remutate terminate? | Cap remutate (N) then ship best / refuse; document N in app.defaults | N=`mastering.listen_delight.max_remutate_attempts` default **3**; sticky exhaust; pick-best then refuse; recovery budget aligned; contract notes runtime remutate ≠ ADG invalidates |
| 2026-09-17 | L3 CONTINUE | B1 Keep fail_early=false? | KEEP | notes only — no code flip; `fail_early_at_audit_stage=false` stays shipped default |
| 2026-09-17 | L3 CONTINUE | B2 Keep authoritative ship re-run? | KEEP | notes only — no code flip; `master_finalize` → `run_authoritative_listen_delight_at_ship` remains ship authority |
