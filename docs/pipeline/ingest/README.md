# Ingest

Normalize source audio and allocate run workspace.

## Ticket

BUILD-020

## Tools

**ffmpeg** — version anchor: [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md#system-binaries)

## Inputs

| Path | Description |
|------|-------------|
| `ASSETS/input/interview.wav` | Raw source (configurable) |
| `preclean/isolated.wav` | When [audio pre-clean](../audio_preclean/README.md) ran — ingest uses this instead of raw capture |

## Outputs

| Path | Description |
|------|-------------|
| `data/run_NNN/ingest/normalized.wav` | 48 kHz PCM WAV, peak-safe |
| `data/run_NNN/ingest/checksums.json` | SHA-256 of source + normalized |

## Re-run after pre-clean

If the operator accepts a **full-source** pre-clean offer at any checkpoint, invalidate from `audio_preclean` (or `ingest`) and re-run ingest → transcribe → downstream. See [idempotent-runs.md](../../workflows/idempotent-runs.md).

**Pickup-only** pre-clean at G1 does not require re-ingest of the interview — only `vo_ingest` and assembly stages that use `vo_pickup/`.

## Success criteria

- `normalized.wav` exists, duration > 0
- `ffprobe` reports 48000 Hz (or configured rate)
- When pre-clean ran: `checksums.json` includes `preclean_sha256`

## Module

`src/interview_mux/stages/ingest.py` (pre-clean: BUILD-019, planned)

---

## Build-out

BUILD-020 · [README.md](../../build-out/README.md) · [repository-map.md](../../build-out/repository-map.md)
