# Local configuration

**Runtime:** Python **3.12** in repo `.venv` (see [SETUP.md](../SETUP.md)). Activate with `source .venv/bin/activate` before running tools.

## Single source of truth

| File | Purpose |
|------|---------|
| `config/app.defaults.json` | Committed defaults: SQLite path, `ASSETS/` root, `input_audio_path` |
| `config/secrets/secrets.env` | **Your** API keys and per-machine overrides (gitignored) |

**Resolution order** for pipeline tools: CLI flag → `secrets.env` → `app.defaults.json`.

**Session ids** are auto-allocated (`run_001`, `run_002`, …) on each `run_ingest.py` — not configured.

### One file to copy and edit

```bash
mkdir -p config/secrets ASSETS/input
cp config/templates/secrets.env.example config/secrets/secrets.env
# edit secrets.env — keys, INPUT_AUDIO_PATH, AWS_S3_* as needed
```

Place your raw interview WAV at the path in `INPUT_AUDIO_PATH` (default `ASSETS/input/interview.wav`).

**Loading:** `mux_secrets.load_repo_config()` reads optional `config/secrets/openai.env`, then `config/secrets/secrets.env` (duplicate keys: **`secrets.env` wins**). Values stay in memory only; `os.environ` is not modified.

## `config/app.defaults.json`

| Key | Meaning |
|-----|---------|
| `database_path` | SQLite file (relative to repo root unless absolute) |
| `assets_root` | On-disk media tree (default `ASSETS`) |
| `input_audio_path` | Raw WAV for `tools/run_ingest.py` when CLI/`INPUT_AUDIO_PATH` omitted |

## `config/secrets/secrets.env` — keys

### Run targets (override app.defaults)

| Key | Used by |
|-----|---------|
| `INPUT_AUDIO_PATH` | `run_ingest` |

### Integrations

| Package | Keys |
|---------|------|
| `openai_mux` | `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_SPEECH_MODEL` |
| `aws_mux` | `AWS_PROFILE` and/or `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` / `AWS_REGION` |
| `elevenlabs_mux` | `ELEVENLABS_API_KEY` |

### AWS Transcribe (`run_stt.py --provider aws`)

Assume **AWS CLI v2 is already authenticated** (`~/.aws` or keys in `secrets.env`). Set **one** of:

- `AWS_S3_URI=s3://bucket/key.wav`
- `AWS_S3_BUCKET` + `AWS_S3_INPUT_KEY`

Smoke: `tools/aws_smoke.py` (no extra setup commands in SETUP.md).

### Legacy `openai.env`

Merged before `secrets.env`; prefer consolidating into `secrets.env`.

## What reads these files

- **Paths / sessions:** `mux_store.run_config` (`allocate_session_id`, `resolve_active_session_id`, `resolve_input_audio_path`, `resolve_s3_uri`)
- **Secrets:** all packages under `ai/python/*` via `mux_secrets.get_config_value`

Pipeline CLIs accept optional `--input`, `--s3-uri` to override config for one-off runs.
