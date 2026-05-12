---
id: mux-timeline-edl
tier: both
status: spec
depends_on: [pipeline-assembly-mux]
---

# Timeline and EDL

An **edit decision list** references `segment_id` or file paths with **in/out**, **order**, **gain**, **fade**, and optional **parallel** tracks (music under voice).

## Minimal EDL row

- `sequence_index`
- `source_ref` (segment id or URI)
- `in_ms`, `out_ms`
- `fade_in_ms`, `fade_out_ms`
- `gain_db` (optional)

## Open decisions

- Single stereo bus vs multitrack project export.

## Links

- [dynamic-assembly-graph.md](dynamic-assembly-graph.md)
- [edge-cost-bridging-and-order-search.md](edge-cost-bridging-and-order-search.md)
- [../mastering-and-export/chapters-metadata-export.md](../mastering-and-export/chapters-metadata-export.md)
