# Ingest

Normalize source audio (sample rate / mono **and** default loudness stabilize) and allocate run workspace.

## Ticket

BUILD-020

## Tools

**ffmpeg** (`dynaudnorm` + `loudnorm`) — version anchor: [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md#system-binaries)

## Inputs

| Path | Description |
|------|-------------|
| `run_meta.json` → `input_audio_path` | Source WAV chosen at run creation (GUI asset picker or CLI); typically `ASSETS/input/…` |
| `preclean/isolated.wav` | When [audio pre-clean](../audio_preclean/README.md) ran — ingest uses this instead of raw capture |

Run workspace: `ASSETS/executions/exec_NNN_…/` ([assets-and-executions.md](../../cross-cutting/assets-and-executions.md)).

## Loudness stabilize (default on)

After optional preclean, ingest applies a mild **dynaudnorm** (within-file leveling) then **loudnorm** to **−18 LUFS** / −1.5 dBTP so quiet captures are enjoyable for STT review and listening. Final `master_finalize` still loudnorms the mix to podcast **−16 LUFS**.

Config: `ingest.loudness_stabilize.*` — [config-keys.md](../../cross-cutting/config-keys.md). Set `enabled: false` for format-only ingest.

## Outputs

| Path | Description |
|------|-------------|
| `ingest/normalized.wav` | 48 kHz mono PCM WAV, loudness-stabilized (default) |
| `ingest/loudness.json` | Filter lineage (`af_filter`, targets) |
| `ingest/checksums.json` | SHA-256 of source + normalized (+ preclean when used) |

## Re-run after pre-clean

If the operator accepts a **full-source** pre-clean offer at any checkpoint, invalidate from `audio_preclean` (or `ingest`) and re-run ingest → transcribe → downstream. See [idempotent-runs.md](../../workflows/idempotent-runs.md).

**Pickup-only** pre-clean at G1 does not require re-ingest of the interview — only `vo_ingest` and assembly stages that use `vo_pickup/`.

## Success criteria

- `normalized.wav` exists, duration > 0
- `ffprobe` reports 48000 Hz (or configured rate)
- `loudness.json` records whether stabilize ran
- When pre-clean ran: `checksums.json` includes `preclean_sha256`

## Module

`src/interview_mux/stages/ingest.py` · `src/interview_mux/source_loudness.py` (pre-clean input: BUILD-019)
