# Anchored toolchain (single source of truth)

**Status:** Authoritative for **all** dependency versions referenced in `docs/`.  
**Scope:** Python runtime, pip packages, system binaries, external HTTP API surfaces, and optional research libraries.  
**Not in scope:** Operator secrets, per-account OpenAI model availability, or removed cloud audio APIs (ElevenLabs removed; SFX is local MMAudio).

**Related:** [model-routing.md](./model-routing.md) (OpenAI model IDs) · [config-keys.md](./config-keys.md) · [smoke-test.md](../workflows/smoke-test.md) · BUILD-010 (`pyproject.toml`, `requirements.txt`, **`requirements.lock`**, `pip-audit` in `check_prerequisites.sh`) · [podcast-rss-hosting.md](./podcast-rss-hosting.md) (Terraform AWS)

---

## Policy

| Rule | Detail |
|------|--------|
| **Anchor lock** | Direct deps live in `requirements.txt` (or `pyproject.toml` `[project.dependencies]`). **Exact** transitive pins live in **`requirements.lock`** at repo root, produced by `pip-compile` (or `uv lock` + `uv sync`). Bootstrap installs **only** from the lock: `pip install -r requirements.lock`. |
| **No drift in prose** | Docs list versions **only** in this file (or link here). Stage READMEs say *which* tool, not *which version*. |
| **Vulnerability gate** | `./tools/check_prerequisites.sh` runs **`pip-audit`** against `requirements.lock` (and fails on known CVEs at or above configured severity). Re-run after any lock refresh. |
| **Context7 for code** | Agents implementing or changing Python that calls third-party APIs/libraries **must** resolve docs via **Context7** using the **exact** package version from `requirements.lock` (see [Context7](#context7-for-implementers)). |
| **AWS** | **Terraform owns infra** (`terraform/` + committed `terraform/state/terraform.tfstate` via `scripts/tf-*.sh`). App publish/seed/invalidate uses **boto3** with credentials from `config/secrets/secrets.env`. **Never** require AWS CLI, `aws login`, or `aws configure` for operators. |
| **Local audio** | SFX via **MMAudio** subprocess (`mmaudio_runner`); preclean via **DeepFilterNet** — no cloud audio REST in pipeline stages. STT is local MLX (`ASSETS/local_speech`), not cloud Transcribe. |

When you change a pinned version, update **`requirements.lock`**, this doc’s `last_verified` date, and any Context7 library queries in the same PR.

---

## Bootstrap (operator / agent)

```bash
./scripts/bootstrap_venv.sh    # creates .venv, installs from requirements.lock
source .venv/bin/activate
./tools/check_prerequisites.sh # ffmpeg, ffprobe, Python, pip-audit, import smoke
```

`scripts/run.sh` must use the same lock install path (no unpinned `pip install -U` of app deps).

### AWS / podcast hosting (optional Ship)

```bash
# Credentials in config/secrets/secrets.env (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY or AWS_PROFILE)
# — no aws login / AWS CLI required
./scripts/tf-init.sh && ./scripts/tf-plan.sh && ./scripts/tf-apply.sh   # updates terraform/state/
python scripts/seed_podcast_origin.py                                  # boto3 PutObject + invalidate
./scripts/invalidate_podcast_cf.sh                                     # boto3 CreateInvalidation
```

See [podcast-rss-hosting.md](./podcast-rss-hosting.md) · [terraform/README.md](../../terraform/README.md).

### Vulnerability audit (setup gate)

Contract for `tools/check_prerequisites.sh` (BUILD-010):

1. Require `pip-audit` in the venv (from `requirements.lock`) and invoke via `python -m pip_audit`.
2. Audit `requirements.lock` (JSON output); resolve severity via OSV for each advisory.
3. **Fail** if any unaccepted finding is **HIGH** or **CRITICAL** (default `PIP_AUDIT_FAIL_LEVEL=HIGH`; use `PIP_AUDIT_IGNORE_VULNS` only with a row in [Accepted advisories](#accepted-advisories)).
4. Print advisory IDs and fix versions; refresh the lock or document an exception before pipeline work.

**Regenerate lock:** `pip-compile requirements.txt -o requirements.lock` (Python 3.12).

Optional CI: same command on every PR that touches `requirements.txt` or `requirements.lock`.

---

## Python runtime

| Component | Anchored version | Notes |
|-----------|------------------|-------|
| **CPython** | **3.12.13** | Create venv with `/opt/homebrew/bin/python3.12` on macOS; minimum **3.12.0** |
| **pip** | **26.1.1** | Bootstrapped in venv only |
| **setuptools** | **82.0.1** | Build backend when using `pyproject.toml` |
| **wheel** | **0.47.0** | |

---

## Python packages (application)

Direct dependencies for `interview_mux`. **Authoritative pins:** `requirements.lock` at repo root. Table below mirrors lock as of **`last_verified: 2026-08-03`** — if lock and table disagree, **lock wins**.

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | 0.136.3 | Web GUI `/api/*` |
| `python-multipart` | 0.0.30 | FastAPI form/file uploads (`UploadFile`, multipart endpoints) |
| `uvicorn[standard]` | 0.47.0 | ASGI server for `serve` |
| `starlette` | 1.3.1 | (transitive) ASGI stack |
| `pydantic` | 2.13.4 | Request/response models |
| `openai` | 2.38.0 | Chat Completions (`llm_runner.py`) + Images (covers) |
| `typer` | 0.25.1 | CLI |
| `rich` | 13.9.4 | CLI output |
| `jsonschema` | 4.26.0 | Artifact validation (`prompt_validation.py`) |
| `filelock` | 3.29.0 | Atomic JSON writes |
| `httpx` | 0.28.1 | (transitive) OpenAI HTTP |
| `numpy` | 2.4.6 | Audio metrics, value-analysis extract, mix helpers (shipped) |
| `pyloudnorm` | 0.2.0 | Mastering-bus LUFS (BUILD-071); QA uses ffmpeg `loudnorm` (BUILD-070) |
| `pydub` | 0.25.1 | Mix engine (`mix`, `REMOVED_mix_flow2` — BUILD-065, shipped) |
| `soundfile` | 0.13.1 | WAV I/O helpers |
| `boto3` | ≥1.35,&lt;2 (lock wins) | Podcast S3 PutObject + CloudFront invalidation (`podcast_rss/s3_publish.py`) |
| `Pillow` | ≥10,&lt;12 (lock wins) | Cover JPEG 3000² upscale / dimension gates |
| `ffmpeg-python` | 0.2.0 | Optional Python-side ffmpeg wrappers (prefer subprocess) |

**Dev / QA only** (not required in production path):

| Package | Version | Purpose |
|---------|---------|---------|
| `pytest` | 8.4.2 | Unit tests |
| `pip-audit` | 2.10.0 | CVE gate at setup |

**Explicitly excluded from application env:**

| Package | Reason |
|---------|--------|
| `elevenlabs` (SDK) | Removed — was ElevenLabs REST; use local MMAudio |
| AWS CLI as a required tool | Infra via Terraform; app AWS via boto3 + `secrets.env` |

---

## System binaries

Pin **minimum** versions; operators may run newer patch releases if `check_prerequisites.sh` passes feature probes.

| Binary | Anchored minimum | Verified example | Used by |
|--------|------------------|------------------|---------|
| **ffmpeg** | **8.0** | 8.1.1 | ingest, assembly, transcript clips, MMAudio resample, podcast MP3 |
| **ffprobe** | **8.0** (ships with ffmpeg) | 8.1.1 | `verify_master.py`, probing |
| **terraform** | **~> 1.14.7** | 1.14.7 | Podcast RSS stack (`scripts/tf-*.sh`) — optional until you publish |

Install on macOS (example): `brew install ffmpeg` — then confirm versions against this table. Terraform: use `tfenv` / vendor install matching `terraform/versions.tf`. **Do not** install AWS CLI for this repo’s pipeline or publish path.

---

## External HTTP APIs (version surfaces)

| Service | Anchored surface | Client in repo |
|---------|------------------|----------------|
| **OpenAI** | Chat Completions + Images; model IDs in [model-routing.md](./model-routing.md#model-tier-registry) | `openai` SDK → `llm_runner.py` / `podcast_rss/openai_cover.py` |
| **AWS S3 / CloudFront** | PutObject + CreateInvalidation for podcast origin | `boto3` → `podcast_rss/s3_publish.py` (creds from `secrets.env`) |

Local MMAudio and DeepFilterNet run as subprocesses in isolated venvs — see [local-audio-stack.md](./local-audio-stack.md). No ElevenLabs HTTP surface. No Amazon Transcribe.

**Local speech venv** (`ASSETS/local_speech/venv`, [`requirements-local-speech.txt`](../../requirements-local-speech.txt)): **mlx-audio 0.4.8** (STT + Sortformer `mlx_audio.vad` identity classify). Verify: `python scripts/download_local_speech.py --verify-stt` and `--verify-diarization`. Identity is Sortformer, not Qwen S2S.

---

## Optional research / spike libraries (not in default lock)

When a spike adds a library, add a row here **and** a dedicated optional extra in `requirements.lock` (or `requirements-spike.lock`). Use Context7 with that exact version before writing integration code.

| Library | Suggested pin (spike) | Lever (see [tools-not-in-repo-landscape.md](../pipeline/value-analysis/tools-not-in-repo-landscape.md)) |
|---------|----------------------|--------------------------------------------------------------------------------------------------------|
| `faster-whisper` | `1.1.1` in [`requirements-spike.lock`](../../requirements-spike.lock) | STT catalog (spike only) |
| `mlx-lm` / `mlx` | pinned in `requirements-spike.lock` (Darwin) | Local LLM volley framing |
| `huggingface_hub` | `0.26.5` in `requirements-spike.lock` | Model download scripts |
| `whisperx` | pin at spike time | Alignment |
| `demucs` | pin at spike time | Stem features |
| `opensmile` / `speechbrain` | pin at spike time | Prosody |

---

## Context7 for implementers

When generating or editing **Python** (or shell that calls library CLIs), use the **Context7** MCP server — not training-data memory — for API shapes, parameters, and breaking changes.

**Workflow:**

1. Read the package version from **`requirements.lock`** (column `Version`).
2. Call Context7 **`resolve-library-id`** with `libraryName` + that version (e.g. `fastapi`, `0.136.3`).
3. Call **`query-docs`** (MCP server `user-context7` / `context7`) with `libraryId` from step 2 and a focused `query` (e.g. `FileResponse static files`, `Chat Completions structured output`).
4. Implement against retrieved docs; cite behavior in PR description, not stale blog posts.

**Required Context7 lookups before touching:**

| Area | Library | Lock version |
|------|---------|--------------|
| Web API | `fastapi` | 0.136.3 |
| Server | `uvicorn` | 0.47.0 |
| LLM / Images | `openai` | 2.38.0 |
| Validation | `jsonschema` | 4.26.0 |
| CLI | `typer` | 0.25.1 |
| Podcast AWS SDK | `boto3` | from `requirements.lock` |

For **ffmpeg**, use Context7 or vendor CLI reference for the **anchored major** in [System binaries](#system-binaries). For **Terraform / AWS provider**, use HashiCorp + AWS provider docs for the versions in `terraform/versions.tf` — not AWS CLI.

---

## Accepted advisories

| Advisory ID | Package | Accepted until | Mitigation |
|-------------|---------|----------------|------------|
| *(none)* | — | — | — |

Rows here are the **only** exception to the vulnerability gate. Remove rows when lock is upgraded.

---

## Doc authoring rule

Any `docs/**/*.md` file that names a third-party product for **implementation** must:

1. Link to this file for versions: `[anchored-toolchain.md](./anchored-toolchain.md)` (adjust relative path), and  
2. Avoid embedding floating ranges (`pip install foo>=1`) in prose — point to lock refresh process instead.
3. For AWS hosting, link [podcast-rss-hosting.md](./podcast-rss-hosting.md) and describe **Terraform + state**, never AWS CLI as the operator path.

Hub pages: [INDEX.md](../INDEX.md), [README.md](../README.md), [prompts/README.md](../prompts/README.md).
