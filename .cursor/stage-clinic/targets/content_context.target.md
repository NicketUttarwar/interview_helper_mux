# Target Spec — content_context

brain: 0.2.0 | target_status: draft  

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| OpenAI ok | content_brief schema + done | ≤2 / shard merge |
| missing topology | either hard refuse at PRESTAGE or contract soft | aligned |
| schema fail | StageError no hollow | |

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| B1 | P0 | needs_you | Hard topology: enforce in body vs soften contract | intent | 2,4 | yes if enforce mid-flight |
| B2 | P2 | unambiguous | Deduplicate soft review_queue rows in contract YAML | dependency data | 2 | no |

## target_status

`draft`
