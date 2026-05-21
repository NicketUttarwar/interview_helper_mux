# Setup and execution plan — interview_helper_mux

**Canonical environment:** **Python 3.12** (native **arm64** on Apple Silicon) in repo-root **`.venv`**.

**Readiness (Steps 0–5):** native terminal → host tools → venv + pip → config → tests.  
**Production (Step 6+):** real interview audio → listen → export — after Steps 0–5 pass.

**Each session**

```bash
cd /path/to/interview_helper_mux
source .venv/bin/activate
```

No `PYTHONPATH` — run targets and paths come from `config/secrets/secrets.env` and `config/app.defaults.json` (CLI flags optional overrides). See [config/README.md](config/README.md).

---

## What exists in this repo

| Layer | Status | Location |
|-------|--------|----------|
| Product spec | Living docs | `docs/` (~59 Markdown files, FTS in SQLite) |
| Canonical store | Implemented | `db/schema.sql`, `db/python/mux_store/` |
| Secrets + adapters | Implemented | `ai/python/mux_secrets/`, `openai_mux/`, `aws_mux/`, `elevenlabs_mux/` |
| Pipeline A–E | Runnable scaffold | `pipeline/` + `tools/run_*.py` |
| Presets F–K | Docs only | `docs/execution/complexity-ladder-end-to-end-ideas.md` |

| Preset | CLI | Lightweight test |
|--------|-----|------------------|
| Store + docs | `tools/sync_to_sqlite.py` | `python tools/check_env.py` |
| Ingest | `tools/run_ingest.py` | `--help`; pytest ingest leg |
| STT | `tools/run_stt.py` | `--help`; pytest STT (`tiny`) |
| Segment + rank | `tools/run_segment.py` | `--help` |
| A — Highlight reel | `tools/run_preset_a.py` | pytest end-to-end (`--no-llm`) |
| E — Room polish | `tools/run_preset_e.py` | `--help` (optional re-polish; DSP also runs in preset A) |
| OpenAI rank | `openai_mux` | `tools/openai_smoke.py` |
| AWS STT | `aws_mux` | `tools/aws_smoke.py` |
| ElevenLabs | `elevenlabs_mux` | `tools/elevenlabs_smoke.py` |

---

## Gate checklist

| Step | Command | Pass means |
|------|---------|------------|
| **0** | `uname -m` → `arm64` (Apple Silicon) | Not Rosetta (`x86_64` / `i386`) |
| **1** | `./tools/check_prerequisites.sh` | ffmpeg, Python 3.12+ arm64, loudnorm |
| **2** | `./scripts/bootstrap_venv.sh` *or* `./scripts/install_venv_deps.sh` | packages importable |
| **2b** | `python tools/verify_install.py` | all `OK`, arch OK |
| **3** | `python tools/check_env.py` | secrets + doc sync |
| **4** | `pytest -q` | fast tests green |
| **4b** | `pytest -q -m slow` | pipeline smoke (macOS: auto speech via `say`) |
| **3b** | `*_smoke.py` | API connectivity (keys in `secrets.env`) |
| **6+** | `run_ingest` → … → `run_preset_e` | WAV outputs |

---

## Step 0 — Native shell (Apple Silicon only)

Before installing Python or creating `.venv`, confirm the **terminal** is not running under Rosetta:

```bash
uname -m    # must be arm64
arch        # must be arm64 (not i386 / x86_64)
```

| `uname -m` | Action |
|------------|--------|
| `arm64` | Continue |
| `x86_64` | Quit Terminal → **Get Info** on Terminal.app (or iTerm) → **uncheck** “Open using Rosetta” → new window. Or: `arch -arm64 zsh` for this session only |

Same check for **Cursor** integrated terminal: Cursor.app → Get Info → uncheck Rosetta if needed.

---

## Step 1 — System prerequisites

### Homebrew (Apple Silicon)

```bash
eval "$(/opt/homebrew/bin/brew shellenv)"   # add to ~/.zprofile for new shells
which brew                                  # /opt/homebrew/bin/brew
brew install ffmpeg python@3.12
```

`/opt/homebrew` is the Apple Silicon prefix. **`/usr/local`** Homebrew is often **x86_64** — do not use it for this repo’s venv.

Confirm Python **before** creating `.venv`:

```bash
/opt/homebrew/bin/python3.12 -c "import platform; print(platform.machine())"
# must print: arm64
```

```bash
./tools/check_prerequisites.sh
```

| Check | If missing |
|-------|------------|
| Python **3.12+** (native arm64) | `brew install python@3.12` |
| ffmpeg + ffprobe | `brew install ffmpeg` |
| loudnorm filter | Reinstall ffmpeg |
| AWS CLI v2 on `PATH` | Optional — only for `--provider aws` or `tools/aws_smoke.py` (assume already authenticated) |

