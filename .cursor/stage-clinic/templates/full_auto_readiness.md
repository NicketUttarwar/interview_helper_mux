# Full-auto readiness rollup (Wave 3)

last_scored:  
verdict: `not_ready` | `ready_for_unattended_full_auto_attempt`

## §0.2 scorecard

| # | Check | Score | Evidence (map/target paths) | Notes |
|---|-------|-------|-------------------------------|-------|
| 1 | Progression | pass\|fail\|partial\|unknown | | |
| 2 | Honesty | | | |
| 3 | Stalls | | | |
| 4 | OpenAI variance | | | |
| 5 | Defaults | | | |
| 6 | Ship bar | | | |
| 7 | Cross-stage | | | |

## Aggregation rules

- `ready` only if 1–6 are pass or justified partial, no open FULL_AUTO_REGRESSION_RISK, and 7 has no unlabeled repeats
- `not_ready` if any of 1–6 fail/unknown on ship-critical stages or defaults inventory incomplete

## Blockers

- 

## Residual needs_you

- 

## Cross-stage patterns open

- 

## Optional outside confirmation

Live Full-auto run is **outside** this campaign; not required to close Wave 3.
