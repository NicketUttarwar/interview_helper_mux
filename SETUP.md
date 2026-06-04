# Setup — interview_helper_mux

Complete this guide **before** `./scripts/run.sh`. The run script creates or refreshes `.venv`, installs Python deps, and builds the React GUI on first launch if needed — but it cannot substitute for system tools, cloud credentials, or optional model downloads you choose up front.

---

## Quick checklist (before `./scripts/run.sh`)

| Step | Required? | Command / action |
|------|-----------|------------------|
| System tools (Python, ffmpeg, AWS CLI) | Yes | See [Requirements](#requirements) |
| Node.js 20+ (`npm`, **native arch**) | Yes (GUI) | `node -v` · `npm -v` · `node -p process.arch` must match `uname -m` (see [GUI dependencies](#gui-dependencies-nodejs)) |
| Python venv + lock | Yes | `./scripts/bootstrap_venv.sh` → `source .venv/bin/activate` |
| Prerequisite gate | Yes | `./tools/check_prerequisites.sh` |
| Secrets | Yes | `cp config/templates/secrets.env.example config/secrets/secrets.env` and edit |
| AWS auth | Yes (Transcribe) | `aws sts get-caller-identity` |
| Source WAV | Yes (first run) | `ASSETS/input/<name>.wav` (or resume a prior `exec_*`) |
| GUI dependencies + build | Yes | `cd frontend && npm ci` then `./scripts/build_gui.sh` (or let `run.sh` build on first launch) |
| Local MLX LLM (Apple Silicon) | Recommended on macOS | Installed by `bootstrap_venv.sh` — [Local LLM](#local-llm-apple-silicon-default-on) |
| Value-analysis flags | No | Shipped defaults are on — [Value analysis](#value-analysis) |

---

## Requirements

| Dependency | Why |
|------------|-----|
| **macOS** (Apple Silicon tested) or **Linux** with equivalent packages | Primary dev target; MLX local LLM is **macOS only** |
| **Python 3.12** | On macOS Homebrew: `/opt/homebrew/bin/python3.12` |
| **ffmpeg** + **ffprobe** on `PATH` | Ingest, mix, mastering, QC |
| **AWS CLI** authenticated | `transcribe` stage uploads to S3 and polls AWS Transcribe |
| **Node.js 20+** and **npm** | Build `frontend/` → `src/interview_mux/web/static/` |
| **OpenAI**, **ElevenLabs**, **AWS** credentials | See [Config](#2-config) |

Pinned Python versions and CVE policy: [docs/cross-cutting/anchored-toolchain.md](docs/cross-cutting/anchored-toolchain.md).

### Install system tools (macOS example)

```bash
brew install python@3.12 ffmpeg awscli node@20
brew link --overwrite node@20   # if Homebrew printed a link hint
# Ensure node/npm are on PATH (native arm64 on Apple Silicon — see GUI section)
node -p process.arch   # arm64 when uname -m is arm64
aws configure   # or SSO — must pass: aws sts get-caller-identity
```

Linux: use your distro packages for `python3.12`, `ffmpeg`, `awscli`, and Node 20+.

On **Apple Silicon**, Node must be **arm64** (`node -p process.arch` → `arm64`). An x64 Node binary (Rosetta) installs the wrong Rollup native addon and breaks `npm run build`.

---

## 1. Clone and bootstrap

```bash
cd interview_helper_mux
./scripts/bootstrap_venv.sh
source .venv/bin/activate
./tools/check_prerequisites.sh
```

- `bootstrap_venv.sh` creates `.venv`, installs from `requirements.lock` (full transitive pins), and installs this package in editable mode.
- On **macOS**, bootstrap also installs `mlx-lm` / `huggingface_hub` and runs `scripts/select_local_llm.py --download` (or falls back to `download_local_llm.py`).
- Direct dependency edits go in `requirements.txt`; regenerate the lock with `pip-compile requirements.txt -o requirements.lock` (Python 3.12). Doc mirror: [docs/cross-cutting/anchored-requirements.lock](docs/cross-cutting/anchored-requirements.lock).
- `check_prerequisites.sh` verifies ffmpeg, ffprobe, aws, Python, `import interview_mux`, and runs `pip-audit` on the lock (fails on unaccepted **HIGH** / **CRITICAL** findings; override via `PIP_AUDIT_IGNORE_VULNS` / `PIP_AUDIT_FAIL_LEVEL` per anchored-toolchain).
- On macOS with `local_llm` enabled, prerequisites **warn** (non-fatal) if `llmfit`, `mlx-lm`, or weights under `ASSETS/local_llm/models/` are missing.

### GUI dependencies (Node.js)

Vite/Rollup ship **platform-specific** optional npm packages (for example `@rollup/rollup-darwin-arm64` on Apple Silicon). They are installed for **Node’s CPU architecture**, not the shell’s. A stale `frontend/node_modules` tree from another machine or arch, or npm’s optional-deps bug, causes `Cannot find module @rollup/rollup-darwin-arm64`.

**Verify before installing:**

```bash
node -v && npm -v
uname -m
node -p process.arch    # must match host: arm64↔arm64, x86_64↔x64
```

**Install (from repo root):**

```bash
cd frontend
npm ci                  # uses package-lock.json; reproducible
cd ..
./scripts/build_gui.sh
```

`./scripts/build_gui.sh` runs `npm ci` automatically when `node_modules` is missing or Rollup fails to load; it also checks Node arch vs `uname -m`.

After changing JSON Schemas under `docs/cross-cutting/json-schemas/`, regenerate GUI validators and rebuild:

```bash
python tools/codegen_zod_schemas.py
cd frontend && npm run build
```

Spec: [docs/cross-cutting/artifact-generation-and-validation.md](docs/cross-cutting/artifact-generation-and-validation.md).

`./scripts/run.sh` invokes the same script when `src/interview_mux/web/static/index.html` is missing.

**If Rollup still errors** (wrong-arch tree or corrupted optional deps):

```bash
cd frontend
rm -rf node_modules
npm ci
cd ..
./scripts/build_gui.sh
```

| Symptom | Fix |
|---------|-----|
| `@rollup/rollup-darwin-arm64` not found, host is arm64 | `rm -rf frontend/node_modules && cd frontend && npm ci` |
| `process.arch` is `x64` but `uname -m` is `arm64` | Prefer native arm64 Node (`brew install node@20`); x64 Node needs `@rollup/rollup-darwin-x64` in `node_modules`, not `-arm64` |
| `npm ci` fails on lock mismatch | Regenerate lock on your machine: `cd frontend && npm install` (commit updated `package-lock.json` only if intentional) |

---

## 2. Config

```bash
cp config/templates/secrets.env.example config/secrets/secrets.env
```

Edit at minimum:

| Variable | Used for |
|----------|----------|
| `OPENAI_API_KEY` | Analysis and flow LLM stages (after optional local MLX volley framing) |
| `ELEVENLABS_API_KEY` | SFX generation, optional audio pre-clean / isolation |
| `AWS_S3_BUCKET` | Transcribe job input/output |
| `AWS_DEFAULT_REGION` | Transcribe + S3 |

Optional secrets:

| Variable | Used for |
|----------|----------|
| `INPUT_AUDIO_PATH` | CLI/automation default WAV when not using GUI picker |
| `LOCAL_LLM_MODEL_ID` | Override mlx-community model id |

Key reference: [docs/cross-cutting/config-keys.md](docs/cross-cutting/config-keys.md).

Placeholders in `secrets.env.example` for other STT vendors (AssemblyAI, Deepgram, etc.) are **not wired** in code — do not expect them to work until an adapter ships.

Verify AWS:

```bash
aws sts get-caller-identity
```

Merged config: `config/app.defaults.json` + `config/secrets/secrets.env`. Notable shipped defaults:

| Key | Default | Notes |
|-----|---------|-------|
| `web_port` | `8765` | Web GUI URL |
| `local_llm.enabled` | `true` | OpenAI fallback when MLX/weights unavailable |
| `journey_ui.enabled` | `true` | Phase sidebar, story board, unified preclean drawer |
| `value_analysis.enabled` | `true` | GUI panel + tools; set `false` to disable |
| `value_analysis.auto_extract_after_content_context` | `true` | Writes `understanding/value_features.json` after `content_context` |
| `narrative_qc.strict` / `edl_qc.strict` / `edl_narrative_qc.strict` / `show_description_qc.strict` | `true` | Block or warn per stage validators |

---

## Local LLM (Apple Silicon, default on)

**Default:** `local_llm.enabled: true` in `config/app.defaults.json`. On **macOS**, bootstrap installs `mlx-lm` and uses [llmfit](https://github.com/AlexsJones/llmfit) to pick the **largest context-window** `mlx-community/*` model that fits your hardware with **good+** fit and **medium+** quality, then downloads weights. Every LLM stage can run local volley framing before OpenAI. If MLX, llmfit, or weights are missing, the pipeline **falls back to the full OpenAI volley** (no hard failure).

On **Linux**, MLX is unavailable — OpenAI volleys are used regardless of `local_llm.enabled`.

To turn off: set `"local_llm": { "enabled": false }` in config.

### 1. Install llmfit (macOS)

```bash
brew install AlexsJones/llmfit/llmfit
# or without sudo:
curl -fsSL https://llmfit.axjns.dev/install.sh | sh -s -- --local
```

### 2. Auto setup (recommended)

```bash
source .venv/bin/activate
python scripts/select_local_llm.py --download --verify
```

Or re-run full bootstrap (skips llmfit if `ASSETS/local_llm/selection.json` and weights already exist):

```bash
./scripts/bootstrap_venv.sh
```

Force re-scan after RAM/GPU changes:

```bash
LOCAL_LLM_REFRESH=1 ./scripts/bootstrap_venv.sh
# or:
python scripts/select_local_llm.py --refresh --download --verify
```

### Paths (gitignored under `ASSETS/`)

| Path | Purpose |
|------|---------|
| `ASSETS/local_llm/selection.json` | llmfit choice + metadata |
| `ASSETS/local_llm/models/<slug>/` | MLX weights |
| `ASSETS/local_llm/hf_cache/` | Hugging Face hub cache |

### Manual override

In `config/secrets/secrets.env`:

```bash
LOCAL_LLM_MODEL_ID=mlx-community/Qwen2.5-7B-Instruct-4bit
```

Or edit `local_llm.model_id` in `config/app.defaults.json`. Priority: `LOCAL_LLM_MODEL_ID` → `selection.json` → config default.

### Troubleshooting

| Issue | Action |
|-------|--------|
| `llmfit` not found | Install via brew/curl above; `check_prerequisites.sh` warns only |
| No eligible mlx-community models | Falls back to `mlx-community/Llama-3.2-3B-Instruct-4bit` |
| `mlx-lm` missing | `./scripts/bootstrap_venv.sh` or `pip install mlx-lm huggingface_hub` |
| Weights missing | `python scripts/select_local_llm.py --download` |
| Note on first `run.sh` | Warns if weights missing when `local_llm` enabled |

Direct download (skip llmfit):

```bash
python scripts/download_local_llm.py --install-deps --model mlx-community/Llama-3.2-3B-Instruct-4bit
python scripts/download_local_llm.py --verify
```

Docs: [docs/cross-cutting/local-llm-tier.md](docs/cross-cutting/local-llm-tier.md).

---

## Value analysis

Shipped in `config/app.defaults.json` with **`value_analysis.enabled: true`** (code treats missing key as `false` if you strip the block). Sub-flags:

| Flag | Shipped default | Effect |
|------|-----------------|--------|
| `value_analysis.enabled` | `true` | Master switch for CLIs and GUI panel |
| `value_analysis.auto_extract_after_content_context` | `true` | Writes `understanding/value_features.json` after `content_context` |
| `value_analysis.transcript_features` | `true` | Transcript-derived metrics |
| `value_analysis.audio_features` | `true` | Audio profile from `ingest/normalized.wav` |
| `value_analysis.spike_scoring` | `true` | Enables spike scorecard tooling |

To disable for a lean run: set `"value_analysis": { "enabled": false }` in config or secrets overlay.

Docs: [docs/pipeline/value-analysis/README.md](docs/pipeline/value-analysis/README.md).

```bash
python tools/extract_value_features.py --run-id <exec_id> --profile all
python tools/run_value_spike.py --scorecard <path-to-scorecard.json>
```

Not in default `pipeline.py` stage orders — hooks and CLIs only.

---

## 3. Media

Place source audio under:

```text
ASSETS/input/interview.wav
```

Or pick any `.wav` from the GUI **Input audio** list after launch. Heavy media stays under `ASSETS/` (gitignored). GUI-created runs live under `ASSETS/executions/exec_*` and resume after restart — see [docs/cross-cutting/assets-and-executions.md](docs/cross-cutting/assets-and-executions.md).

Headless fallback: set `INPUT_AUDIO_PATH` in secrets for CLI-only workflows.

---

## 4. Run

### Web GUI (recommended)

```bash
./scripts/run.sh
# equivalent:
source .venv/bin/activate && python -m interview_mux serve
# or:
interview-mux serve
```

| Option / env | Effect |
|--------------|--------|
| `--port` / `--host` / `--no-browser` | Passed through to `interview-mux serve` |
| `MUX_FRESH_SESSION=0` | Keep `ASSETS/.gui/active_execution.json` and related session files across restarts (default `1` clears them) |
| `./scripts/run.sh --cli …` | Headless: `python -m interview_mux …` without starting the web server |

Default URL: `http://127.0.0.1:8765` (`web_port` in config).

Operator phases: **Prepare → Understand → Complete → Create → Ship** — [docs/workflows/operator-journey.md](docs/workflows/operator-journey.md). Tab layout, modals, and checkpoints: [docs/workflows/operator-flow-audit.md](docs/workflows/operator-flow-audit.md). **Clear session** (header menu) clears both browser state and server active run.

### CLI (headless)

Create or resume a run via GUI first, or allocate with `interview-mux` / tools:

```bash
# Shared analysis (ingest → transcribe → … → optimal_questions)
python tools/run_analysis.py --run-id exec_001_20260523T120000Z

# After G0/G1/G2 in GUI (or set selected_flow via API/CLI):
python tools/run_flow.py --flow flow1 --run-id exec_001_20260523T120000Z
python tools/run_flow.py --flow flow2 --run-id exec_001_20260523T120000Z
python tools/run_flow.py --flow flow3 --run-id exec_001_20260523T120000Z

# Full pipeline in one shot (needs --flow after analysis):
interview-mux run --run-id exec_001_20260523T120000Z --flow flow1
interview-mux analysis --run-id exec_001_20260523T120000Z --analysis-only
```

Subcommands: `interview-mux analysis`, `flow`, `serve`, `run` (see `interview-mux --help`).

Flow 3 produces text only. Flow 1/2 produce `master.wav` under `flow_1_master/` or `flow_2_highlights/`.

---

## 5. Quality checks (before sign-off)

```bash
python tools/verify_master.py ASSETS/executions/<exec_id>/flow_1_master/master.wav
python tools/validate_narrative.py --run-id <exec_id> --include-edl
python tools/verify_edl.py --run-id <exec_id>   # schema-only EDL diagnostic
python tools/validate_nle.py --run-id <exec_id>
python tools/validate_show_description.py --run-id <exec_id>   # flow3
python tools/export_llm_calls.py --run-id <exec_id> -o /tmp/llm_calls.md
```

When `narrative_qc.strict` / `edl_qc.strict` / `edl_narrative_qc.strict` are true (shipped default), pipeline stages enforce the same rules; CLIs are for preflight and debugging.

---

## 6. Validate

| Check | Doc |
|-------|-----|
| Operator smoke | [docs/workflows/smoke-test.md](docs/workflows/smoke-test.md) |
| Release sign-off | [docs/build-out/definition-of-done-signoff.md](docs/build-out/definition-of-done-signoff.md) |
| Automated tests | `source .venv/bin/activate && pytest tests/` |

`pytest` and `pip-audit` are installed via `requirements.lock` / bootstrap (also listed under `[project.optional-dependencies] dev` in `pyproject.toml`).

---

## What is still being built?

**In code:** Waves 0–7, gap-closure GC track, G1.5 prompt review, BUILD-084 LLM harness, journey UI, flows 1–3, value-analysis hooks — **shipped**.

**Remaining:** Documentation sweeps (Commands 2–9 in [docs/build-out/remaining-build-commands.md](docs/build-out/remaining-build-commands.md)), optional value-analysis spike docs (Command 7), and **manual** E2E sign-off per [definition-of-done-signoff.md](docs/build-out/definition-of-done-signoff.md). Product quality vs target master: [docs/cross-cutting/podcast-quality-roadmap.md](docs/cross-cutting/podcast-quality-roadmap.md).

---

## Docs map

| Doc | Purpose |
|-----|---------|
| [docs/INDEX.md](docs/INDEX.md) | Documentation hub |
| [README.md](README.md) | Repo entry (scripts, tools, status) |
| [AGENTS.md](AGENTS.md) | Agent constraints and read order |
| [docs/build-out/repository-map.md](docs/build-out/repository-map.md) | Code ↔ docs layout |
| [docs/build-out/stage-registry.md](docs/build-out/stage-registry.md) | Every stage id |
| [docs/build-out/remaining-build-commands.md](docs/build-out/remaining-build-commands.md) | Remaining Agent command queue |
| [docs/workflows/troubleshooting.md](docs/workflows/troubleshooting.md) | Common failures |

## Troubleshooting

[docs/workflows/troubleshooting.md](docs/workflows/troubleshooting.md)
