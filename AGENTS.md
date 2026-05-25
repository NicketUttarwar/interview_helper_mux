# Agent guide — interview_helper_mux

Rules for autonomous agents implementing or running this pipeline.

## Read order

1. [docs/build-out/README.md](docs/build-out/README.md) — ticket sequence and dependencies
2. [docs/cross-cutting/podcast-quality-roadmap.md](docs/cross-cutting/podcast-quality-roadmap.md) — v1 vs target master, priority waves
3. [docs/workflows/operator-gates.md](docs/workflows/operator-gates.md) — gates + optional quality offers (incl. pre-clean)
4. [docs/pipeline.md](docs/pipeline.md) — two flows, stage overview
5. [docs/cross-cutting/artifact-layout.md](docs/cross-cutting/artifact-layout.md) — file paths per run

## Hard constraints

- **Python 3.12** in `.venv` at repo root; bootstrap via `scripts/bootstrap_venv.sh`
- **AWS**: use `aws` CLI subprocess only — **no boto3**
- **Secrets**: load from `config/secrets/secrets.env` — never commit, never hardcode
- **Media**: default input `./ASSETS/`; ask for full path if missing
- **Docs/prompts** are authoritative for LLM behavior — do not drift copy without updating specs

## Operator gates (mandatory)

| Gate | When | Action |
|------|------|--------|
| **G0** | After `transcript_review_build` | Operator corrects STT in GUI (confidence-ranked clips); sign off before `speaker_roles` |
| **G1** | After `run_analysis.py` | If `delivery: record` lines lack `vo_pickup/*.wav`, stop until operator records |
| **G2** | After G1 cleared | Ask: `flow1` (full podcast) or `flow2` (highlight reel) |

**Quality offers (optional, not gates):** Offer background noise removal at documented checkpoints — before ingest, after G0, **after G1 pickup recordings** (`vo_pickup` scope), before mix. Never auto-enable. See [docs/pipeline/audio_preclean/README.md](docs/pipeline/audio_preclean/README.md).

Do not run Flow 1 extended analysis (BUILD-029+) unless `run_meta.json` has `selected_flow: flow1`.

**v1 assembly:** Flow 1 mux is speech-only; do not claim VO/SFX are in `master.wav` until BUILD-065/067 ship.

## Idempotency

- Each stage writes `data/run_NNN/.stage_done/<stage_name>`
- Re-run a stage only if upstream artifacts exist and operator requests it
- See [docs/workflows/idempotent-runs.md](docs/workflows/idempotent-runs.md)

## What not to build in v1

- SQLite / mux_store
- boto3, preset ladder A–E from old repo

## Web GUI

Launch with `./scripts/run.sh` (default) or `python -m interview_mux serve`. The GUI reads/writes all state from `data/run_NNN/` JSON files on disk.

## Testing changes

```bash
./tools/check_prerequisites.sh
python tools/run_analysis.py --run-id run_001
python tools/verify_master.py data/run_001/flow_1_master/master.wav
```
