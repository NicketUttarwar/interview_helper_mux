---
id: human-review-force
tier: both
status: spec
depends_on: [pipeline-human-review]
---

# Force include and exclude

Hard constraints for assembly: `force_include` segments must appear; `force_exclude` never appear regardless of score.

## Data model

- Store flags on `segments` row; assembly step must respect them before optimization passes.

## Open decisions

- Whether force-include can violate max duration budget (warn vs hard error).

## Links

- [../../workflows/human-overrides-and-rescore.md](../../workflows/human-overrides-and-rescore.md)
- [../../cross-cutting/segment-schema.md](../../cross-cutting/segment-schema.md)
