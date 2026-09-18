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
| B1 | P0 | unambiguous | Hard topology: enforce in body (SEED_ORDER SSOT) | refuse before LLM | 2,4 | no (seed already requires topology) |
| B2 | P2 | unambiguous | Deduplicate soft review_queue rows in contract YAML | dependency data | 2 | no |

## target_status

`applied` — Wave 2 CC-B2 + CC-B1 (Q1A harden topology body/preflight)
