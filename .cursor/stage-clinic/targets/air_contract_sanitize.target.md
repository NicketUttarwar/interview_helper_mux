# Target Spec — air_contract_sanitize

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| clean | commit + heal + soft freeze | Completes |
| unsanitary / reentry | raise; not done | Honest |
| freeze stamp fail | raise | Fail-closed |

## Rules set

- admit / sanitary commit
- refuse / unsanitary|reentry
- precise invalidate / pin air_contract_sanitize

## Complexity subtraction

- Keep single commit_air_contract owner

## Non-goals

- Wave 1 patches

## Acceptance checks

- HF-4 dirty done cleared; soft freeze stamped

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Keep reentry refuse (no nested guard wrap) | existing tests | 2 | yes |
| B2 | P1 | unambiguous | Contract lifecycle non-LLM | yaml | 2 | no |

## Defaults inventory impact

- soft seat freeze after sanitize is Full-auto landmine if stamp fails

## target_status

`draft`
