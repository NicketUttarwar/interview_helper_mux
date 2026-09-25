# Artifact generation and validation

**Status: shipped** — flagship OpenAI generation for all structured LLM artifacts, JSON Schema validation on every disk write, and Zod validation in the GUI before save. **Incremental gap-fill is partially absent:** gap *detection* and merge-on-persist are live, but nothing injects `gap_fill_context` into the model's packet — see [gap-fill-capability-gap.md](./gap-fill-capability-gap.md).

**Related:**

- [model-routing.md](./model-routing.md) — tier registry (`flagship` = `gpt-5.6-terra` by default)
- [llm-call-record-framework.md](./llm-call-record-framework.md) — call → schema → persist gating and audit records
- [json-schema-coverage.md](./json-schema-coverage.md) — which paths have validators
- [analysis-memory.md](./analysis-memory.md) — profile merge and operator verification
- [artifact-layout.md](./artifact-layout.md) — on-disk paths per stage
- [gui-surface-map.md](../workflows/gui-surface-map.md) — Stage outputs UI
- [api-reference.md](../workflows/api-reference.md) — `artifacts_status`, `fill-artifact-gaps`
- [gap-fill-capability-gap.md](./gap-fill-capability-gap.md) — **gap-fill context injection absent since 2026-07-20**

---

## Goals

1. **Every descriptive JSON artifact** under a run workspace is produced by an **OpenAI flagship** primary call (not economy/standard tiers, not local-only pilot).
2. **Incremental fill** *(design goal — the injection half is currently absent)* — when a file already exists but is incomplete, the model should receive `gap_fill_context` and return **patches only** for missing fields, with satisfied keys listed in `skip_fields`. **Not in force since 2026-07-20:** the v2 reset (`f99f228b`) rewrote `stages/analysis_stage.py` and dropped the injection call; nothing has produced the block since. Detection (`compute_gaps`) and merge (`merge_artifact`) still work, so a re-running stage regenerates blind and the merge layer absorbs a full rewrite. Full record: [gap-fill-capability-gap.md](./gap-fill-capability-gap.md).
3. **Validate before write** — no artifact is persisted unless it passes the on-disk JSON Schema registered in `ARTIFACT_WRITE_VALIDATORS`.
4. **Operator review** — GUI shows `pending` / `partial` / `complete` per artifact; Open / edit / save with client-side Zod + server-side jsonschema.
5. **Auto-commit** — stage outputs are written straight to their final paths (`v2.auto_commit_artifacts: true`). Inter-stage handoff acks and per-stage write approval were removed ([operator-gates.md](../workflows/operator-gates.md)).

**Out of scope:** binary audio (`*.wav`), raw local STT export shape, deterministic numeric fields in `source_acoustic_profile.json` (WPM, pause stats from audio analysis).

---

## Architecture

```mermaid
flowchart TD
  subgraph input [Stage input]
    Disk[Read existing artifact]
    Gaps[compute_gaps + validate_artifact_write]
    Disk --> Gaps
    Gaps -.-> Ctx["gap_fill_context in stage JSON — ABSENT since 2026-07-20"]
    Ctx -.-> Volley[stage_input_helpers]
  end
  subgraph openai [OpenAI]
    Volley --> Primary["primary task_kind — tier flagship"]
    Primary --> Env[analysis envelope]
  end
  subgraph persist [Persist path]
    Env --> StageVal[validate_stage_artifacts]
    StageVal --> Arb[llm_arbiter economy]
    Arb --> Merge[merge_artifact optional]
    Merge --> DiskVal[validate_artifact_write]
    DiskVal --> Write[write_validated_artifact / write_json]
  end
  subgraph gui [GUI]
    Write --> Status[artifacts_status on GET run]
    Status --> Panel[Stage outputs pending partial complete]
    Panel --> Editor[ArtifactEditor Zod safeParse]
    Editor --> Put[PUT artifact — server validates again]
  end
```

**Dotted edges = designed but not currently wired.** The `Ctx` node is kept as the design record; no
code has produced `gap_fill_context` since 2026-07-20 ([gap-fill-capability-gap.md](./gap-fill-capability-gap.md)).
Everything on the solid path — `compute_gaps`, `validate_artifact_write`, the persist chain and the GUI
surface — is live.

---

## Code modules

