# Mastering and export

Final loudness, limiting, and export for the **single** podcast master. Optional RSS packaging is separate — [publishing/README.md](../publishing/README.md).

## Tools

**pyloudnorm**, **ffmpeg** — [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md)

## Targets

| Deliverable | LUFS | Notes |
|-------------|------|-------|
| `master/master.wav` | −16 | Podcast standard (`target_lufs` / `flow1_target_lufs`) |

## Outputs

| Path | Description |
|------|-------------|
| `master/master.wav` | Full episode (north star) |
| `publish/` | Optional G-Publish local package (mp3, cover, meta) — no S3 until sync |

## QA

```bash
python tools/verify_master.py ASSETS/executions/<exec_id>/master/master.wav
```

Enforces integrated LUFS −16 ±1, true peak ≤ −1 dBTP — [evaluation-metrics.md](../../cross-cutting/evaluation-metrics.md).

If the master sounds noisy after listen-test, offer [pre-clean](../audio_preclean/README.md) and re-run from mux/ingest per operator choice.

## Modules

- `src/interview_mux/mastering_bus.py` — pyloudnorm assembly-bus measurement
- `src/interview_mux/stages/mastering.py` — `master_finalize` (limiter + loudness)
- `src/interview_mux/junction_snip_qa.py` — pre-master junction repair

## Heritage

Flow 2 (−14 LUFS reel) and Flow 3 (text-only) mastering/export paths were removed.
