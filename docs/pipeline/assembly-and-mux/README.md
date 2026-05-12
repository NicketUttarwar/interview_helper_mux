---
id: pipeline-assembly-mux
tier: both
status: spec
depends_on: [pipeline-audio-editing]
---

# Assembly and mux

**Composition layer:** order clips, insert transitions and optional beds, produce a **master timeline**—not only linear concat. Repo name **mux** maps here.

## In this folder

| Topic | File |
|-------|------|
| EDL / timeline model | [timeline-and-edl.md](timeline-and-edl.md) |
| Non-linear assembly | [dynamic-assembly-graph.md](dynamic-assembly-graph.md) |
| Edge cost, bridging, order search | [edge-cost-bridging-and-order-search.md](edge-cost-bridging-and-order-search.md) |

## Next stage

[../mastering-and-export/README.md](../mastering-and-export/README.md)

## Open decisions

- Declarative timeline format (JSON EDL vs FFmpeg concat demuxer only).

## Links

- [../../workflows/human-overrides-and-rescore.md](../../workflows/human-overrides-and-rescore.md)
- [../../execution/orchestration-component-map.md](../../execution/orchestration-component-map.md)
