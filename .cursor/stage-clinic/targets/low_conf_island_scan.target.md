# Target Spec — low_conf_island_scan

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| enabled=true (default) | Scan + must_keep + heal | Continue |
| enabled=false | Persist explicit skip artifact(s) + heal done | Continue (no pending stall) |
| HV scan fails | Fail-open (current) | Continue |

## Rules set (prefer deterministic)

- admit / enabled
- refuse / N/A for disable
- incomplete / only if enabled and required outputs missing after run
- precise invalidate / none new
- auto_resolve_default / disabled → skip doc like `persist_fuse_skip`

## Complexity subtraction list

- Mirror connector_fuse disabled skip persistence

## Contract / dependency deltas (proposed; not applied)

- Optional: demote hard vernacular report to soft to match body

## Non-goals

- Changing density ladder thresholds
- OpenAI island structure quality

## Acceptance checks

- enabled=false leaves stage done with skip_reason
- enabled=true still requires islands or must_keep before heal

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| B1 | P0 | unambiguous | Disabled path: write skip + heal | unit test enabled=false | 1,2,3,5 | no |

## Defaults inventory impact

- Note landmine until B1; default enabled=true so Full-auto OK today

## target_status

`draft`
