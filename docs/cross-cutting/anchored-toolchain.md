# Anchored toolchain (single source of truth)

**Status:** Authoritative for **all** dependency versions referenced in `docs/`.  
**Scope:** Python runtime, pip packages, system binaries, external HTTP API surfaces, and optional research libraries.  
**Not in scope:** Operator secrets, per-account OpenAI model availability, or ElevenLabs account tier limits.

**Related:** [model-routing.md](./model-routing.md) (OpenAI model IDs) · [config-keys.md](./config-keys.md) · [smoke-test.md](../workflows/smoke-test.md) · BUILD-010 (`pyproject.toml`, `requirements.txt` at repo root; **`requirements.lock` + `pip-audit` gate partial**)

---

## Policy

| Rule | Detail |
|------|--------|
| **Anchor lock** | Direct deps live in `requirements.txt` (or `pyproject.toml` `[project.dependencies]`). **Exact** transitive pins live in **`requirements.lock`** at repo root, produced by `pip-compile` (or `uv lock` + `uv sync`). Bootstrap installs **only** from the lock: `pip install -r requirements.lock`. |
| **No drift in prose** | Docs list versions **only** in this file (or link here). Stage READMEs say *which* tool, not *which version*. |
| **Vulnerability gate** | `./tools/check_prerequisites.sh` runs **`pip-audit`** against `requirements.lock` (and fails on known CVEs at or above configured severity). Re-run after any lock refresh. |
| **Context7 for code** | Agents implementing or changing Python that calls third-party APIs/libraries **must** resolve docs via **Context7** using the **exact** package version from `requirements.lock` (see [Context7](#context7-for-implementers)). |
| **AWS** | Application code uses **`aws` CLI subprocess only** — no boto3. Pin CLI major in docs; operators verify with `aws --version`. |
| **ElevenLabs** | Application code uses **REST** (`urllib`) — no ElevenLabs Python SDK in pipeline stages. Pin **API base path** `/v1` here. |

When you change a pinned version, update **`requirements.lock`**, this doc’s `last_verified` date, and any Context7 library queries in the same PR.

---

## Bootstrap (operator / agent)

```bash
./scripts/bootstrap_venv.sh    # creates .venv, installs from requirements.lock
source .venv/bin/activate
./tools/check_prerequisites.sh # ffmpeg, ffprobe, aws, Python, pip-audit, import smoke
```

`scripts/run.sh` must use the same lock install path (no unpinned `pip install -U` of app deps).

### Vulnerability audit (setup gate)

Documented contract for `tools/check_prerequisites.sh` (implementation tracked under BUILD-010):

1. Require `pip-audit` in the venv (dev dependency) or invoke via `python -m pip_audit`.
2. Run: `pip-audit -r requirements.lock --strict` (or equivalent OSV feed).
3. **Fail** if any finding is **HIGH** or **CRITICAL** (configurable `PIP_AUDIT_FAIL_LEVEL`).
4. Print advisory IDs and fixed versions; do not proceed to pipeline work until lock is refreshed or finding is accepted in writing in this doc’s [Accepted advisories](#accepted-advisories) table.

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

Direct dependencies for `interview_mux`. **Authoritative pins:** `requirements.lock` at repo root. Table below mirrors lock as of **`last_verified: 2026-05-27`** — if lock and table disagree, **lock wins**.

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | 0.136.3 | Web GUI `/api/*` |
| `uvicorn[standard]` | 0.47.0 | ASGI server for `serve` |
| `starlette` | 1.1.0 | (transitive) ASGI stack |
| `pydantic` | 2.13.4 | Request/response models |
| `openai` | 2.38.0 | Chat Completions (`llm_runner.py`) |
| `typer` | 0.25.1 | CLI |
| `rich` | 13.9.4 | CLI output |
| `jsonschema` | 4.26.0 | Artifact validation (`prompt_validation.py`) |
| `filelock` | 3.29.0 | Atomic JSON writes |
| `httpx` | 0.28.1 | (transitive) OpenAI HTTP |
| `numpy` | 2.4.6 | Audio metrics (planned / optional stages) |
| `pyloudnorm` | 0.2.0 | LUFS measurement (BUILD-070+) |
| `pydub` | 0.25.1 | Mix engine (BUILD-065, planned) |
| `soundfile` | 0.13.1 | WAV I/O helpers |
| `ffmpeg-python` | 0.2.0 | Optional Python-side ffmpeg wrappers (prefer subprocess) |

**Dev / QA only** (not required in production path):

| Package | Version | Purpose |
|---------|---------|---------|
| `pytest` | 8.4.2 | Unit tests |
| `pip-audit` | *(pin in lock)* | CVE gate at setup |

**Explicitly excluded from application env:**

| Package | Reason |
|---------|--------|
| `boto3`, `botocore` | AWS via CLI only |
| `elevenlabs` (SDK) | ElevenLabs via REST (`elevenlabs_rest.py`) |

---

## System binaries

Pin **minimum** versions; operators may run newer patch releases if `check_prerequisites.sh` passes feature probes.

| Binary | Anchored minimum | Verified example | Used by |
|--------|------------------|------------------|---------|
| **ffmpeg** | **8.0** | 8.1.1 | ingest, assembly, transcript clips, ElevenLabs normalize |
| **ffprobe** | **8.0** (ships with ffmpeg) | 8.1.1 | `verify_master.py`, probing |
| **aws** CLI | **2.30** | 2.34.18 | Transcribe, S3 upload/download |

Install on macOS (example): `brew install ffmpeg awscli` — then confirm versions against this table.

---

## External HTTP APIs (version surfaces)

| Service | Anchored surface | Client in repo |
|---------|------------------|----------------|
| **OpenAI** | Chat Completions; model IDs in [model-routing.md](./model-routing.md#model-tier-registry) | `openai` SDK → `llm_runner.py` |
| **ElevenLabs** | `https://api.elevenlabs.io/v1` — `POST /sound-generation`, `POST /audio-isolation` | `elevenlabs_rest.py` |
| **AWS Transcribe** | Batch jobs via `aws transcribe` CLI; S3 via `aws s3` | `transcribe_aws.py` |

Do not bump ElevenLabs path to `/v2` without updating `ELEVENLABS_API_BASE` and [elevenlabs-integration-guide.md](./elevenlabs-integration-guide.md) in the same change.

---

## Optional research / spike libraries (not in default lock)

When a spike adds a library, add a row here **and** a dedicated optional extra in `requirements.lock` (or `requirements-spike.lock`). Use Context7 with that exact version before writing integration code.

| Library | Suggested pin (spike) | Lever (see [tools-not-in-repo-landscape.md](../pipeline/value-analysis/tools-not-in-repo-landscape.md)) |
|---------|----------------------|--------------------------------------------------------------------------------------------------------|
| `faster-whisper` | pin at spike time | STT catalog |
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
| LLM | `openai` | 2.38.0 |
| Validation | `jsonschema` | 4.26.0 |
| CLI | `typer` | 0.25.1 |

For **ffmpeg** and **aws** CLI, use Context7 or vendor CLI reference for the **anchored major** in [System binaries](#system-binaries).

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

Hub pages: [INDEX.md](../INDEX.md), [README.md](../README.md), [prompts/README.md](../prompts/README.md).
