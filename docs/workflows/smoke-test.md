# Smoke test

End-to-end validation checklist for a new machine.

## Prerequisites

```bash
./scripts/bootstrap_venv.sh
source .venv/bin/activate
./tools/check_prerequisites.sh
```

## Config

- `config/secrets/secrets.env` has `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `AWS_S3_BUCKET`, `AWS_DEFAULT_REGION`
- `aws sts get-caller-identity` succeeds
- `ASSETS/input/interview.wav` exists (or set `INPUT_AUDIO_PATH`)

## Analysis

```bash
python tools/run_analysis.py
```

Expect under `data/run_001/`:

- `ingest/normalized.wav`
- `transcript/full.json`
- `segments/manifest.json`
- `understanding/gap_report.json`
- `analysis_complete.json`

If G1 triggers, record VO to `vo_pickup/` and re-run with `--from-stage vo_ingest`.

**Optional at G1:** If pickup recordings are noisy, accept VO-scoped pre-clean offer (BUILD-072) before continuing.

## Flow 1

```bash
python tools/run_flow.py --flow flow1
python tools/verify_master.py data/run_001/flow_1_master/master.wav
```

**Expectations:** v1 produces a playable `master.wav` (reordered speech). Full VO+SFX mix is not validated until BUILD-065/067. LUFS checks are BUILD-070.

## Flow 2

Use a fresh run or separate `run_002` after analysis:

```bash
python tools/run_flow.py --flow flow2 --run-id run_001
python tools/verify_master.py data/run_001/flow_2_highlights/master.wav
```

## Pass criteria

- No unhandled exceptions
- Master WAV plays; duration > 0
- `ffprobe` reports valid sample rate