| Module | Path | Role |
|--------|------|------|
| Gap-fill + merge + completeness | `src/interview_mux/artifact_completeness.py` | `compute_gaps`, `merge_artifact`, `artifact_status`, `should_run_stage_for_artifact`, `make_stage_persist`; plus `build_gap_fill_context` — **intact but zero callers** |
| Validated write | `src/interview_mux/artifact_writes.py` | `write_validated_artifact` — merge, validate, log, `RunContext.write_json` |
| Schema registry | `src/interview_mux/prompt_validation.py` | `STAGE_ARTIFACT_SCHEMAS`, `STAGE_ARTIFACT_DISK_PATHS`, `ARTIFACT_WRITE_VALIDATORS`, `validate_artifact_write` |
| Stage runner | `src/interview_mux/stages/analysis_stage.py` | **`attach_gap_fill_to_input` no longer exists.** The *call* was dropped by the v2 reset `f99f228b` (2026-07-20); the then-orphaned *definition* was later deleted. Nothing injects `gap_fill_context` into stage input today — [gap-fill-capability-gap.md](./gap-fill-capability-gap.md) |
| Call path | `src/interview_mux/llm_simple.py` | Single OpenAI call per attempt, max 2 attempts |
| Pipeline | `src/interview_mux/pipeline.py` | Re-run LLM stage if `should_run_stage_for_artifact` even when `.stage_done` exists |
| GUI API | `src/interview_mux/web/server.py` | `artifacts_status`, `POST …/fill-artifact-gaps` |
| Zod codegen | `tools/codegen_zod_schemas.py` | Emits `frontend/src/schemas/generated/*.ts` |
| GUI validate | `frontend/src/schemas/validateArtifact.ts` | Mirrors `ARTIFACT_WRITE_VALIDATORS` paths |

---

## Stage → disk path map

Canonical map: `STAGE_ARTIFACT_DISK_PATHS` in `prompt_validation.py`.

| Stage key | On-disk path |
|-----------|----------------|
| `speaker_roles` | `understanding/speakers.json` |
| `content_context` | `understanding/content_brief.json` |
| `boundary_detection` | `segments/boundaries.json` |
| `segment_classification` | `segments/manifest.json` |
| `content_brief_reanchor` | `understanding/content_brief.json` (patch merge) |
| `sound_design_palettes` | `understanding/sound_design_plan.json` |
| `missing_framing` | `understanding/gap_evaluations.json` |
| `optimal_questions` | `understanding/gap_report.json` |
| `topic_coverage_audit` | `master/coverage_audit.json` |
| `narrative_arc_plan` | `master/narrative_plan.json` |
| `full_master_ranking` | `master/selection.json` |
| `transitions` | `master/transitions.json` |
| `podcast_sfx_brief` | `master/podcast_sfx_brief.json` |
| `sound_design_plan` / `flow2` | `understanding/sound_design_plan.json` |
| `sfx_prompt_craft` | `sound_design/sfx_prompts.json` |
| `sfx_brief` | `REMOVED_flow2/sfx_brief.json` |
| `REMOVED_podcast_show_description` | `show_notes/show_description.json` |
| `edl_narrative_audit` | `master/edl_narrative_audit.json` |
| `REMOVED_highlight_selection` | `REMOVED_flow2/selection.json` |

`analysis_state.json` is updated via `memory_updates` on the envelope (not a direct stage artifact file), but is validated on every `write_json` and included in completeness rules for themes/thesis.

---

## Gap-fill contract

### Input: `gap_fill_context`

> **ABSENT since 2026-07-20 — no live code path produces this block.** The v2 reset `f99f228b`
> rewrote `stages/analysis_stage.py` (+14/−572) and dropped the `attach_gap_fill_to_input()` call;
> the function then sat orphaned for two months before guardrail subtraction deleted the definition
> (guardrail subtraction). **The subtraction campaign did not cause this
> gap.** Its builder `artifact_completeness.build_gap_fill_context` still exists intact but has no
> callers, and no caller passes `gap_fill_context` to `build_required_response_block()` /
> `volley_format_footer()`. **No replacement route exists in the source** — stage inputs currently
> carry no gap-fill block. The shape below is kept as the record of the contract, not as current
> behaviour. Gap *detection* (`compute_gaps`, `artifact_status`, `should_run_stage_for_artifact`) and
> the re-run rule below are unaffected. Timeline, affected prompts and a suggested (unvalidated) fix:
> [gap-fill-capability-gap.md](./gap-fill-capability-gap.md).

