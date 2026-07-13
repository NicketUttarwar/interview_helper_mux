# Disfluency restore (Flow 1 EDL + mix)

When `disfluency_restore.enabled` is true (or per-run override via `PATCH /api/runs/{id}/disfluency-restore`), **edl** splits selected segment speech into alternating `speech` and `disfluency` sub-clips at original source times.

## Artifacts

| Path | Role |
|------|------|
| `master/disfluency_restore_plan.json` | Per-segment confirmed event placement |
| `master/edl.json` | EDL clips with `type: "disfluency"` |

## Mix behavior

- **assembly_preview** and **mix** load disfluency clips from `source_path` (WAV under `transcript/disfluency_clips/`).
- Disfluency clips use `disfluency_restore.crossfade_ms` (default 30ms) when appended in mix.
- SFX beds/stingers that would overlap disfluency timeline windows are skipped in mix.

## Operator toggle

On the EDL / assembly preview stage, use **Include confirmed fillers in assembly** then re-run `edl` to rebuild the EDL.

## Related

- Extract + review: [disfluency-extract.md](../transcription/disfluency-extract.md)
