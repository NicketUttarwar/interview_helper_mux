# Setup — interview_helper_mux

Complete this guide **before** `./scripts/run.sh`. **Install everything once** with `./scripts/install.sh` (same as `./scripts/bootstrap_venv.sh`): core `.venv` + dev tools, React GUI bundle, and isolated local stacks under `ASSETS/`. `./scripts/run.sh` only activates `.venv` and serves — it does not pip-install on every launch (use `MUX_REFRESH_DEPS=1` after `git pull`).

**Single install command:** `./scripts/install.sh` creates the core `.venv` plus all isolated local stacks under `ASSETS/` (MLX, DeepFilterNet, MMAudio), builds the GUI, clones upstream audio repos, downloads MLX weights on macOS Apple Silicon, prefetches optional STT weights, runs verify gates, and writes `install.json` manifests. If you delete any venv or clone tree, re-run this one script.

Per-stack requirements: `requirements.txt` (core), `requirements-local-mlx.txt`, `requirements-local-deepfilter.txt`, `requirements-local-mmaudio.txt`. See [Local audio stack](#local-audio-stack) and [docs/cross-cutting/local-audio-stack.md](docs/cross-cutting/local-audio-stack.md).

---

## Fresh install (copy-paste order)

Run from a clean clone on a new machine:

```bash
# 1. System tools (macOS example — see Requirements)
brew install python@3.12 ffmpeg awscli node@20 rust
brew link --overwrite node@20   # if Homebrew printed a link hint
node -p process.arch            # arm64 on Apple Silicon (must match uname -m)

# 2. Clone and install everything (venvs + GUI + repos + MLX weights + verify)
cd interview_helper_mux
./scripts/install.sh
source .venv/bin/activate

# 3. Confirm local stacks (required before preclean / SFX stages)
./scripts/verify_local_models.sh
./tools/check_prerequisites.sh
CHECK_LOCAL_RUNTIMES=1 ./tools/check_prerequisites.sh   # same verify, fails on missing stacks

# 4. Secrets + AWS
cp config/templates/secrets.env.example config/secrets/secrets.env   # edit keys
aws sts get-caller-identity

# 5. Source audio + launch
mkdir -p ASSETS/input
# copy your interview.wav → ASSETS/input/
./scripts/run.sh
```

**Optional but recommended on macOS:** install [llmfit](https://github.com/AlexsJones/llmfit) before bootstrap so MLX model selection is hardware-aware (`brew install AlexsJones/llmfit/llmfit`). Without llmfit, bootstrap downloads the default `mlx-community/Llama-3.2-3B-Instruct-4bit` weights.

Skip the post-install verify gate only: `BOOTSTRAP_SKIP_VERIFY=1 ./scripts/install.sh` — then run `./scripts/verify_local_models.sh` manually.

Headless / CI (Python only, no npm GUI build): `BOOTSTRAP_SKIP_GUI=1 ./scripts/install.sh`

---

## Quick checklist (before `./scripts/run.sh`)

| Step | Required? | Command / action |
|------|-----------|------------------|
| System tools (Python, ffmpeg, AWS CLI, **Rust**) | Yes | See [Requirements](#requirements) |
| Node.js 20+ (`npm`, **native arch**) | Yes (GUI) | `node -v` · `npm -v` · `node -p process.arch` must match `uname -m` (see [GUI dependencies](#gui-dependencies-nodejs)) |
| Python venv + lock | Yes | `./scripts/bootstrap_venv.sh` → `source .venv/bin/activate` |
| **Local model verify** | Yes (preclean/SFX) | `./scripts/verify_local_models.sh` |
| Prerequisite gate | Yes | `./tools/check_prerequisites.sh` |
| Secrets | Yes | `cp config/templates/secrets.env.example config/secrets/secrets.env` and edit |
| AWS auth | Yes (Transcribe) | `aws sts get-caller-identity` |
| Source WAV | Yes (first run) | `ASSETS/input/<name>.wav` (or resume a prior `exec_*`) |
| GUI dependencies + build | Yes | `cd frontend && npm ci` then `./scripts/build_gui.sh` (or let `run.sh` build on first launch) |
| Local MLX LLM (Apple Silicon) | Recommended on macOS | Installed by `bootstrap_venv.sh` — [Local LLM](#local-llm-apple-silicon-default-on) |
| Local audio stack (DeepFilterNet + MMAudio) | MMAudio **required** for SFX; DeepFilterNet optional (preclean) | Installed by `bootstrap_venv.sh` — [Local audio stack](#local-audio-stack) |
| faster-whisper (disfluency) | Optional | Prefetched by bootstrap; lexicon-only path works without weights — [Local STT](#local-stt-disfluency-extract-optional) |
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
| **Rust toolchain** (`rustc`, `cargo`) | DeepFilterNet builds native `pyDF` via **maturin** during bootstrap |
| **OpenAI**, **AWS** credentials | See [Config](#2-config) — no cloud audio API for SFX or preclean |

Pinned Python versions and CVE policy: [docs/cross-cutting/anchored-toolchain.md](docs/cross-cutting/anchored-toolchain.md).

### Install system tools (macOS example)

```bash
brew install python@3.12 ffmpeg awscli node@20 rust
brew link --overwrite node@20   # if Homebrew printed a link hint
# Ensure node/npm are on PATH (native arm64 on Apple Silicon — see GUI section)
node -p process.arch   # arm64 when uname -m is arm64
aws configure   # or SSO — must pass: aws sts get-caller-identity
```

Linux: use your distro packages for `python3.12`, `ffmpeg`, `awscli`, Node 20+, and Rust (`rustup` recommended).

On **Apple Silicon**, Node must be **arm64** (`node -p process.arch` → `arm64`). An x64 Node binary (Rosetta) installs the wrong Rollup native addon and breaks `npm run build`.

---

## 1. Clone and bootstrap

```bash
cd interview_helper_mux
./scripts/bootstrap_venv.sh
source .venv/bin/activate
./scripts/verify_local_models.sh
./tools/check_prerequisites.sh
```

What `bootstrap_venv.sh` does:

| Step | Output |
|------|--------|
| Core `.venv` | `requirements.lock` + editable `interview_mux` install |
| `ASSETS/local_llm/venv` | MLX volley framing (macOS Apple Silicon only) |
| `ASSETS/local_deepfilter/venv` | DeepFilterNet preclean (`maturin` + `pip install -e` upstream clone) |
| `ASSETS/local_mmaudio/venv` | MMAudio SFX (`pip install -e` upstream clone) |
| Git clones | `ASSETS/local_deepfilter/DeepFilterNet`, `ASSETS/local_mmaudio/MMAudio` |
| MLX weights (macOS) | `ASSETS/local_llm/models/<slug>/` via llmfit or default fallback |
| STT weights (optional) | `ASSETS/local_stt/models/` — non-fatal if download skipped |
| Verify + manifests | `scripts/verify_local_models.sh` + `ASSETS/local_*/install.json` |

- On **macOS Apple Silicon**, bootstrap runs `scripts/select_local_llm.py --download --verify` when **llmfit** is on `PATH`; otherwise it downloads the default `mlx-community/Llama-3.2-3B-Instruct-4bit` model.
- Bootstrap prefetches optional faster-whisper weights (`disfluency_extract`); lexicon-only mode works without them.
- Direct dependency edits go in `requirements.txt`; regenerate the lock with `pip-compile requirements.txt -o requirements.lock` (Python 3.12). Doc mirror: [docs/cross-cutting/anchored-requirements.lock](docs/cross-cutting/anchored-requirements.lock).
- `check_prerequisites.sh` verifies ffmpeg, ffprobe, aws, Python, `import interview_mux`, and runs `pip-audit` on the lock (fails on unaccepted **HIGH** / **CRITICAL** findings; override via `PIP_AUDIT_IGNORE_VULNS` / `PIP_AUDIT_FAIL_LEVEL` per anchored-toolchain).
- On macOS with `local_llm` enabled, prerequisites **warn** (non-fatal) if `llmfit`, `mlx-lm`, or weights under `ASSETS/local_llm/models/` are missing. Use `./scripts/verify_local_models.sh` or `CHECK_LOCAL_RUNTIMES=1 ./tools/check_prerequisites.sh` for a **strict** local-stack gate.

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

**Static bundle:** Vite writes hashed files to `src/interview_mux/web/static/assets/`. `./scripts/run.sh` rebuilds when `index.html` references missing assets (`interview_mux.gui_bundle`). The bundle is **committed** in git (operator-media ignore uses `/ASSETS/` at repo root only — not `web/static/assets/`). After frontend edits: `./scripts/build_gui.sh` and commit `static/` changes.

**Operator flow (full autopilot, default):** Click **Run** on an automated stage — the server resolves artifact issues in-process. If a choice is still needed, the **Stage Decision Wizard** appears one question at a time. Then **Review and save** staged outputs. Manual gates (G0, G0.5, profile, G1, G2) are unchanged. See [docs/workflows/full-autopilot-operator-model.md](docs/workflows/full-autopilot-operator-model.md).

`./tools/check_prerequisites.sh` warns when the bundle is incomplete; set `CHECK_GUI_BUNDLE=1` to fail instead of warn.

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
| `AWS_S3_BUCKET` | Transcribe job input/output |
| `AWS_DEFAULT_REGION` | Transcribe + S3 |

MMAudio SFX generation is local-only in the shipped stack (`ASSETS/local_mmaudio/...`) and does not require a cloud audio API key.

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
| `narrative_qc.strict` / `edl_qc.strict` / `edl_narrative_qc.strict` / `show_notes_qc.strict` | `true` | Block or warn per stage validators |

---

## Verify local models

After bootstrap, confirm every local stack the podcast pipeline needs:

```bash
source .venv/bin/activate
./scripts/verify_local_models.sh
```

Strict STT check (fail if faster-whisper weights missing):

```bash
STRICT_LOCAL_STT=1 ./scripts/verify_local_models.sh
```

| Stack | Downloaded when | On-disk path | Required for |
|-------|-----------------|--------------|--------------|
| **MLX LLM** | `bootstrap_venv.sh` (macOS) | `ASSETS/local_llm/models/<slug>/` | Local volley framing before OpenAI (fail-open to OpenAI) |
| **DeepFilterNet** | Bootstrap builds venv + clone; weights bundled in upstream | `ASSETS/local_deepfilter/` | Optional preclean (`audio_preclean`); needs **Rust** |
| **MMAudio** | Bootstrap builds venv + clone; **HF weights on first SFX generation** | `ASSETS/local_mmaudio/` | `mmaudio_sfx` / `flow2` |
| **CLAP (semantic QA)** | First MMAudio QA run when `mmaudio.semantic_qa_enabled: true` | Hugging Face cache in MMAudio venv | Tier-2 SFX semantic QA (fail-open) |
| **faster-whisper** | Bootstrap prefetch (optional) | `ASSETS/local_stt/models/` | `disfluency_extract` gap clips (lexicon works without) |

Per-stack verify commands (same checks as the script):

```bash
python scripts/download_local_llm.py --verify
ASSETS/local_deepfilter/venv/bin/python scripts/download_deepfilter.py --verify
ASSETS/local_mmaudio/venv/bin/python scripts/download_mmaudio.py --verify
python scripts/download_local_stt.py --verify
```

**Not downloaded at setup:** AWS Transcribe (cloud), OpenAI models (API), or interview source WAVs — place those under `ASSETS/input/` and configure secrets.

---

## Local LLM (Apple Silicon, default on)

**Default:** `local_llm.enabled: true` in `config/app.defaults.json`. On **macOS**, bootstrap installs `mlx-lm` and uses [llmfit](https://github.com/AlexsJones/llmfit) to pick the **largest context-window** `mlx-community/*` model that fits your hardware with **good+** fit and **medium+** quality, then downloads weights and runs Stage-1 `calibrate_local_llm.py` (capability manifest). Quality-allowlisted LLM stages may run a fail-fast local capability ladder (framer / digest / shard prep) before OpenAI; housekeeping stages do not. If MLX, llmfit, weights, or calibrate fail, the pipeline **falls back to the OpenAI volley** (non-fatal WARN).

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
| `ASSETS/local_llm/capability_manifest.json` | Stage-1 enabled caps + budgets |
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
| Capability calibrate failed | WARN only; degraded LX-01 path — re-run `python scripts/calibrate_local_llm.py --refresh` |
| Note on first `run.sh` | Warns if weights missing when `local_llm` enabled |

Direct download (skip llmfit):

```bash
python scripts/download_local_llm.py --install-deps --model mlx-community/Llama-3.2-3B-Instruct-4bit
python scripts/download_local_llm.py --verify
```

Docs: [docs/cross-cutting/local-llm-tier.md](docs/cross-cutting/local-llm-tier.md).

---

## Local audio stack

**Default:** `audio_preclean.provider: deepfilternet` and local MMAudio for SFX stages. Bootstrap clones [DeepFilterNet](https://github.com/rikorose/deepfilternet) and [MMAudio](https://github.com/hkchengrex/MMAudio) into separate gitignored trees and builds isolated venvs.

```bash
./scripts/bootstrap_venv.sh
# or manual:
./scripts/clone_local_audio_repos.sh
bash scripts/lib/bootstrap_local_runtimes.sh
./scripts/verify_local_models.sh
```

Verify:

```bash
ASSETS/local_deepfilter/venv/bin/python scripts/download_deepfilter.py --verify
ASSETS/local_mmaudio/venv/bin/python scripts/download_mmaudio.py --verify
# optional inference smoke (GPU/MPS recommended):
ASSETS/local_mmaudio/venv/bin/python scripts/download_mmaudio.py --verify --smoke-generate
```

**Manual MMAudio SFX smoke:** approve prompts on `sfx_prompt_craft` → run `mmaudio_sfx` → check `sound_design/mmaudio_qa.json` → post-listen in GUI (solo + under-speech preview via `GET …/audio/sfx-under-speech`). Tier-2 CLAP QA is **on by default** (`mmaudio.semantic_qa_enabled: true`); re-bootstrap the MMAudio venv so `transformers` + `librosa` are installed (first run downloads `laion/clap-htsat-fused`). CLAP fail-open: missing deps/timeouts set `semantic_qa_verdict=skipped`. See [sfx-prompt-regression.md](docs/prompts/_shared/examples/sfx-prompt-regression.md).

| Path | Purpose |
|------|---------|
| `ASSETS/local_deepfilter/DeepFilterNet/` | Upstream clone |
| `ASSETS/local_deepfilter/venv/` | DeepFilterNet venv |
| `ASSETS/local_mmaudio/MMAudio/` | Upstream clone |
| `ASSETS/local_mmaudio/venv/` | MMAudio venv |
| `ASSETS/local_*/install.json` | Bootstrap verify manifest |

**Existing runs:** Re-run from `sfx_prompt_craft` if artifacts used legacy `elevenlabs_*` stage markers or old `sound_design/elevenlabs_prompts.json`.

Docs: [docs/cross-cutting/local-audio-stack.md](docs/cross-cutting/local-audio-stack.md).

---

## Local STT (disfluency extract; optional)

When `disfluency_extract.enabled` is true (default), the pipeline detects filler words in inter-word gaps using energy VAD and optional **faster-whisper** on gap clips. Without Whisper weights, lexicon pass on transcript words still runs.

```bash
python scripts/download_local_stt.py --model base
python scripts/download_local_stt.py --verify
```

Weights: `ASSETS/local_stt/models/` (gitignored). Docs: [docs/pipeline/transcription/disfluency-extract.md](docs/pipeline/transcription/disfluency-extract.md).

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
| `MUX_PRESERVE_SESSION=1` | Keep `ASSETS/.gui/active_execution.json` and related session files on this launch (default clears them for a fresh Start tab) |
| `./scripts/run.sh --cli …` | Headless: `python -m interview_mux …` without starting the web server |

Default URL: `http://127.0.0.1:8765` (`web_port` in config).

Operator phases: **Prepare → Understand → Complete → Create → Ship** — [docs/workflows/operator-journey.md](docs/workflows/operator-journey.md). Tab layout, modals, and checkpoints: [docs/workflows/operator-flow-audit.md](docs/workflows/operator-flow-audit.md). **Clear session** (header menu) clears both browser state and server active run.

New executions get ids like `exec_003_<hash12>_TIMESTAMP` where `<hash12>` fingerprints the canonical pipeline WAV. Runs on the same source audio can **reuse** prior stage outputs — [docs/workflows/stage-execution-reuse.md](docs/workflows/stage-execution-reuse.md). By default each stage pauses for **review before save** (`journey_ui.require_write_approval_per_stage`).

### CLI (headless)

Create or resume a run via GUI first, or allocate with `interview-mux` / tools. Use the actual `run_id` from the workspace header or `ASSETS/executions/` (new ids include a 12-char audio hash segment).

```bash
# Shared analysis (ingest → transcribe → … → optimal_questions)
python tools/run_analysis.py --run-id exec_001_a1b2c3d4e5f6_20260523T120000Z

# After G0/G1/G2 in GUI (or set REMOVED_selected_flow via API/CLI):
python tools/run_delivery.py --flow flow1 --run-id exec_001_a1b2c3d4e5f6_20260523T120000Z
python tools/run_delivery.py --flow flow2 --run-id exec_001_a1b2c3d4e5f6_20260523T120000Z
python tools/run_delivery.py --flow flow3 --run-id exec_001_a1b2c3d4e5f6_20260523T120000Z

# Full pipeline in one shot (needs --flow after analysis):
interview-mux run --run-id exec_001_a1b2c3d4e5f6_20260523T120000Z --flow flow1
interview-mux analysis --run-id exec_001_a1b2c3d4e5f6_20260523T120000Z --analysis-only

# Reuse all reusable stages from a prior run (same source audio hash):
interview-mux analysis --run-id exec_002_… --reuse-from exec_001_…
```

Subcommands: `interview-mux analysis`, `flow`, `serve`, `run` (see `interview-mux --help`).

Flow 3 produces text only. Flow 1/2 produce `master.wav` under `master/` or `REMOVED_flow2/`.

---

## 5. Quality checks (before sign-off)

```bash
python tools/verify_master.py ASSETS/executions/<exec_id>/master/master.wav
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
| Local model stacks | `./scripts/verify_local_models.sh` |
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
