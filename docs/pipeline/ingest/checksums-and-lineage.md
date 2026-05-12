---
id: ingest-checksums
tier: both
status: spec
depends_on: [pipeline-ingest]
---

# Checksums and lineage

Every derived artifact should point back to **which bytes** produced it.

## Lineage fields (conceptual)

- `source_audio_id` + `sha256` of normalized file (or raw if you never re-encode).
- `ingest_config_version` (semver or git SHA of config).
- Optional: `parent_job_id` for chunked pieces merged after STT.

## Open decisions

- Hash **raw** vs **normalized** file as primary key.

## Links

- [../../cross-cutting/segment-schema.md](../../cross-cutting/segment-schema.md)
- [../../workflows/idempotent-runs.md](../../workflows/idempotent-runs.md)
