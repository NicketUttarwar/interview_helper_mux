# Model routing

OpenAI chat models per stage. Configured in `config/app.defaults.json` under `models`.

## Defaults

| Stage key | Default model | Tier |
|-----------|---------------|------|
| `speaker_roles` | gpt-4o-mini | bulk |
| `content_context` | gpt-4o-mini | bulk |
| `boundary_detection` | gpt-4o | quality |
| `segment_classification` | gpt-4o | quality |
| `missing_framing` | gpt-4o | quality |
| `optimal_questions` | gpt-4o | quality |
| `topic_coverage_audit` | gpt-4o | quality (Flow 1) |
| `narrative_arc_plan` | gpt-4o | quality (Flow 1) |
| `full_master_ranking` | gpt-4o | quality (Flow 1) |
| `highlight_selection` | gpt-4o | quality (Flow 2) |
| `transitions` | gpt-4o-mini | bulk |
| `podcast_sfx_brief` | gpt-4o-mini | bulk (Flow 1) |
| `sfx_brief` | gpt-4o-mini | bulk (Flow 2) |

## When to use flagship (e.g. GPT-5.x)

Use stronger models for:

- Gap detection and optimal questions
- Flow 1 coverage audit, narrative plan, full master ranking
- Flow 2 highlight selection

Keep mini models for speaker/content pass and SFX brief generation; use quality tier for segmentation (cascade-sensitive).

Override per machine in `config/app.defaults.json` — not in prompt files.
