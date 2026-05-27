# Smoke test

End-to-end validation checklist for a new machine.

## Prerequisites

Install from the **anchor lock** (exact pins in repo-root `requirements.lock`; doc mirror: [anchored-requirements.lock](../cross-cutting/anchored-requirements.lock)). Policy: [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md).

```bash
./scripts/bootstrap_venv.sh   # venv + pip install -r requirements.lock
source .venv/bin/activate
./tools/check_prerequisites.sh # ffmpeg, ffprobe, aws, Python 3.12.x, pip-audit on lock, import smoke
```

**Fail fast:** If `pip-audit` reports HIGH/CRITICAL CVEs against the lock, refresh the lock or record an accepted advisory in [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md#accepted-advisories) before continuing.

## Config

- `config/secrets/secrets.env` has `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `AWS_S3_BUCKET`, `AWS_DEFAULT_REGION`
- `aws sts get-caller-identity` succeeds
- `ASSETS/input/interview.wav` exists (or set `INPUT_AUDIO_PATH`)

## Analysis

```bash
python tools/run_analysis.py
```

**Future (after smart routing implementation):** spot-check `understanding/stage_runs/<stage>/attempt_001.json` for `arbiter_result.verdict: accept` on at least one LLM stage; long-interview fixture should show `shard_count` > 0 when decompose fires — [llm-orchestration.md](../cross-cutting/llm-orchestration.md).

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

## Flow 3

**Status:** Not runnable until **BUILD-045** / **BUILD-080** (no `publishing_flow3.py` or `run_flow3` in `pipeline.py` yet). Spec: [publishing/README.md](../pipeline/publishing/README.md).

When implemented:

```bash
python tools/run_flow.py --flow flow3 --run-id run_001
# Expect flow_3_description/show_description.json (and .md when BUILD-046 ships)
```

**Expectations:** Third-person blurb ~150–250 words; no `master.wav`. Inspect JSON in GUI artifact editor or `cat flow_3_description/show_description.md`.

## Pass criteria

- No unhandled exceptions
- Master WAV plays; duration > 0
- `ffprobe` reports valid sample rate

## If something fails

Use [troubleshooting.md](./troubleshooting.md) and [operator-stage-checklists.md](./operator-stage-checklists.md) to narrow the stage, then [feedback-loops-and-reruns.md](./feedback-loops-and-reruns.md) for `--from-stage` commands.
