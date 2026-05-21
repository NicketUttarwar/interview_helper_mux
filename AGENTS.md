# Agent guide — interview_helper_mux (presets A–E)

## North star

Turn one long interview recording into transcript, ranked segments, and a muxed podcast master. **`docs/` is authoritative**; sync into SQLite after doc edits:

```bash
python tools/sync_to_sqlite.py
```

## Preset ladder (canonical letters)

| # | Preset | Scope in this repo |
|---|--------|-------------------|
| A | Highlight reel | **Shipped path** — `tools/run_preset_a.py` |
| B | Chapter podcast | Metadata on A backbone |
| C | Director's cut | Budgeted selection + diversity |
| D | Nonlinear story | Graph EDL (`networkx`) |
| E | **Room and breath polish** | `tools/run_preset_e.py` (gated DSP) |
| F | Bilingual / code-switch | **Docs only** — deferred |
| G–K | S2S, ranker, YOLO, Wav2Vec, dub | **Docs only** |

**E = Room polish, F = Bilingual** (swapped from legacy docs in Phase 0).

## MCP (approved trio)

Configured in `.cursor/mcp.json`:

1. **SQLite** — `data/interview_mux.sqlite` (runs, segments, doc_search)
2. **Filesystem** — `ASSETS/` waveforms and processed stems
3. **Transcription** — placeholder; point at your STT MCP for preset A iteration

## Python layout

| Path | Role |
|------|------|
| `ai/python/mux_secrets/` | In-memory secrets (no `os.environ` mutation) |
| `ai/python/openai_mux/` | LLM ranking |
| `ai/python/aws_mux/` | **AWS CLI** subprocess only |
| `db/python/mux_store/` | SQLite store + doc sync |
| `pipeline/` | Ingest → STT → seg → score → mux → DSP |

## Setup

See **[SETUP.md](SETUP.md)** — **Python 3.12**, native **arm64** on Apple Silicon, repo `.venv`:

```bash
eval "$(/opt/homebrew/bin/brew shellenv)"
export PYTHON=/opt/homebrew/bin/python3.12   # optional pin
./scripts/bootstrap_venv.sh                  # or install_venv_deps.sh if venv already arm64/3.12
source .venv/bin/activate
```

No `PYTHONPATH`. Confirm `uname -m` is `arm64` before bootstrapping (Rosetta causes native-wheel import failures).

**AWS:** AWS CLI v2 assumed authenticated; S3/region/profile in `config/secrets/secrets.env` (not boto3).

## Pipeline CLIs

Set `INTERVIEW_ID`, `INPUT_AUDIO_PATH` in `config/secrets/secrets.env` (see `config/README.md`), then:

```bash
python tools/run_ingest.py
python tools/run_stt.py --provider faster-whisper
python tools/run_preset_a.py --top-n 8 --skip-stt
python tools/run_preset_e.py --approve-dsp
```

## Rules

See `.cursor/rules/*.mdc` — especially `preset-ladder-a-e.mdc` and `aws-cli-only.mdc`.
