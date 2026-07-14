# Local LLM tier — implementation handoff

**Status: shipped** — on-device MLX volley framing before OpenAI; fail-safe escalation to cloud primary.

**Framework docs:** [local-llm-tier.md](./local-llm-tier.md) · [context-padding.md](./context-padding.md) · [llm-orchestration.md](./llm-orchestration.md) · [config-keys.md](./config-keys.md#local_llm)

---

## Module map (shipped)

| Spec concept | Module | Notes |
|--------------|--------|-------|
| Download / verify weights | `scripts/download_local_llm.py`, `scripts/select_local_llm.py` | Weights under `ASSETS/local_llm/models/` |
| Stage-1 calibrate | `scripts/calibrate_local_llm.py` | Writes `capability_manifest.json` |
| Capability router | `src/interview_mux/local_capability_router.py` | Allowlist + fail-fast LX-01/03/04/05 |
| Manifest I/O | `src/interview_mux/local_capability_manifest.py` | Load/validate/degraded |
| `load_local_model()` cache | `src/interview_mux/local_llm_runner.py` | Singleton `load()` per process |
| `prepare_volley_for_llm(...)` | `src/interview_mux/local_volley_framer.py` | Builds local messages; parses JSON contract |
| Inject framed turns | `src/interview_mux/context_volley.py` | `local_framing` optional param |
| Escalation before OpenAI | `src/interview_mux/llm_stage_routing.py` | Router then OpenAI primary |
| Config | `config/app.defaults.json` `local_llm.*` / `capability.*` | Documented in config-keys.md |
| Prompts | `docs/prompts/_shared/local-*.system.txt` | Framer, compressor, advisory, shard-prep, planner |

---

## Local framer JSON contract (assistant output)

```json
{
  "escalate": true,
  "confidence": 0.85,
  "reason": "one sentence",
  "volley_turns": [
    {"role": "assistant", "content": "Prior conclusions in prose..."},
    {"role": "user", "content": "## Profile slice\n..."}
  ]
}
```

| Field | Rule |
|-------|------|
| `escalate` | If `true`, run OpenAI primary with `volley_turns` merged into `build_message_volley` output |
| `confidence` | If &lt; 0.6, force `escalate: true` in code |
| `volley_turns` | Max length `local_llm.max_volley_turns` (default 2); roles only `user` \| `assistant` |
| `reason` | Audit only; not sent to OpenAI |

Invalid JSON → treat as `escalate: true`, log warning.

---

## Implementation checklist

### Phase A — toolchain

- [x] `mlx-lm`, `mlx`, `huggingface_hub` in `requirements.txt` (darwin); lock in `requirements.lock`
- [x] [anchored-toolchain.md](./anchored-toolchain.md) table
- [x] `local_llm` keys in [config-keys.md](./config-keys.md)
- [x] `./tools/check_prerequisites.sh` warns when `mlx_lm` or weights missing on macOS

### Phase B — download + paths

- [x] `scripts/download_local_llm.py` with `ASSETS/local_llm/models/` + `hf_cache/`
- [x] `local_llm_config.resolve_model_path()` — env &gt; selection manifest &gt; config &gt; default HF id

### Phase C — framer

- [x] `local_volley_framer.prepare_volley_for_llm` → `LocalFramingResult`
- [x] Unit tests: `tests/test_local_volley_framer.py`
- [x] Prompt loader via `load_system_prompt` pattern

### Phase D — pipeline integration

- [x] `build_message_volley(..., local_framing=...)` — merge framed turns
- [x] `llm_stage_routing.run_llm_stage_with_routing`: framer when `local_llm.enabled`
- [x] `skip_openai_primary_when_local_satisfied` (default `false` — OpenAI primary still runs unless promoted)
- [x] Attempt JSON `local_llm` meta in routing debug / GUI

### Phase E — docs

- [x] [repository-map.md](../build-out/repository-map.md) modules listed
- [x] [SETUP.md](../../SETUP.md) Local LLM section
- [x] Troubleshooting: OOM → smaller model; missing weights → `select_local_llm.py --download`

---

### Phase F — quality capability ladder

- [x] `QUALITY_LOCAL_ALLOWLIST` + `transitions` in `ALWAYS_ESCALATE_STAGES`
- [x] `local_llm.capability.*` config + calibrate script + bootstrap hook
- [x] Router fail-fast (`retries=0`); LX-03..05 + economy planner OM-LX-P
- [x] LX-03 reserved `episode_structure` section; `extra_digest_paths` hook
- [x] Tests: `test_local_capability_router.py`, `test_calibrate_local_llm.py`

**Handoff → Episode Structure Catalog:** router stable; inject compact structure via `extra_digest_paths` / LX-03 section only on allowlisted stages.

## Verify

```bash
source .venv/bin/activate
python scripts/select_local_llm.py --download
python scripts/download_local_llm.py --verify
python scripts/calibrate_local_llm.py --dry-run
pytest tests/test_local_volley_framer.py tests/test_local_capability_router.py tests/test_calibrate_local_llm.py
```
