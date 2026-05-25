# interview_helper_mux

Turn a raw interview recording into **two investor-facing deliverables**:

1. **Full master podcast** — complete narrative with optimal segment ordering and subtle sound design
2. **Highlight reel** — up to five punchy clips with montage-style SFX

## Quick start

```bash
# 1. Config
cp config/templates/secrets.env.example config/secrets/secrets.env
# Edit secrets.env — OpenAI, AWS S3, ElevenLabs

# 2. Place source audio
mkdir -p ASSETS/input
cp /path/to/your/interview.wav ASSETS/input/interview.wav

# 3. Run web GUI (creates .venv if needed, opens browser at http://127.0.0.1:8765)
./scripts/run.sh

# Headless CLI (legacy):
./scripts/run.sh --cli --flow flow1

# Analysis only (stops before flow / G2):
./scripts/run.sh --analysis-only
```

See [SETUP.md](SETUP.md) for host prerequisites (ffmpeg, AWS CLI).

## Documentation

- [docs/README.md](docs/README.md) — spec index
- [docs/INDEX.md](docs/INDEX.md) — flat doc hub
- [docs/build-out/README.md](docs/build-out/README.md) — agent build tickets
- [AGENTS.md](AGENTS.md) — rules for autonomous agents

## Layout

| Path | Purpose |
|------|---------|
| Path | Purpose |
|------|---------|
| `ASSETS/` | Input audio (gitignored) |
| `ASSETS/executions/exec_NNN_TIMESTAMP/` | Per-run artifacts (JSON + WAV) — primary storage |
| `ASSETS/.gui/` | Active execution pointer + server session |
| `data/run_NNN/` | Legacy run storage (still supported) |
| `docs/prompts/` | LLM system prompts (envelope + shared preamble) |
| `understanding/analysis_state.json` | Per-interview profile (themes, questions, style) — edit in GUI |
| `src/interview_mux/` | Python pipeline |
| `tools/` | CLI entry points |
| `config/` | Defaults and secrets |
