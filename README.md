# interview_helper_mux

Turn a long-form interview recording into **three possible deliverables** (operator picks one after shared analysis):

1. **Full master podcast** — reordered speech, VO bridges, cohesive SFX mix, mastered WAV
2. **Highlight reel** — up to five clips with montage SFX, mastered WAV
3. **Podcast show description** — ~200-word third-person blurb (text export; no audio mux)

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
| **Full build-out guide** | [docs/build-out/implementation-guide.md](docs/build-out/implementation-guide.md) |
| Application flow (E2E) | [docs/build-out/full-application-flow.md](docs/build-out/full-application-flow.md) |
| Stage registry | [docs/build-out/stage-registry.md](docs/build-out/stage-registry.md) |
| Ticket acceptance | [docs/build-out/ticket-specs.md](docs/build-out/ticket-specs.md) |
| Pipeline overview | [docs/pipeline.md](docs/pipeline.md) |
| Agent guide | [AGENTS.md](AGENTS.md) |
| Build-out tickets | [docs/build-out/README.md](docs/build-out/README.md) |
| Repo map | [docs/build-out/repository-map.md](docs/build-out/repository-map.md) |
| Steps forward | [docs/build-out/steps-forward.md](docs/build-out/steps-forward.md) |
| Remaining build commands | [docs/build-out/remaining-build-commands.md](docs/build-out/remaining-build-commands.md) |
| Release sign-off | [docs/build-out/definition-of-done-signoff.md](docs/build-out/definition-of-done-signoff.md) |
| Operator gates | [docs/workflows/operator-gates.md](docs/workflows/operator-gates.md) |
| GUI ↔ API | [docs/workflows/gui-surface-map.md](docs/workflows/gui-surface-map.md) |

## Layout

```text
ASSETS/          # input audio + per-run executions (gitignored)
config/          # defaults + secrets
docs/            # authoritative specs and prompts
src/interview_mux/   # Python package (pipeline + Web GUI)
tools/             # run_analysis, run_flow, verify_master, validate_narrative, verify_edl, value-analysis CLIs
scripts/         # bootstrap, run.sh
tests/           # pytest
```

## Implementation status

Shared **analysis** (ingest → transcribe → review → understanding → gaps), **Flow 1/2** mix paths (`mix_flow1` / `mix_flow2` → mastered WAV), **Flow 3** publishing copy, and a **FastAPI Web GUI** are shipped. Stage ids: [docs/build-out/stage-registry.md](docs/build-out/stage-registry.md). Release sign-off: [docs/build-out/definition-of-done-signoff.md](docs/build-out/definition-of-done-signoff.md).

**v1 honesty:** Mix quality and operator polish still trail the target in [docs/cross-cutting/podcast-quality-roadmap.md](docs/cross-cutting/podcast-quality-roadmap.md) — listen-test every `master.wav`; use `tools/verify_master.py`, `tools/validate_narrative.py`, and `tools/verify_edl.py` before calling a run done.