Formerly injected by `attach_gap_fill_to_input()` into the final user turn JSON for each LLM stage:

```json
{
  "gap_fill_context": {
    "artifact_path": "understanding/content_brief.json",
    "existing": { "... prior on-disk object or null ..." },
    "gaps": ["thesis", "topics[0].summary"],
    "skip_fields": ["audience"],
    "instructions": "Only fill listed gaps. Do not overwrite skip_fields..."
  }
}
```

Documented in [analysis-preamble.system.txt](../prompts/_shared/analysis-preamble.system.txt). Per-stage prompts should repeat the one-line rule when they write structured `artifacts`. **Six live prompt files still carry that rule** and therefore instruct the model about a block it never receives; they are enumerated in [gap-fill-capability-gap.md](./gap-fill-capability-gap.md) §3.1 and are deliberately left unedited pending a decision on restoring the injection.

### Semantic completeness rules

`ARTIFACT_COMPLETENESS_RULES` in `artifact_completeness.py` — examples:

| Path | Incomplete when |
|------|-----------------|
| `understanding/content_brief.json` | empty `thesis`, no `topics`, or topic missing `summary` |
| `understanding/analysis_state.json` | no `themes`, empty `narrative.thesis`, empty `interview_identity.one_line_summary` |
| `understanding/speakers.json` | no speakers or missing `role` |
| `understanding/sound_design_plan.json` | empty `coherence.sonic_identity` or no `palettes` |
| `segments/manifest.json` | no `segments` array |

Schema validation failures also mark an artifact **partial** and trigger re-run.

### Merge behavior

`merge_artifact(rel_path, existing, patch)`:

- Default: deep merge; lists like `themes` use analysis-memory append semantics where applicable.
- `segments/manifest.json`: merge by `segment_id`.
- `understanding/sound_design_plan.json`: deep merge for palettes/coherence/assets/flow_plans.
- When `meta.operator_verified: true` on `analysis_state.json`, protected keys (`themes`, `major_questions`, `narrative`, `style`) are not overwritten by LLM patches.

Stage persist helpers use `make_stage_persist(path, stage_key)` → `write_validated_artifact(..., merge_from_disk=True)`.

---

## Validation layers

| Layer | When | Mechanism |
|-------|------|-----------|
| **Envelope** | After primary parse, before arbiter | `validate_envelope` → `analysis_envelope.schema.json` |
| **Stage artifacts** | Before persist decision | `validate_stage_artifacts(stage_key, artifacts)` → `artifacts/*.schema.json` |
| **On-disk write** | Every `RunContext.write_json` dict + GUI PUT | `validate_artifact_write(rel_path, data)` → `ARTIFACT_WRITE_VALIDATORS` |
| **GUI pre-save** | Artifact editor / profile save | Zod `safeParse` via `frontend/src/schemas/validateArtifact.ts` |

If `validate_artifact_write` fails, `write_json` raises `ValueError` and `write_validated_artifact` logs to `gui_log.jsonl` with `level=error`.

**Arbiter:** Still **economy** tier. Persist only when `should_persist_artifacts` is true (accept or successful collate, no schema errors).

---

## OpenAI flagship routing

- **Config:** `config/app.defaults.json` → `models.stages.<stage_key>.tier: "flagship"` for every stage in `STAGE_ARTIFACT_SCHEMAS`.
- **Registry:** [model-routing.md](./model-routing.md) — default API ID `gpt-5.6-terra` for tier `flagship`; override via `OPENAI_TIER_FLAGSHIP` in secrets.
- **Local LLM:** The local MLX framer may pre-compress the volley (fail-open), but stages that write structured artifacts **always** call OpenAI via `llm_simple.py`.

---

## Pipeline re-run when incomplete

In `run_analysis()` and `_run_steps()` (flow1/2/3):

If `.stage_done/<stage>` exists **and** `should_run_stage_for_artifact(ctx, stage_key)` is true, the stage runs again and logs:

`Re-running <stage>: artifact incomplete or invalid`

Triggers: missing file, schema errors, or semantic gaps from `compute_gaps`.

---

## GUI operator workflow

### Stage outputs checklist

From `GET /api/runs/{id}` → each stage has:

| Field | Values |
|-------|--------|
| `artifacts_present` | Paths that exist on disk (legacy; subset of status) |
| `artifacts_status` | Per path: `pending` \| `partial` \| `complete` |

