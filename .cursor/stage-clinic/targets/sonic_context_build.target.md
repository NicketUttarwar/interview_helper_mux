# Target Spec — sonic_context_build

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| brief+manifest present | Build + schema heal (current) | Continue |
| fuse audit missing | Still admit if brief+manifest OK | Do not stall on fuse-only hard |
| schema hollow | Refuse done (HM-4) | Keep |

## Rules set (prefer deterministic)

- admit / brief + manifest (match input_checks)
- refuse / schema hollow
- incomplete / missing brief or manifest
- precise invalidate / none
- auto_resolve_default / N/A

## Complexity subtraction list

- Single hard-input SSOT: code input_checks, not contract fuse audit

## Contract / dependency deltas (proposed; not applied)

- Contract hard: replace connector_fuse_audit with content_brief + manifest (or soft fuse)

## Non-goals

- Changing sonic schema richness

## Acceptance checks

- Contract/generator matches `_check_sonic_context_build`
- HM-4 tests still pass

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| B1 | P1 | unambiguous | Align contract hard inputs to input_checks | contract roundtrip test | 2,7 | no |

## Defaults inventory impact

- none

## target_status

`draft` — Wave 2 applied SCB-B1 (hard = brief+manifest+acoustic; fuse soft-carved)
