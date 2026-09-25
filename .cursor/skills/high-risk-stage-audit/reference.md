# High-risk stage audit — reference

## Operator paste (single command)

```
/high-risk-audit STAGE=___
Follow .cursor/skills/high-risk-stage-audit/SKILL.md
```

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

## Paths

| Artifact | Path |
|----------|------|
| Master report | `.cursor/plans/high_risk_error_stages_report.md` |
| Audits | `.cursor/plans/high_risk_stage_audits/<stage_id>.md` |
| Template | `.cursor/plans/high_risk_stage_audits/_TEMPLATE.md` |

## Status

`not_started` → `in_progress` → `complete`
