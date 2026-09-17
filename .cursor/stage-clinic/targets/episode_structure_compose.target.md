# Target Spec — episode_structure_compose

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| enabled | Structure+compact done; may stamp analysis_complete | Completes |
| boundary quality fail | Hard fail / incomplete | Honest |
| disabled | Skip stub done | Completes |
| gap not done & not skipped | Do not falsely finalize analysis_complete | Honest |

## Rules set

- admit / after soundscape
- refuse / boundary assert
- incomplete / hollow structure

## Complexity subtraction

- Forward soft edges into synthesize in contract (noise)

## Acceptance checks

- shared_analysis_chain_complete; gap gating on analysis_complete

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P1 | unambiguous | Test analysis_complete withheld when gap pending | pytest | 2 | no |
| B2 | P2 | unambiguous | Clean contract forward consumers | yaml | 7 | no |

## Defaults inventory impact

- structure.enabled=true; require_payoff/outro false

## target_status

`draft`
