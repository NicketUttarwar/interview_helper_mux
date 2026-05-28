# Audio editing

Trim boundaries, build EDL from selection, and prepare clips for mix.

## Tickets

BUILD-032 (Flow 1 transitions JSON), BUILD-035 (EDL), BUILD-043 (Flow 2 clips), BUILD-067 (EDL wiring), BUILD-068 (NLE → selection/EDL), BUILD-069 (planned)

## Tools

**ffmpeg**, **pydub** (mix engine, planned) — [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md)

## Inputs

| Path | Description |
|------|-------------|
| `ingest/normalized.wav` | Source speech (from pre-clean lineage when used) |
| `*/selection.json` | Ordered segments or clips |
| `vo_pickup/*.wav` | Human interviewer lines (G1); optional `vo_pickup/clean/` after pickup pre-clean |
| `flow_1_master/transitions.json` | Interviewer bridges (target: consumed in EDL/mix) |
| `segments/nle_edits.json` | Operator timeline overrides (applied in ranking + EDL, BUILD-068) |

## Outputs

| Path | Description |
|------|-------------|
| `flow_1_master/edl.json` | Continuous timeline — speech, VO, placements |
| `flow_1_master/assembly_preview.wav` | Speech + VO only (planned, BUILD-069) |
| `flow_1_master/assembly.wav` | Pre-master mux |
| Clip extracts in temp dir | Flow 2 |

## Rules

- Avoid mid-word cuts (target: short crossfades 50–150 ms at jumps, planned)
- Flow 2 allows harder cuts between clips
- Gap report placements appear in EDL (`edl_flow1`, BUILD-067); audible VO in assembly is BUILD-065/069

## Quality offers

Before final concat/mix, operator may accept [pre-clean](../audio_preclean/README.md) on full normalized audio if the assembly preview sounds noisy.

## Module

`assembly_flow1.py`, `assembly_flow2.py` — see [assembly_and_mux](../assembly_and_mux/README.md)

---

## Build-out

BUILD-032, BUILD-067–069 · [README.md](../../build-out/README.md) · [steps-forward.md](../../build-out/steps-forward.md)
