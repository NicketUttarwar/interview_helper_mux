# Local configuration

## `config/secrets/` — API keys and integration settings

Put **only** machine-local values under `config/secrets/`. The entire `config/secrets/` tree is in `.gitignore`, so nothing there is committed.

### One file to copy and edit

1. Create the directory and copy the example:

   ```bash
   mkdir -p config/secrets
   cp config/templates/secrets.env.example config/secrets/secrets.env
   ```

2. Open `config/secrets/secrets.env` and fill in keys (OpenAI, AWS, ElevenLabs, and any optional keys listed in the template).

3. **Loading:** `mux_secrets.load_repo_config()` reads `config/secrets/openai.env` (if present), then `config/secrets/secrets.env`, so **duplicate keys are taken from `secrets.env`**. Values are kept **in memory only**; the process `os.environ` is **not** modified.

## `config/app.defaults.json` — paths and non-secret defaults

The repository ships `config/app.defaults.json` (committed). It currently defines:

- **`database_path`** — default SQLite file path, relative to the repository root unless absolute.

`tools/sync_to_sqlite.py` uses this file when `--db` is omitted. Override by passing `--db` or editing `database_path`.

## What reads these files

All integration packages under `ai/python/` call `mux_secrets.load_repo_config()` before reading credentials from the in-memory map (`get_config_value`, …):

| Package | Purpose | Keys in `secrets.env` |
|---------|---------|------------------------|
| `mux_secrets` | Parses `openai.env` then `secrets.env` | — |
| `openai_mux` | OpenAI chat / ranking | `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_SPEECH_MODEL` |
| `aws_mux` | `boto3` sessions | `AWS_PROFILE` **or** `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`, plus `AWS_DEFAULT_REGION` / `AWS_REGION` |
| `elevenlabs_mux` | ElevenLabs TTS / voice | `ELEVENLABS_API_KEY` |

Smoke scripts: `tools/openai_smoke.py`, `tools/aws_smoke.py`, `tools/elevenlabs_smoke.py`.

### AWS region

Set **`AWS_DEFAULT_REGION`** (and optionally **`AWS_REGION`** to the same value) in `secrets.env`. `aws_mux` passes the region into `boto3.Session` from that file only.

### Legacy `openai.env`

If you already use `config/secrets/openai.env`, it is merged first; **`secrets.env` overwrites the same key**. Prefer consolidating into `secrets.env` when convenient.
