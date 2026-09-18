# Target Spec — framing_posture_decide

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| homunculus 0.2.0 + eligible | Advisory LLM persist; do not resolve G-Framing | Continue; gate later |
| monologue / ineligible silent | Deterministic monologue + host_enforce skip gaps | Continue |
| no homunculus features | Allow stub + heal | N/A clinic brain |

## Rules set (prefer deterministic)

- admit / always produce decision artifact
- refuse / N/A for advisory hollow — validate schema
- wait_for_gate / never at this stage
- auto_resolve_default / N/A here (G-Framing elsewhere)

## Complexity subtraction list

- Keep advisory-only; do not promote to gate authority

## Contract / dependency deltas (proposed; not applied)

- Optional: note tier llm_full with skip paths in contract comments via generator metadata — low priority

## Non-goals

- Changing G-Framing auto-Yes policy
- Chatterbox / voice-ref

## Acceptance checks

- Stage never stamps needs_operator
- apply_host_gate only for native_only monologue/forced paths

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| B1 | P3 | unambiguous | StageInfo blurb: brain 0.2.0 not 0.1.0 | web/stages.py string | 5 | no |

## Defaults inventory impact

- gap_fill.auto_accept_defaults=false; homunculus auto-Yes later — document adjacency only

## target_status

`draft` — Wave 2 applied B1 (StageInfo 0.2.0 blurb)