| UI | Meaning |
|----|---------|
| ○ pending | File missing |
| ◐ partial | File exists but schema or semantic gaps remain — **Open**, **Copy**, **Fill gaps** |
| ✓ complete | Passes schema + completeness rules |

### Fill gaps

`POST /api/runs/{run_id}/fill-artifact-gaps` (`web/server.py:2964`) body `{ "path": "understanding/content_brief.json" }` starts a background job (`mode: stage`) for the first stage in `stage_keys_for_artifact_path(path)`.

**Caveat — the route is live, the name overstates it.** It re-runs the stage; it does not tell the model which fields are already satisfied, because no `gap_fill_context` is injected. The model regenerates the whole artifact and `merge_artifact` absorbs the result. See [gap-fill-capability-gap.md](./gap-fill-capability-gap.md).

### Edit and save

1. **Open** → Files tab / `ArtifactEditor`.
2. Edit JSON; **Save** runs Zod validation client-side.
3. `PUT /api/runs/{id}/artifact` runs `validate_artifact_write` server-side.
4. Optional `invalidate_from` clears downstream `.stage_done` markers.

**Profile tab:** `PUT /api/runs/{id}/analysis-profile` validates `understanding/analysis_state.json` on write.

---

## Zod codegen (frontend)

JSON Schema remains **source of truth** under `docs/cross-cutting/json-schemas/`.

```bash
python tools/codegen_zod_schemas.py
# or
cd frontend && npm run codegen:schemas
```

Outputs:

- `frontend/src/schemas/generated/<path>Schema.ts` — one per registered artifact path
- `frontend/src/schemas/generated/index.ts` — `loadArtifactWriteSchema` lazy registry

After changing any `*.schema.json`, regenerate and rebuild the GUI:

```bash
cd frontend && npm run build
```

---

## Adding a new LLM artifact

1. Add or extend `docs/cross-cutting/json-schemas/artifacts/<name>.schema.json`.
2. Register `STAGE_ARTIFACT_SCHEMAS[stage_key]`.
3. Register `STAGE_ARTIFACT_DISK_PATHS[stage_key]`.
4. Add validator to `ARTIFACT_WRITE_VALIDATORS` (thin wrapper around `_validate_by_artifact_schema` or dedicated function).
5. Add `ARTIFACT_COMPLETENESS_RULES[rel_path]` if semantic gaps matter beyond JSON Schema.
6. Use `make_stage_persist` or `write_validated_artifact` in the stage `persist` callback.
7. Add example under `docs/prompts/_shared/examples/` if non-trivial. *(The stage-prompt gap-fill one-liner is dormant — no `gap_fill_context` is injected today; do not add new ones until the injection is restored: [gap-fill-capability-gap.md](./gap-fill-capability-gap.md).)*
8. Run `python tools/codegen_zod_schemas.py` and extend [json-schema-coverage.md](./json-schema-coverage.md).
9. Update [stage-contracts/00-INDEX.md](./stage-contracts/00-INDEX.md) and [gui-surface-map.md](../workflows/gui-surface-map.md).

---

## Verification

```bash
pytest tests/test_artifact_completeness.py tests/test_prompt_validation.py -q
python tools/codegen_zod_schemas.py
cd frontend && npm run build
```

On a run with transcript ready:

```bash
python tools/run_analysis.py --run-id <exec_id> --from-stage content_context
```

Confirm `understanding/content_brief.json` shows **complete** after `content_context` (thesis + topics). After full analysis, confirm **complete** again post-`content_brief_reanchor` (`topics[].segment_ids`, `topic_relationships`). Themes and hypotheses sync into `analysis_state.json` via stage `memory_updates`.

---

## Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| Artifact stuck **pending** | Stage not run or persist blocked (arbiter/schema) | Check `gui_log.jsonl`, `understanding/stage_runs/<stage>/attempt_*.json` |
| **partial** after stage done | Semantic gaps or schema drift | **Fill gaps** or fix JSON in editor; re-run from stage |
| Save fails in GUI | Zod or server schema error | Read error list in editor status / toast; fix fields |
| Empty themes after content | `memory_updates` not merged | Arbiter reject or `status != complete` — check attempt audit |
| Operator edits overwritten | Not verified | Set **Mark profile verified**; merge skips protected keys |

More: [troubleshooting.md](../workflows/troubleshooting.md).