**Avoid on Apple Silicon:** bare `python3.12` from `/usr/local` (x86_64), Rosetta terminals, and Intel-only `python3.11` — they cause `pydantic_core` / `numba` **architecture mismatch** errors at import time.

---

## Step 2 — Python environment (`.venv`)

All dependencies live in **`requirements.txt`** (includes editable install `-e .`). Minimum declared in `pyproject.toml`: **Python 3.12**.

### Fresh install (recommended)

```bash
cd /path/to/interview_helper_mux
chmod +x scripts/bootstrap_venv.sh tools/check_prerequisites.sh
eval "$(/opt/homebrew/bin/brew shellenv)"

# Pin interpreter (recommended on Apple Silicon)
export PYTHON=/opt/homebrew/bin/python3.12
./scripts/bootstrap_venv.sh
```

This **removes** any existing `.venv`, creates a new one with the picked interpreter, and runs `pip install -r requirements.txt` + `python tools/verify_install.py`.

### Existing `.venv` (refresh deps only)

If `.venv` was already built with **arm64 Python 3.12** (check with the verify command below):

```bash
source .venv/bin/activate
./scripts/install_venv_deps.sh
```

Do **not** use `install_venv_deps.sh` to fix a broken arch — run `bootstrap_venv.sh` instead.

### Manual install

```bash
eval "$(/opt/homebrew/bin/brew shellenv)"
export PYTHON=/opt/homebrew/bin/python3.12
"$PYTHON" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel
pip install --prefer-binary -r requirements.txt
python tools/verify_install.py
```

### Verify interpreter and imports

```bash
source .venv/bin/activate
python -c "import sys, platform; print(sys.version); print(sys.executable); print(platform.machine())"
# expect: 3.12.x, .../.venv/bin/python, arm64 (on M1/M2/M3)

python -c "import mux_secrets, mux_store, pipeline; from pipeline.common import repo_root; print(repo_root())"
```

---

## Step 3 — Config and SQLite store

```bash
mkdir -p config/secrets ASSETS/input
cp config/templates/secrets.env.example config/secrets/secrets.env
# edit secrets.env: INPUT_AUDIO_PATH, API keys, AWS_S3_* as needed
# place your raw WAV at INPUT_AUDIO_PATH (default ASSETS/input/interview.wav)
python tools/check_env.py
python tools/sync_to_sqlite.py
```

Committed defaults: `config/app.defaults.json`. Per-machine overrides and API keys: `config/secrets/secrets.env`. See [config/README.md](config/README.md).

---

## Step 3b — Integration smoke (optional)

Assume cloud CLIs and SDK keys are already set up outside this doc. Repo tools only read `config/secrets/secrets.env` (optional overlay for AWS region/profile/keys).

```bash
source .venv/bin/activate
python tools/openai_smoke.py      # needs OPENAI_API_KEY in secrets.env
python tools/aws_smoke.py         # needs AWS CLI v2 already authenticated
python tools/elevenlabs_smoke.py  # needs ELEVENLABS_API_KEY in secrets.env
```

For AWS Transcribe later, set `AWS_S3_URI` or `AWS_S3_BUCKET` + `AWS_S3_INPUT_KEY` in `secrets.env` (see [config/README.md](config/README.md)).

---

## Step 4 — Automated validation

```bash
source .venv/bin/activate
pytest -q
pytest -q tests/test_prerequisites.py
pytest -q -m slow tests/test_pipeline_smoke.py   # optional; may download Whisper models
```

Prefer **`.venv/bin/pytest`** if a global `pytest` points at another Python.

Speech fixture: [tests/fixtures/README.md](tests/fixtures/README.md).

---

## Step 5 — Gotchas

| Gotcha | Fix |
|--------|-----|
| `incompatible architecture` / `pydantic_core` dlopen | Rebuild `.venv` on **arm64** Python 3.12 — Step 0 + `./scripts/bootstrap_venv.sh` with `PYTHON=/opt/homebrew/bin/python3.12` |
| `uname -m` is `x86_64` | Rosetta terminal — Step 0 |
| `/opt/homebrew/bin/python3.12` missing | `brew install python@3.12` after `brew shellenv` |
| Preset A re-runs STT | `run_stt.py` once, then `run_preset_a.py --skip-stt` |
| Double loudnorm | `--skip-ingest-loudnorm` or `--skip-master-lufs` |
| Skip DSP (debug only) | `run_preset_a.py --skip-dsp` |
| Import errors | `source .venv/bin/activate` then `pip install -r requirements.txt` |
| Ad-hoc `*.whl` in repo root | Do not `pip install` them — wrong arch breaks native extensions |

**Production order:** `run_ingest` → `run_stt` → `run_preset_a --skip-stt` (DSP included in preset A)

---

## Step 6+ — Production pipeline

1. Set `INPUT_AUDIO_PATH` in `config/secrets/secrets.env` (or rely on `config/app.defaults.json`).
2. Copy your raw interview WAV to `INPUT_AUDIO_PATH` (default `ASSETS/input/interview.wav`).

