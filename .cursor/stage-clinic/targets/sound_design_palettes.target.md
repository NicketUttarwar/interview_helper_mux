# Target Spec — sound_design_palettes

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| early_palettes_llm=false | Deferred empty palettes + heal | Continue (shipped) |
| early_palettes_llm=true | LLM palettes ≥1 or refuse | Opt-in variance |
| sound_design.enabled=false | Skip heal | Continue |

## Rules set (prefer deterministic)

- admit / deferred path without palette min
- refuse / LLM path hollow palettes when early LLM on
- incomplete / missing sonic when LLM path
- auto_resolve_default / keep early_palettes_llm=false

## Complexity subtraction list

- Contract sufficiency must encode deferred_ok

## Contract / dependency deltas (proposed; not applied)

- Sufficiency: palettes min_rows only when not deferred_early_palettes / early_palettes_llm

## Non-goals

- Turning early LLM on by default
- MusicGen quality

## Acceptance checks

- Defaults path still completes with empty palettes
- Contract no longer claims blocking palettes≥1 unconditionally

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| B1 | P2 | unambiguous | Fix contract sufficiency for deferred | contract + completeness parity | 2,5 | no |

## Defaults inventory impact

- Confirm early_palettes_llm=false row

## target_status

`draft`
