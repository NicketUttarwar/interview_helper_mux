---
id: pipeline-ingest
tier: both
status: spec
depends_on: [pipeline-capture]
---

# Ingest

Move from **raw capture** to **normalized assets** ready for transcription: checksums, loudness/format normalization, and strategies for **very long** files.

## In this folder

| Topic | File |
|-------|------|
| Sample rate, channels, loudness prep | [normalization-and-format.md](normalization-and-format.md) |
| Hashes and lineage | [checksums-and-lineage.md](checksums-and-lineage.md) |
| Splitting for STT limits | [chunking-long-interviews.md](chunking-long-interviews.md) |

## Next stage

[../transcription/README.md](../transcription/README.md)

## Open decisions

- Whether normalization is **lossy** (re-encode) or **lossless** trim only.

## Links

- [../capture/backup-and-integrity.md](../capture/backup-and-integrity.md)
