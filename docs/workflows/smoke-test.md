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
- At least one `.wav` under `ASSETS/` (recommended: `ASSETS/input/interview.wav`)

## GUI path (preferred)

1. `./scripts/run.sh`
2. Home → pick a file under **Input audio** (or resume **Previous executions**)
3. Note `run_id` (e.g. `exec_001_20260523T120000Z`) from the workspace header

**Resume check:** stop the server, run `./scripts/run.sh` again, open the same execution from **Previous executions** — stage markers and `gui_log.jsonl` should still be present under `ASSETS/executions/<run_id>/`.

See [assets-and-executions.md](../cross-cutting/assets-and-executions.md).

## Analysis (CLI)

```bash
python tools/run_analysis.py --run-id exec_001_20260523T120000Z
```

Use the `run_id` from the GUI step above. For headless-only setups, `INPUT_AUDIO_PATH` in `secrets.env` remains a fallback — not required when the run was created via the GUI asset picker.

**Future (after smart routing implementation):** spot-check `understanding/stage_runs/<stage>/attempt_001.json` for `arbiter_result.verdict: accept` on at least one LLM stage; long-interview fixture should show `shard_count` > 0 when decompose fires — [llm-orchestration.md](../cross-cutting/llm-orchestration.md).

Expect under `ASSETS/executions/exec_001_…/` (legacy: `data/run_001/`):

- `ingest/normalized.wav`
- `transcript/full.json`
- `segments/manifest.json`
- `understanding/gap_report.json`
- `analysis_complete.json`

If G1 triggers, record VO to `vo_pickup/` and re-run with `--from-stage vo_ingest`.

**Optional at G1:** If pickup recordings are noisy, accept VO-scoped pre-clean offer (BUILD-072) before continuing.

## Flow 1

```bash
python tools/run_flow.py --flow flow1 --run-id exec_001_20260523T120000Z
python tools/verify_master.py ASSETS/executions/exec_001_20260523T120000Z/flow_1_master/master.wav
```

**Expectations:** v1 produces a playable `master.wav` (reordered speech). Full VO+SFX mix is not validated until BUILD-065/067. `verify_master.py` now enforces LUFS and true-peak thresholds (Flow 1: -16 +/-1 LUFS, <= -1 dBTP) and exits non-zero on failure.

## Flow 2

Use a fresh run or separate `run_002` after analysis:

```bash
python tools/run_flow.py --flow flow2 --run-id exec_001_20260523T120000Z
python tools/verify_master.py ASSETS/executions/exec_001_20260523T120000Z/flow_2_highlights/master.wav
```

## Flow 3

After shared analysis and **G2** with `selected_flow: flow3`:

```bash
python tools/run_flow.py --flow flow3 --run-id exec_001_20260523T120000Z
```

**Expectations:**

- `flow_3_description/show_description.json` validates against the show-description schema
- `flow_3_description/show_description.md` exists (plain-text export)
- Third-person blurb ~150–250 words (`word_count` in JSON)
- No `master.wav` under the run directory

Inspect copy in the GUI artifact editor or:

```bash
cat ASSETS/executions/exec_001_20260523T120000Z/flow_3_description/show_description.md
```

Spec: [publishing/README.md](../pipeline/publishing/README.md).

## Pass criteria

- No unhandled exceptions
- Master WAV plays; duration > 0
- `verify_master.py` exits 0 for Flow 1 and Flow 2 masters

## If something fails

Use [troubleshooting.md](./troubleshooting.md) and [operator-stage-checklists.md](./operator-stage-checklists.md) to narrow the stage, then [feedback-loops-and-reruns.md](./feedback-loops-and-reruns.md) for `--from-stage` commands.
