# Target Spec — ideal_cuts_materialize

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| ideal_cuts.json missing | Incomplete/refuse (honest) — do not claim soft | Unattended hard-stop until propose lands |
| enable=false | Explicit disabled artifact + done OK | Continue |
| empty/coarse snap | Materialize done; do not publish coarse boundaries | boundary_detection owns LLM map |
| quality bind OK | Publish boundaries + seed | Skip boundary LLM downstream |

## Rules set (prefer deterministic)

- admit / snap when ideal_cuts present
- refuse / missing ideal_cuts (align contract hard)
- wait_for_gate / N/A
- incomplete / missing upstream propose
- precise invalidate / none (consumers react to publisher stamp)
- auto_resolve_default / N/A

## Complexity subtraction list

- Treat ideal_cuts as hard in contract YAML (match RuntimeError)

## Contract / dependency deltas (proposed; not applied)

- Move `understanding/ideal_cuts.json` from soft→hard inputs

## Non-goals

- Changing bind_mode defaults
- Local acoustic refine quality

## Acceptance checks

- Contract hard list matches raise path
- Coarse bind still demotes without hollow boundaries

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| B1 | P2 | unambiguous | Contract: ideal_cuts soft→hard | contract YAML + generator roundtrip | 2,7 | no |
| B2 | P3 | needs_you | Soft-stale propose freshness gate? | only if operator wants | 7 | yes if adds stalls |

## Defaults inventory impact

- Rows touched in `defaults_inventory.md`: none (bind defaults already correct)

## target_status

`draft`
