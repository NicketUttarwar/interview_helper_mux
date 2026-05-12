---
id: scoring-llm-ranking
tier: both
status: idea
depends_on: [pipeline-scoring]
---

# LLM-assisted ranking

Use an LLM to **compare** or **grade** candidate segments with a fixed rubric (specificity, novelty, narrative value).

## Practices

- Freeze **prompt version** in manifest for reproducibility.

Reference implementation (OpenAI API only): repository package `ai/python/openai_mux` — `rank_segments_by_rubric` reads transcript snippets and returns a permutation of `segment_id` values. Configure `OPENAI_API_KEY` in `config/secrets/secrets.env` (copy from `config/templates/secrets.env.example`; gitignored); `mux_secrets.load_repo_config()` parses that file tree into memory for all `ai/python/*` integrations — see repository `config/README.md`.
- Batch segments to control cost; cache scores by `segment_id`.

## Mutual exclusion (narrative contradictions)

For **nonlinear** or aggressive automatic picks, two clips may be individually “great” but **incompatible** if played in the same episode. Use `mutex_group_id` on segments ([../../cross-cutting/segment-schema.md](../../cross-cutting/segment-schema.md)) and teach the ranker/solver: **at most one** per group. Detection can be LLM-assisted with a frozen prompt version; assembly still obeys [../../execution/difficult-segment-combinations.md](../../execution/difficult-segment-combinations.md).

## Open decisions

- Pairwise ranking vs absolute 1–10 scores.

## Links

- [diversity-constraints.md](diversity-constraints.md)
- [../../workflows/human-overrides-and-rescore.md](../../workflows/human-overrides-and-rescore.md)
- [../../execution/orchestration-component-map.md](../../execution/orchestration-component-map.md)
