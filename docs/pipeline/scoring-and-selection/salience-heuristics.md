---
id: scoring-salience-heuristics
tier: both
status: spec
depends_on: [pipeline-scoring]
---

# Salience heuristics

Fast, explainable scores before or instead of heavy LLM use.

## Example signals

- **Tokens per second** (after removing disfluencies).
- **Named entity** count or capitalized phrase density.
- **Question density** in surrounding context.
- **Numeric / date** mentions (often story-bearing in interviews).

## Open decisions

- Stopword lists and language-specific tokenizers.

## Links

- [llm-assisted-ranking.md](llm-assisted-ranking.md)
- [../../cross-cutting/evaluation-metrics.md](../../cross-cutting/evaluation-metrics.md)
