# Agent guide — interview_helper_mux

Rules for autonomous agents implementing or running this pipeline.

## Read order

1. [docs/roadmap/future-proofing.md](docs/roadmap/future-proofing.md) — future-proofing guardrails + small R&D directions (audio-only; optional research track)
2. [docs/build-out/README.md](docs/build-out/README.md) — ticket sequence and dependencies
3. [docs/cross-cutting/podcast-quality-roadmap.md](docs/cross-cutting/podcast-quality-roadmap.md) — v1 vs target master, priority waves
4. [docs/workflows/operator-gates.md](docs/workflows/operator-gates.md) — gates + optional quality offers (incl. pre-clean)
5. [docs/workflows/operator-stage-checklists.md](docs/workflows/operator-stage-checklists.md) — **per-stage verification**; extend this file whenever you add a stage, gate, GUI panel, or quality offer
6. [docs/workflows/gui-surface-map.md](docs/workflows/gui-surface-map.md) — GUI panels ↔ FastAPI routes ↔ `gui_log.jsonl` / `gui_job.json` ↔ artifacts
7. [docs/workflows/api-reference.md](docs/workflows/api-reference.md) — full `/api/*` contract (companion to the GUI map)
8. [docs/pipeline.md](docs/pipeline.md) — three flows, stage overview
9. [docs/cross-cutting/artifact-layout.md](docs/cross-cutting/artifact-layout.md) — file paths per run
10. [docs/cross-cutting/config-keys.md](docs/cross-cutting/config-keys.md) — `config/app.defaults.json` + merged `secrets.env` keys

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
| **G2** | After G1 cleared | Ask: `flow1` (full podcast), `flow2` (highlight reel), or `flow3` (show description) |

**Quality offers (optional, not gates):** Offer background noise removal at documented checkpoints — before ingest, after G0, **after G1 pickup recordings** (`vo_pickup` scope), before mix. Never auto-enable. See [docs/pipeline/audio_preclean/README.md](docs/pipeline/audio_preclean/README.md).

Do not run Flow 1 extended analysis (BUILD-029+) unless `run_meta.json` has `selected_flow: flow1`.

**v1 assembly:** Flow 1 mux is speech-only; do not claim VO/SFX are in `master.wav` until BUILD-065/067 ship.

## Idempotency

- Each stage writes `data/run_NNN/.stage_done/<stage_name>` (or under `ASSETS/executions/.../.stage_done/`)
- Re-run a stage only if upstream artifacts exist and operator requests it
- See [docs/workflows/idempotent-runs.md](docs/workflows/idempotent-runs.md)

## What not to build in v1

- SQLite / mux_store
- boto3, preset ladder A–E from old repo

## Web GUI

Launch with `./scripts/run.sh` (default) or `python -m interview_mux serve`. The GUI reads/writes run state from the **run directory** (`ASSETS/executions/exec_*` or legacy `data/run_*`) via the FastAPI routes in `src/interview_mux/web/server.py`.

- **Operator status/logs:** `.cursor/rules/interview-helper-mux.mdc` (Centralized operator status and logs). GUI wiring: [docs/workflows/gui-surface-map.md](docs/workflows/gui-surface-map.md).
- **Long runs / LLM context:** see [docs/workflows/long-interview-chunking.md](docs/workflows/long-interview-chunking.md).

## Audio / STT reference docs

- [docs/pipeline/transcription/stt-and-diarization.md](docs/pipeline/transcription/stt-and-diarization.md) — STT + diarization catalog (AWS = implemented)
- [docs/pipeline/transcription/source-separation-and-enhancement.md](docs/pipeline/transcription/source-separation-and-enhancement.md) — denoise / separation options
- [docs/cross-cutting/elevenlabs-integration-guide.md](docs/cross-cutting/elevenlabs-integration-guide.md) — ElevenLabs REST SFX + isolation (canonical)
- [docs/cross-cutting/elevenlabs-prompt-influence-tuning.md](docs/cross-cutting/elevenlabs-prompt-influence-tuning.md) — `prompt_influence` tuning
- [docs/prompts/_shared/examples/elevenlabs-prompt-regression.md](docs/prompts/_shared/examples/elevenlabs-prompt-regression.md) — golden prompt QA

## Testing changes

```bash
./tools/check_prerequisites.sh
python tools/run_analysis.py --run-id run_001
python tools/verify_master.py data/run_001/flow_1_master/master.wav
```
