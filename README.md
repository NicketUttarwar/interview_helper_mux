# interview_helper_mux

Turn a long-form interview recording into **three possible deliverables** (operator picks one after shared analysis):

1. **Full master podcast** — reordered speech, transitions, SFX path (v1 export is speech-only until mix waves land)
2. **Highlight reel** — up to five clips with montage SFX
3. **Podcast show description** — ~200-word third-person blurb *(spec + prompt; pipeline BUILD-045)*

## Quick start

See **[SETUP.md](SETUP.md)** for bootstrap, secrets, and first run.

```bash
./scripts/bootstrap_venv.sh && source .venv/bin/activate
./scripts/run.sh
```

## Documentation

| Resource | Link |
|----------|------|
| Doc hub | [docs/INDEX.md](docs/INDEX.md) |
| Pipeline overview | [docs/pipeline.md](docs/pipeline.md) |
| Agent guide | [AGENTS.md](AGENTS.md) |
| Build-out tickets | [docs/build-out/README.md](docs/build-out/README.md) |
| Repo map | [docs/build-out/repository-map.md](docs/build-out/repository-map.md) |
| Steps forward | [docs/build-out/steps-forward.md](docs/build-out/steps-forward.md) |
| Operator gates | [docs/workflows/operator-gates.md](docs/workflows/operator-gates.md) |
| GUI ↔ API | [docs/workflows/gui-surface-map.md](docs/workflows/gui-surface-map.md) |

## Layout

```text
ASSETS/          # input audio + per-run executions (gitignored)
config/          # defaults + secrets
docs/            # authoritative specs and prompts
src/interview_mux/   # Python package (pipeline + Web GUI)
tools/             # run_analysis, run_flow, verify_master
scripts/         # bootstrap, run.sh
tests/           # pytest
```

## Implementation status

Shared **analysis** (ingest → transcribe → review → understanding → gaps) and **Flow 1/2** audio paths are implemented with a **FastAPI Web GUI**. Target podcast mix (VO + beds + measured loudness) is documented in [docs/cross-cutting/podcast-quality-roadmap.md](docs/cross-cutting/podcast-quality-roadmap.md) and tracked in [docs/build-out/steps-forward.md](docs/build-out/steps-forward.md).

**v1 honesty:** Flow 1 `master.wav` is reordered speech concat; do not treat it as the final mixed episode until BUILD-065/067 ship.
