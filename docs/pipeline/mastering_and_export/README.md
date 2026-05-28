# Mastering and export

Final loudness, limiting, and export.

## Tickets

BUILD-036 (Flow 1), BUILD-044 (Flow 2), BUILD-050 (shared module)

## Tools

**pyloudnorm**, **ffmpeg** — [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md)

## Targets

| Flow | LUFS | Notes |
|------|------|-------|
| Flow 1 | −16 | Podcast standard |
| Flow 2 | −14 | Slightly hotter for social |

## Outputs

| Path | Description |
|------|-------------|
| `flow_1_master/master.wav` | Full episode |
| `flow_2_highlights/master.wav` | Short reel |

Flow 3 has **no mastering step** — text export only. See [publishing/README.md](../publishing/README.md).

## QA

`python tools/verify_master.py <path> [--flow flow1|flow2]` — integrated LUFS and true peak per [evaluation-metrics.md](../../cross-cutting/evaluation-metrics.md) (BUILD-070). Infers flow from path (`flow_1_master` / `flow_2_highlights`) or use `--flow`.

If the master sounds noisy after listen-test, offer [pre-clean](../audio_preclean/README.md) and re-run from mux/ingest per operator choice — see [podcast-quality-roadmap.md](../../cross-cutting/podcast-quality-roadmap.md).

## Module

`src/interview_mux/mastering_bus.py` — pyloudnorm assembly-bus measurement (BUILD-071)

`src/interview_mux/stages/mastering.py` — assembly measure + ffmpeg true-peak limiter (BUILD-071); QA via BUILD-070

---

## Build-out

BUILD-036, BUILD-044, BUILD-050, BUILD-070–071 · [README.md](../../build-out/README.md) · [steps-forward.md](../../build-out/steps-forward.md)
