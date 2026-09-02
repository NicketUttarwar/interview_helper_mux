# Ladder / invalidation PR checklist

When changing `run_*_ladder`, `invalidate_downstream`, `handle_gate` heals, or `INVALIDATION_PROFILES`:

1. Update or add an **invalidation profile** (`execution_invalidation_profiles.py`) with explicit `allowed_clear` / `forbidden_clear`.
2. Add at least one **negative test** in `tests/test_ladder_negative_guards.py` documenting MUST_NOT for the tier/profile.
3. Include an `invalidation_log.jsonl` row in the test fixture when profiles clear stages.
4. Run `./scripts/verify_ladder_negative_guards.sh` before mohan partial-auto rerun.

See `.cursor/plans/mohan_general_improvement.plan.md` §12–§14.
