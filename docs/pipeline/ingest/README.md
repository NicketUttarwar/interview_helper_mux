# Ingest

Normalize source audio and allocate run workspace.

## Ticket

BUILD-020

## Tools

**ffmpeg** — version anchor: [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md#system-binaries)

## Inputs

| Path | Description |
|------|-------------|
| `run_meta.json` → `input_audio_path` | Source WAV chosen at run creation (GUI asset picker or CLI); typically `ASSETS/input/…` |
| `preclean/isolated.wav` | When [audio pre-clean](../audio_preclean/README.md) ran — ingest uses this instead of raw capture |

Run workspace: `ASSETS/executions/exec_NNN_…/` ([assets-and-executions.md](../../cross-cutting/assets-and-executions.md)).

## Outputs

| Path | Description |
|------|-------------|
| `ingest/normalized.wav` | 48 kHz PCM WAV, peak-safe |
| `ingest/checksums.json` | SHA-256 of source + normalized |

## Re-run after pre-clean

If the operator accepts a **full-source** pre-clean offer at any checkpoint, invalidate from `audio_preclean` (or `ingest`) and re-run ingest → transcribe → downstream. See [idempotent-runs.md](../../workflows/idempotent-runs.md).

**Pickup-only** pre-clean at G1 does not require re-ingest of the interview — only `vo_ingest` and assembly stages that use `vo_pickup/`.

## Success criteria

- `normalized.wav` exists, duration > 0
- `ffprobe` reports 48000 Hz (or configured rate)
- When pre-clean ran: `checksums.json` includes `preclean_sha256`

## Module

`src/interview_mux/stages/ingest.py` (pre-clean input: BUILD-019)

---

## Build-out

BUILD-020 · [README.md](../../build-out/README.md) · [repository-map.md](../../build-out/repository-map.md)