```bash
source .venv/bin/activate
python tools/sync_to_sqlite.py

python tools/run_ingest.py
python tools/run_stt.py --provider faster-whisper --model-size base
python tools/run_preset_a.py --top-n 8 --skip-stt
# Note session_id printed by ingest; polished master is under ASSETS/run_NNN/processed/
python tools/verify_master.py ASSETS/run_001/processed/room_polish_master.wav
```

Each ingest allocates the next session (`run_001`, `run_002`, …). CLI flags (`--input`, `--s3-uri`) override config for one-off runs.

**AWS STT:** set `AWS_S3_URI` or `AWS_S3_BUCKET` + `AWS_S3_INPUT_KEY` in `secrets.env`, then `python tools/run_stt.py --provider aws`.

Without OpenAI ranking: add `--no-llm` to `run_preset_a.py`.

---

## Outputs

```text
ASSETS/<session-id>/   # e.g. run_001, run_002 (auto-allocated)
  ingest/normalized.wav
  transcripts/<revision>.json
  snippets/manifest.json
  mux/highlight_reel.wav
  master/highlight_master.wav
  processed/room_polish_master.wav   # shippable polished master (mandatory DSP)
data/interview_mux.sqlite
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `No module named 'pipeline'` | `source .venv/bin/activate` && `pip install -r requirements.txt` |
| `have 'arm64', need 'x86_64'` (or reverse) | Mixed-arch venv — `rm -rf .venv` && `./scripts/bootstrap_venv.sh` with `PYTHON=/opt/homebrew/bin/python3.12` |
| `zsh: no such file or directory: /opt/homebrew/bin/python3.12` | Install Apple Silicon Homebrew + `brew install python@3.12` |
| `python3.12` reports `x86_64` | Wrong binary on PATH — use full path `/opt/homebrew/bin/python3.12` |
| `ffmpeg failed` | `brew install ffmpeg` |
| Re-run room polish only | `python tools/run_preset_e.py` |
| pip / setuptools errors | `pip install 'setuptools>=68,<82'` then `pip install -r requirements.txt` |

---

## Quick reference

| Command | Purpose |
|---------|---------|
| `uname -m` | Step 0 — must be `arm64` on Apple Silicon |
| `eval "$(/opt/homebrew/bin/brew shellenv)"` | Load Apple Silicon Homebrew |
| `./tools/check_prerequisites.sh` | Step 1 |
| `export PYTHON=/opt/homebrew/bin/python3.12` | Pin interpreter before bootstrap |
| `./scripts/bootstrap_venv.sh` | New `.venv` + full pip install |
| `./scripts/install_venv_deps.sh` | Refresh deps in existing `.venv` |
| `pip install -r requirements.txt` | Step 2 (inside active venv) |
| `python tools/verify_install.py` | Step 2 gate |
| `python tools/check_env.py` | Step 3 |
| `pytest -q` | Step 4 |

See also: [README.md](README.md), [AGENTS.md](AGENTS.md), [config/README.md](config/README.md).

---

## FYI — Apple Silicon environment recovery (validated path)

This section records a real setup path on an **M1 Mac** where pytest failed with `pydantic_core` **incompatible architecture** (`have 'arm64', need 'x86_64'`). Root cause: **Rosetta terminal** (`uname -m` → `x86_64`) and/or **x86_64 Python** on PATH while some wheels were arm64.

**Working end state**

- Terminal: `uname -m` → `arm64`, `arch` → `arm64`
- Homebrew: `which brew` → `/opt/homebrew/bin/brew`
- Python: `/opt/homebrew/bin/python3.12` → `platform.machine()` → `arm64`
- Venv: `.venv/bin/python` → **Python 3.12.13**, **arm64**
- Gates: `python tools/verify_install.py` → PASS; `pytest -q` → green

**Recovery sequence (summary)**

1. Disable **Open using Rosetta** for Terminal (and Cursor if used); open a new shell; confirm `uname -m` is `arm64`.
2. `eval "$(/opt/homebrew/bin/brew shellenv)"` — if `/opt/homebrew` was missing, install Homebrew from [brew.sh](https://brew.sh) in an arm64 shell (not `/usr/local`-only Intel brew).
3. `brew install python@3.12` — verify `/opt/homebrew/bin/python3.12` prints `arm64`.
4. `cd` to repo; `export PYTHON=/opt/homebrew/bin/python3.12`; `rm -rf .venv`; `./scripts/bootstrap_venv.sh`.
5. `source .venv/bin/activate`; `pytest -q`.

**Do not**

- Build `.venv` while `uname -m` is `x86_64`
- Use `/usr/local/bin/python3.12` for this project on Apple Silicon
- `pip install` random `*.whl` files dropped in the repo root (mixed arch)

If you already have a good **arm64 / 3.12** `.venv`, skip bootstrap and run `./scripts/install_venv_deps.sh` after pulling dependency changes.
