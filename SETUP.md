# Setup

## Host tools

| Tool | Purpose |
|------|---------|
| **ffmpeg** | Ingest normalize, cut, mux, export |
| **aws** CLI | S3 upload + Transcribe (authenticated) |
| **Python 3.12** | `/opt/homebrew/bin/python3.12` on Apple Silicon |

```bash
brew install ffmpeg awscli
./scripts/run.sh --analysis-only   # creates .venv on first run
./tools/check_prerequisites.sh
```

Optional manual venv setup: `./scripts/bootstrap_venv.sh`

## Config

```bash
cp config/templates/secrets.env.example config/secrets/secrets.env
cp config/templates/app.defaults.json config/app.defaults.json  # if needed
```

Required keys in `config/secrets/secrets.env`:

| Key | Purpose |
|-----|---------|
| `OPENAI_API_KEY` | All LLM stages |
| `AWS_DEFAULT_REGION` | Transcribe region |
| `AWS_S3_BUCKET` | Upload normalized WAV |
| `ELEVENLABS_API_KEY` | SFX generation (both flows) |

Optional: `INPUT_AUDIO_PATH` overrides `config/app.defaults.json`.

AWS auth: use `aws configure` or env keys in secrets. Transcribe reads from `s3://bucket/key`.

## ASSETS layout

```
ASSETS/
  input/
    interview.wav    # default source
```

## First run

```bash
./scripts/run.sh
# If G1 blocks (missing VO), record files under data/run_NNN/vo_pickup/ then:
./scripts/run.sh --skip-analysis --flow flow1
```

See [docs/workflows/smoke-test.md](docs/workflows/smoke-test.md) for validation checklist.
