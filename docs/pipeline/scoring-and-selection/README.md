---
id: pipeline-scoring
tier: both
status: spec
depends_on: [pipeline-segmentation]
---

# Scoring and selection

Identify segments with the **most detail** (salience) and pick a **subset** suitable for a tight final master—without redundant overlap unless intentional.

Which scoring tools belong to which **preset** (A–H) is reviewed in [../../execution/orchestration-component-map.md](../../execution/orchestration-component-map.md); do not grow this folder for one-off orchestration whims.

## In this folder

| Topic | File |
|-------|------|
| Heuristic signals | [salience-heuristics.md](salience-heuristics.md) |
| LLM ranking | [llm-assisted-ranking.md](llm-assisted-ranking.md) |
| Diversity in the picked set | [diversity-constraints.md](diversity-constraints.md) |

## Next stage

[../snippet-store/README.md](../snippet-store/README.md)

## Open decisions

- Weighting of “information density” vs emotional peak vs named entities.

## Links

- [../../cross-cutting/evaluation-metrics.md](../../cross-cutting/evaluation-metrics.md)
- [../../execution/orchestration-component-map.md](../../execution/orchestration-component-map.md)
