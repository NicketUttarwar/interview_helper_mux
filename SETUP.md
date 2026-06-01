# Setup — interview_helper_mux

Greenfield install for the interview audio pipeline and Web GUI.

## Requirements

- **macOS** (developed on Apple Silicon) or Linux with equivalent tools
- **Python 3.12** — on this machine prefer `/opt/homebrew/bin/python3.12`
- **ffmpeg** and **ffprobe** on `PATH`
- **AWS CLI** authenticated (`aws sts get-caller-identity`)
- API keys in `config/secrets/secrets.env` (see below)

Pinned versions and CVE policy: [docs/cross-cutting/anchored-toolchain.md](docs/cross-cutting/anchored-toolchain.md).

## 1. Clone and bootstrap

```bash
cd interview_helper_mux
./scripts/bootstrap_venv.sh
source .venv/bin/activate
./tools/check_prerequisites.sh
```

`bootstrap_venv.sh` creates `.venv`, installs from `requirements.lock` (full transitive pins), and installs this package in editable mode. Direct dependency edits go in `requirements.txt`; regenerate the lock with `pip-compile requirements.txt -o requirements.lock` (Python 3.12). Doc mirror: [docs/cross-cutting/anchored-requirements.lock](docs/cross-cutting/anchored-requirements.lock).

`check_prerequisites.sh` runs `pip-audit` against the lock and fails on unaccepted **HIGH** / **CRITICAL** findings (`PIP_AUDIT_FAIL_LEVEL`, default `HIGH`).

## 2. Config

```bash
cp config/templates/secrets.env.example config/secrets/secrets.env
# Edit: OPENAI_API_KEY, ELEVENLABS_API_KEY, AWS_S3_BUCKET, AWS_DEFAULT_REGION
```

Key reference: [docs/cross-cutting/config-keys.md](docs/cross-cutting/config-keys.md).

### Optional: local LLM (Apple Silicon)

To pre-download an on-device framing model into the same `.venv` (plan — not yet wired to the pipeline):

```bash
source .venv/bin/activate
python scripts/download_local_llm.py --install-deps --model mlx-community/Llama-3.2-3B-Instruct-4bit
python scripts/download_local_llm.py --verify
```

Spec: [docs/cross-cutting/local-llm-tier.md](docs/cross-cutting/local-llm-tier.md).

## 3. Media

Place source audio under:

```text
ASSETS/input/interview.wav
```

Or set `INPUT_AUDIO_PATH` in secrets / defaults. Heavy media stays under `ASSETS/` (gitignored).

## 4. Run

**Web GUI (recommended):**

```bash
./scripts/run.sh
# or: python -m interview_mux serve
```

**CLI:**

```bash
python tools/run_analysis.py --run-id exec_001_20260523T120000Z
# After G0/G1/G2 in GUI or CLI:
python tools/run_flow.py --flow flow1 --run-id exec_001_20260523T120000Z
python tools/verify_master.py ASSETS/executions/exec_001_20260523T120000Z/flow_1_master/master.wav
python tools/validate_narrative.py --run-id exec_001_20260523T120000Z
python tools/verify_edl.py --run-id exec_001_20260523T120000Z
```

Flow 3 (show description): `python tools/run_flow.py --flow flow3 --run-id <exec_id>` after G2 — see [docs/workflows/smoke-test.md](docs/workflows/smoke-test.md).

## 5. Validate

Follow [docs/workflows/smoke-test.md](docs/workflows/smoke-test.md).

## Docs map

| Doc | Purpose |
|-----|---------|
| [docs/INDEX.md](docs/INDEX.md) | Documentation hub |
| [AGENTS.md](AGENTS.md) | Agent constraints and read order |
| [docs/build-out/repository-map.md](docs/build-out/repository-map.md) | Code ↔ docs layout |
| [docs/build-out/steps-forward.md](docs/build-out/steps-forward.md) | Prioritized backlog + **Cursor Agent copy-paste prompts** per step |

## Troubleshooting

[docs/workflows/troubleshooting.md](docs/workflows/troubleshooting.md)
