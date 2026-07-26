# Audio editing

Trim boundaries, build EDL from selection, and prepare clips for mix.

## Tickets

BUILD-032 (Flow 1 transitions JSON), BUILD-035 (EDL), BUILD-043 (Flow 2 clips), BUILD-067 (EDL wiring), BUILD-068 (NLE → selection/EDL, shipped), BUILD-069 (assembly preview, shipped)

## Tools

**ffmpeg**, **pydub** (mix engine, shipped) — [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md)

## Inputs

| Path | Description |
|------|-------------|
| `ingest/normalized.wav` | Source speech (from pre-clean lineage when used) |
| `*/selection.json` | Ordered segments or clips |
| `vo_pickup/*.wav` | Human interviewer lines (G1); optional `vo_pickup/clean/` after pickup pre-clean |
| `master/transitions.json` | Interviewer bridges (consumed in EDL/mix) |
| `segments/nle_edits.json` | Operator timeline overrides (applied in ranking + EDL, BUILD-068, shipped) |

## Outputs

| Path | Description |
|------|-------------|
| `master/edl.json` | Continuous timeline — speech, VO, placements (schema: `verify_edl.py`; timeline: `validate_edl.py`; narrative: `validate_narrative.py --include-edl`) |
| `master/assembly_preview.wav` | Speech + VO only (BUILD-069, shipped) |
| `master/assembly.wav` | Pre-master mix (`mix`) |
| Clip extracts (in-memory pydub slices; optional temp WAV export not required for mix) | Flow 2 |

## Rules

- Avoid mid-word cuts — `mix.word_boundary_cuts` snaps slice ends to transcript word boundaries when `transcript/full.json` is present
- Flow 2 allows harder cuts between clips
- Gap report placements in EDL (`edl`, BUILD-067); VO + SFX audible via `mix` / `REMOVED_mix_flow2`

## Quality offers

Before final concat/mix, operator may accept [pre-clean](../audio_preclean/README.md) on full normalized audio if the assembly preview sounds noisy.

## Module

`assembly.py`, `REMOVED_assembly_flow2.py` — see [assembly_and_mux](../assembly_and_mux/README.md)

**QA:** `tools/verify_edl.py`, `tools/validate_edl.py`, `tools/validate_narrative.py --include-edl` — [evaluation-metrics.md](../../cross-cutting/evaluation-metrics.md)
