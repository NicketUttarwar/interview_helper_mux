---
id: scoring-diversity
tier: high
status: idea
depends_on: [pipeline-scoring]
---

# Diversity constraints

Avoid selecting **ten segments that say the same thing** because they all scored high on one keyword.

## Techniques

- **Embedding clustering** on segment text; pick at most one per cluster.
- **MMR**-style re-ranking: maximize score minus similarity to already chosen.

## Open decisions

- Similarity threshold tradeoff vs total runtime target.

## Links

- [../assembly-and-mux/dynamic-assembly-graph.md](../assembly-and-mux/dynamic-assembly-graph.md)
