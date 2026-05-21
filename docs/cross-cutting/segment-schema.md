---
id: cross-segment-schema
tier: both
status: spec
depends_on: []
---

# Segment schema (cross-cutting)

Shared conceptual schema for **segments** and **EDL references** used by snippet store, review UI, and mux.

## Segment record (minimal)

| Field | Type | Notes |
|-------|------|--------|
| `segment_id` | string | Stable within `(session_id, transcript_revision, boundary_set)` |
| `session_id` | string | One pipeline execution / source recording (`run_001`, …) |
| `t_start_ms` | int | Global timeline |
| `t_end_ms` | int | Exclusive or inclusive—pick one convention repo-wide |
| `text` | string | Segment transcript |
| `scores` | object | Named floats, e.g. `salience`, `llm_rank` |
| `flags` | object | `force_include`, `force_exclude`, `human_rejected` |
| `mutex_group_id` | string or null | Optional: segments sharing an id are **mutually exclusive** in final pick (narrative contradiction sets)—see [../../execution/orchestration-component-map.md](../../execution/orchestration-component-map.md) archetype D |
| `provenance` | object | `transcript_revision`, `segmenter_id`, `stt_model_id` |

## EDL reference

- `segment_id` **or** explicit `file_uri` + `in_ms`/`out_ms` for rendered clips.

## Open decisions

- JSON Schema vs SQL migrations as source of truth.

## Links

- [../pipeline/snippet-store/segment-manifest-and-storage.md](../pipeline/snippet-store/segment-manifest-and-storage.md)
- [../pipeline/assembly-and-mux/timeline-and-edl.md](../pipeline/assembly-and-mux/timeline-and-edl.md)
- [../execution/orchestration-component-map.md](../execution/orchestration-component-map.md)
