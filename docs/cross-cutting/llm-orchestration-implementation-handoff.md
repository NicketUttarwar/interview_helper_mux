# LLM orchestration — implementation handoff

**Status: implementation map (BUILD-073 shipped)** — keep in sync when changing routing behavior.

**Before coding:** [anchored-toolchain.md](./anchored-toolchain.md) (`openai` pin, lock, `pip-audit`) + **Context7** for SDK/API docs at that version.

**Framework docs:**

- [llm-orchestration.md](./llm-orchestration.md)
- [llm-stage-model-matrix.md](./llm-stage-model-matrix.md)
- [model-routing.md](./model-routing.md)
- [prompts/_shared/llm-arbiter-contract.md](../prompts/_shared/llm-arbiter-contract.md)

---

## Module map (proposed)

| Spec concept | Suggested module | Notes |
|--------------|------------------|-------|
| `resolve_model(stage_key, task_kind)` | `src/interview_mux/model_registry.py` | Load matrix + `models.tiers`; backward compat flat strings |
| `run_llm_arbiter(...)` | `src/interview_mux/llm_arbiter.py` | Economy tier; load `docs/prompts/_shared/arbiter.system.txt` |
| Shard / collate loop | `src/interview_mux/llm_subtasks.py` | Driven by arbiter `shard_plan` |
| Volley profiles `full` \| `shard` \| `collate` | extend `src/interview_mux/context_volley.py` | `STAGE_PLANS` + profile param |
| Primary + arbiter integration | `src/interview_mux/stages/analysis_stage.py`, `run_flow_llm_stage` | Arbiter after schema validate, before `apply_envelope_to_memory` |
| OpenAI HTTP call | `src/interview_mux/stages/llm_runner.py` | Pass `task_kind`, log tier/id, optional `response_format` for arbiter |
| Config merge | `src/interview_mux/config.py` | `get_model()` delegates to registry |
| Attempt audit | `src/interview_mux/analysis_memory.py` | `record_stage_attempt` adds `model_tier`, `arbiter_result`, etc. |
| Queue drain | `src/interview_mux/analysis_orchestrator.py` | Prefer investigation when not a shard-size issue |

---

## Implementation checklist

### Phase A — registry

- [x] Add `models.tiers` and `models.stages` to `config/app.defaults.json` (migrate from flat strings)
- [x] Implement `model_registry.resolve_model(stage_key, task_kind)`
- [x] Unit tests: tier rules for arbiter/shard/collate; string override wins

### Phase B — arbiter

- [x] Load arbiter system prompt from repo path (same as other prompts)
- [x] Build compact arbiter user payload (no full transcript)
- [x] Parse verdict JSON per contract; handle invalid arbiter JSON as `enqueue_investigation`
- [x] Wire into `run_analysis_llm_stage` and `run_flow_llm_stage`
- [ ] Skip arbiter on pre-arbiter failures (JSON parse still raises before arbiter today)
- [x] Cap: 1 arbiter per primary attempt; 2 uptier retries per stage per run

### Phase C — decompose

- [x] `llm_subtasks.run_shards_then_collate` for pilot stages: `missing_framing`, `segment_classification`
- [x] Volley profiles in `build_message_volley(..., profile=...)`
- [x] Collate tier rule for high severity
- [x] Max 8 shards; fallback to investigation if not decompose_eligible

### Phase D — observability

- [x] Extend `attempt_NNN.json` fields per [llm-orchestration.md](./llm-orchestration.md#observability-target-attempt-json-fields)
- [x] GUI: display arbiter verdict in stage debug (`StageDetail` LLM routing panel + `LlmCallsPanel` arbiter summary)
- [ ] Smoke: short interview + long interview fixtures

### Phase E — config migration

- [ ] Align `config/templates/app.defaults.json` with tier targets
- [ ] Document flagship IDs in registry only
- [ ] Optional secrets `OPENAI_TIER_*`

---

## API surface decisions (deferred)

| Topic | Recommendation in docs |
|-------|------------------------|
| Chat Completions vs Responses API | Stay on Chat Completions unless arbiter A/B shows clear win |
| `response_format: json_object` | Optional for arbiter + envelope stages in `llm_runner` |
| Temperature | Keep 0.2 for primary; arbiter may use 0.0 |

---

## Test scenarios

1. **Accept path** — primary complete, arbiter accept, memory merged once.
2. **retry_uptier** — economy primary weak, arbiter requests standard re-run, then accept.
3. **decompose** — long manifest, shards + collate, single merged artifact file.
4. **enqueue_investigation** — arbiter rejects merge; queue item created; no memory pollution.
5. **Schema retry** — existing volley feedback still runs before arbiter.

---

## Non-goals (this implementation track)

- Changing AWS Transcribe, ElevenLabs REST, or STT paths
- boto3
- Automatic Responses API migration
- Editing prompts to embed model names
