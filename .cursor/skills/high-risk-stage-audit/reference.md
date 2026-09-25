# High-risk stage audit — reference

## Operator paste

```
/high-risk-audit STAGE=___
Follow .cursor/skills/high-risk-stage-audit/SKILL.md
```

Optional: `MODE=fix` · `MODE=rescore`

Replace `___` with seed number (`45`) or stage id (`nugget_layup_compose`).

## §0 Stage Guide checklist

Agent speaks this at chat start, then writes it into the audit file:

- [ ] What this stage does (happy path)
- [ ] Primary artifacts (read / write / SSOT)
- [ ] Rules (admit / refuse / incomplete / heal / gate / done honesty / floors / freeze)
- [ ] Considerations & load-bearing policy
- [ ] LLM / external calls (or N/A)
- [ ] What it does *not* do
- [ ] Operator-visible effects

## Scorecard quick judge

| Verdict | When |
|---------|------|
| **PASS** | `Over-engineered?` = `no` (≤2 responsibilities, no dual SSOT, no hard fail-if rows) |
| **FAIL** | `Over-engineered?` = `yes` **or** `partial` |

Fail-if triggers: responsibilities ≥3 · dual SSOT · soft-heal thrash loops · co-producer unpaid land · brittle predicates=`yes` · disproportionate shard/memo=`yes` · fix-everything-downstream=`yes`.

After patches: fill **§5b**, new PASS/FAIL — never assume scorecard cleared.

On **`MODE=rescore`**: also refresh **§6** — mark shipped rows `done:…`, append new open cuts tied to remaining fail-if hits (≤5 open).

## Findings row format

In `high_risk_error_stages_report.md` → `## Audit findings`, update **only this stage**:

| Column | Content |
|--------|---------|
| Status | `complete` |
| Over-eng? | `yes` / `partial` / `no` |
| Verdict / next | `FAIL — …` or `PASS — …` plus next action; link stays |

## Paths

| Artifact | Path |
|----------|------|
| Master report | `.cursor/plans/high_risk_error_stages_report.md` |
| Audits | `.cursor/plans/high_risk_stage_audits/<stage_id>.md` |
| Template | `.cursor/plans/high_risk_stage_audits/_TEMPLATE.md` |

## Status

`not_started` → `in_progress` → `complete`

`MODE=rescore` may leave status `complete` and bump `updated`.
