# Target Spec — mastering_research_routing

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| research.llm.enabled=false | Sequential stub + heal (current) | Continue |
| llm on + success | Write LLM routing + heal | Opt-in |
| llm on + fail/exhaust | Incomplete/refuse OR explicit stub with llm_failed **and** non-authoritative flag — not silent success | Must not fake rich routing |

## Rules set (prefer deterministic)

- admit / stub when llm disabled
- refuse / llm enabled and invoke fails (preferred) OR stamp llm_failed without claiming complete dispositions
- incomplete / llm enabled + null arts
- auto_resolve_default / keep llm.enabled=false

## Complexity subtraction list

- Remove bare `except Exception: pass` soft-success when llm enabled

## Contract / dependency deltas (proposed; not applied)

- Demote hard SDP or enforce it only when llm.enabled

## Non-goals

- Authoritative routing mode flip
- Wave field quality

## Acceptance checks

- Default Full-auto unchanged (stub)
- With llm.enabled=true, failed invoke does not heal as rich success

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| B1 | P1 | needs_you | LLM fail: refuse vs explicit degraded stub? | operator pick | 2,4 | yes if refuse stalls unexpected |
| B2 | P2 | unambiguous | Log+stamp llm_failed clearly; avoid empty except | unit with llm forced on | 2,4 | no |

## Defaults inventory impact

- research.llm.enabled=false row

## target_status

`draft`
