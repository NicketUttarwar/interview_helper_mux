---
id: capture-backup-integrity
tier: both
status: spec
depends_on: [pipeline-capture]
---

# Backup and integrity

Avoid losing the only copy of an irreplaceable interview.

## Practices

- Copy raw capture to **two locations** before destructive edits (local disk + external or cloud you control).
- Compute **SHA-256** (or BLAKE3) at ingest; store hash in manifest ([../snippet-store/segment-manifest-and-storage.md](../snippet-store/segment-manifest-and-storage.md)).

## Duplicate detection

- Same filename, different hash → treat as distinct asset with disambiguated IDs.
- Same hash → idempotent ingest ([../../workflows/idempotent-runs.md](../../workflows/idempotent-runs.md)).

## Open decisions

- Whether phone auto-upload is trusted enough to skip manual copy.

## Links

- [../ingest/checksums-and-lineage.md](../ingest/checksums-and-lineage.md)
