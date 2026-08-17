# JSON Schema coverage — gaps, fixes, and guards

This document answers: **which on-disk artifacts have a formal JSON Schema**, which do not yet, and how we keep contracts **resilient** (operators, code, and LLMs stay aligned).

## Problem: coverage vs. artifact layout

[artifact-layout.md](./artifact-layout.md) lists many files under a run workspace. Only a **subset** have schemas under `docs/cross-cutting/json-schemas/`. When a path has **no schema**:

- Operators and tools cannot cheaply validate shape before mux or export.
- Docs and code can drift without a failing check.
- Downstream stages may assume fields that upstream never guaranteed.

That is expected for **binary/audio** paths and for artifacts awaiting boundary validators, but it should be **explicit** so nobody treats “mentioned in layout” as “schema-validated in CI.”

## What is validated today (hard guard)

Python validates LLM **`artifacts`** per stage using `interview_mux.prompt_validation.validate_stage_artifacts` and files under `docs/cross-cutting/json-schemas/` (see [evaluation-metrics.md](./evaluation-metrics.md)).

| Stage key | Schema file | Notes |
|-----------|---------------|--------|
| `speaker_roles` | `artifacts/speakers_artifact.schema.json` | |
| `content_context` | `artifacts/content_brief_artifact.schema.json` | |
| `boundary_detection` | `artifacts/boundaries_artifact.schema.json` | |
| `segment_classification` | `artifacts/manifest_artifact.schema.json` | Classification slice; see [segment-schema.md](./segment-schema.md) |
| `sound_design_palettes` | `artifacts/sound_design_palettes_artifact.schema.json` | Writes SDP `coherence` + `palettes`; persisted into `understanding/sound_design_plan.json` |
| `missing_framing` | `artifacts/gap_evaluations_artifact.schema.json` | |
| `optimal_questions` | `gap_report.schema.json` (repo root of json-schemas) | |
| `topic_coverage_audit` | `artifacts/coverage_audit_artifact.schema.json` | |
| `narrative_arc_plan` | `artifacts/narrative_plan_artifact.schema.json` | |
| `full_master_ranking` | `artifacts/master_selection_artifact.schema.json` | |
| `REMOVED_highlight_selection` | `artifacts/highlights_artifact.schema.json` | |
| `transitions` | `artifacts/transitions_artifact.schema.json` | |
| `podcast_sfx_brief` | `artifacts/podcast_sfx_artifact.schema.json` | |
| `sound_design_plan` | `artifacts/sound_design_plan_artifact.schema.json` | Merged into `understanding/sound_design_plan.json`; full SDP validated on persist |
| `REMOVED_sdp_flow2` | `artifacts/REMOVED_sdp_flow2_artifact.schema.json` | Merged into `understanding/sound_design_plan.json`; full SDP validated on persist |
| `sfx_prompt_craft` | `artifacts/sfx_prompts_artifact.schema.json` | Writes `sound_design/sfx_prompts.json` |
| `sfx_brief` | `artifacts/sfx_montage_artifact.schema.json` | |
| `REMOVED_podcast_show_description` | `artifacts/show_description_artifact.schema.json` | Flow 3 |

**Guard:** Any new LLM stage that writes structured JSON should register in `src/interview_mux/prompt_validation.py` → `STAGE_ARTIFACT_SCHEMAS` **and** add or extend a schema file. Missing registration = **silent** non-validation (worst case).

## Schemas that exist but are not tied to `validate_stage_artifacts`

These support docs, optional tooling, or future gates; they are **not** automatically run per LLM stage unless wired separately:

| Schema | Typical use |
|--------|-------------|
| [analysis_envelope.schema.json](./json-schemas/analysis_envelope.schema.json) | Envelope shape; preamble references it |
| [analysis_state.schema.json](./json-schemas/analysis_state.schema.json) | Profile / memory file |
| [segment.schema.json](./json-schemas/segment.schema.json) | Full timeline segment (timestamps + text); canonical reference |
| [transcript_review.schema.json](./json-schemas/transcript_review.schema.json) | `review_queue.json` shape |
| [disfluencies.schema.json](./json-schemas/disfluencies.schema.json) | `transcript/disfluencies.json` catalog |
| [investigation_queue.schema.json](./json-schemas/investigation_queue.schema.json) | Queue file |
| [context_index.schema.json](./json-schemas/context_index.schema.json) | `understanding/context_index.json` volley memory v2 |
| [sound_design_plan.schema.json](./json-schemas/sound_design_plan.schema.json) | `understanding/sound_design_plan.json` baseline + Wave 5 planning contract |
| [sonic_context.schema.json](./json-schemas/sonic_context.schema.json) | `understanding/sonic_context.json` — tags, scenario policy, cue opportunities (BUILD-SFX-01) |
| [soundscape_policy.schema.json](./json-schemas/soundscape_policy.schema.json) | `understanding/soundscape_policy.json` — unified soundscape standards + cue slots (BUILD-SS-01) |
| [artifacts/mmaudio_qa.schema.json](./json-schemas/artifacts/mmaudio_qa.schema.json) | `sound_design/mmaudio_qa.json` post-generation QA |
| [artifacts/musicgen_candidates.schema.json](./json-schemas/artifacts/musicgen_candidates.schema.json) | `sound_design/musicgen_candidates.json` candidate selection audit |
| [artifacts/underbed_ab_qc.schema.json](./json-schemas/artifacts/underbed_ab_qc.schema.json) | `master/underbed_ab_qc.json` automated stem-derived masking/presence audit |
| [refinement_agenda.schema.json](./json-schemas/refinement_agenda.schema.json) | `understanding/refinement_agenda.json` — L0 eligible-class agenda ([refinement-passes.md](./refinement-passes.md)) |
| [refinement_ledger.schema.json](./json-schemas/refinement_ledger.schema.json) | `understanding/refinement_ledger.json` — CFI call ledger, second-run cap |
| [refinement_plan.schema.json](./json-schemas/refinement_plan.schema.json) | `understanding/refinement_plan.json` — L1 activate/skip gate decisions |

**On-disk SDP validation (BUILD-060):** `prompt_validation.validate_sound_design_plan` runs when `ensure_analysis_workspace` writes the empty scaffold and when Wave 5 stages persist into `understanding/sound_design_plan.json` (`sound_design_stages._validate_sound_design_plan`).

**On-disk artifact validation (BUILD-067 + artifact generation):** `prompt_validation.validate_artifact_write` runs from `RunContext.write_json`, `write_validated_artifact`, and GUI `PUT /artifact` / analysis-profile. All LLM JSON paths in `STAGE_ARTIFACT_DISK_PATHS` are registered — see [artifact-generation-and-validation.md](./artifact-generation-and-validation.md). `edl` also validates before write. CLI: `python tools/verify_edl.py --run-id <exec_id>`.

**Frontend Zod (GUI):** JSON Schema remains canonical in this folder. `python tools/codegen_zod_schemas.py` emits `frontend/src/schemas/generated/*.ts`; `validateArtifactWrite()` mirrors `ARTIFACT_WRITE_VALIDATORS` for pre-save UX. Regenerate after schema edits, then `cd frontend && npm run build`.

| Validator | Artifact path | Wired on write? |
|-----------|---------------|-----------------|
| `validate_edl` | `master/edl.json` | Yes (`edl` + `write_json`) |
| `validate_master_transcript` | `master/transcript.json` | Yes (`master_transcript_build` + `write_json`) |
| `validate_asset_transcript` | `transcripts/{speech,vo,transition}/*.json` | Yes (`write_json` path glob) |
| `validate_edl_narrative_audit` | `master/edl_narrative_audit.json` | Yes (`edl_narrative_audit` + `write_json`) |
| `validate_source_acoustic_profile` | `understanding/source_acoustic_profile.json` | Yes |
| `validate_analysis_state` | `understanding/analysis_state.json` | Yes |
| `validate_context_index` | `understanding/context_index.json` | Yes |
| `validate_content_brief` | `understanding/content_brief.json` | Yes |
| `validate_speakers` | `understanding/speakers.json` | Yes |
| `validate_boundaries` | `segments/boundaries.json` | Yes |
| `validate_manifest` | `segments/manifest.json` | Yes |
| `validate_gap_evaluations` | `understanding/gap_evaluations.json` | Yes |
| `validate_gap_report` | `understanding/gap_report.json` | Yes |
| `validate_nugget_layup_plan` | `understanding/nugget_layup_plan.json` | Yes |
| `validate_omit_ledger` | `understanding/omit_ledger.json` | Yes |
| `validate_coverage_audit` | `master/coverage_audit.json` | Yes |
| `validate_narrative_plan` | `master/narrative_plan.json` | Yes |
| `validate_transitions` | `master/transitions.json` | Yes |
| `validate_podcast_sfx_brief` | `master/podcast_sfx_brief.json` | Yes |
| `validate_highlights_selection` | `REMOVED_flow2/selection.json` | Yes |
| `validate_sfx_montage_brief` | `REMOVED_flow2/sfx_brief.json` | Yes |
| `validate_show_description` | `show_notes/show_description.json` | Yes |
| `validate_sfx_prompts` | `sound_design/sfx_prompts.json` | Yes |
| `validate_sonic_context` | `understanding/sonic_context.json` | Yes (BUILD-SFX-01) |
| `validate_soundscape_policy` | `understanding/soundscape_policy.json` | Yes (BUILD-SS-01) |
| `validate_mmaudio_qa` | `sound_design/mmaudio_qa.json` | Yes (BUILD-SFX-01) |
| `validate_musicgen_candidates` | `sound_design/musicgen_candidates.json` | Yes |
| `validate_underbed_ab_qc` | `master/underbed_ab_qc.json` | Yes |
| `validate_placement_adjustments` | `sound_design/placement_adjustments.json` | Yes (BUILD-SFX-01) |
| `validate_refinement_agenda` | `understanding/refinement_agenda.json` | Yes |
| `validate_refinement_ledger` | `understanding/refinement_ledger.json` | Yes |
| `validate_refinement_plan` | `understanding/refinement_plan.json` | Yes |
| `validate_run_meta` | `run_meta.json` | Yes |
| `validate_transcript_corrections` | `transcript/corrections.json` | Yes |
| `validate_disfluencies` | `transcript/disfluencies.json` | Yes |
| `validate_ingest_checksums` | `ingest/checksums.json` | Yes |

**Guard:** When adding GUI import/export or a new validator, prefer reusing these files instead of duplicating field lists in prose-only docs.

## Artifacts in layout with **no** JSON Schema yet (explicit gap)

Treat these as **contract TBD** until a schema lands (and ideally a validator or mux-time check):

| Path | Why a schema matters | Status |
|------|----------------------|--------|
| `master/edl.json` | Mux depends on timeline events | **Schema yes** — `artifacts/edl.schema.json`; **validator wired** (`validate_edl`, `tools/verify_edl.py`) |
| `segments/nle_edits.json` | Overrides selection / EDL | **Schema yes** — `nle_edits.schema.json`; validator on `save_nle` + `write_json` |
| `transcript/full.json` | Local MLX STT export shape | Optional: external-shape schema |
| `understanding/source_acoustic_profile.json` | Per-run pacing/mix profile | `source_acoustic_profile.schema.json` · validator wired |
| `gui_log.jsonl` | NDJSON stream | Often line-schema only |

**Best-in-class fixes (priority order):**

1. **Add a schema file** next to others under `json-schemas/` (or `artifacts/` if it is stage output), version with `schema_version` if the object evolves.
2. **Wire validation** at the boundary that consumes the file: mux builder, GUI save, or CLI `verify_*` — fail fast with path + JSON Pointer in the error message.
3. **Document the contract** in [artifact-layout.md](./artifact-layout.md) with a one-line link to the schema file (this doc is the index; per-file tables can duplicate the “schema?” column).
4. **Golden fixtures** in `tests/fixtures/` (optional) — smallest valid JSON per schema for regression.

**Resilience guards (operational):**

- **Pre-mux checklist:** If `edl.json` / `nle_edits.json` is required for a build wave, add an explicit “file exists and validates” step in [workflows/smoke-test.md](../workflows/smoke-test.md) when those tickets ship.
- **CI:** Run `jsonschema` (pinned in [anchored-toolchain.md](./anchored-toolchain.md); use **Context7** at that version when changing validators) against fixtures whenever schemas change.
- **Do not infer:** If code reads a field not in the schema, either extend the schema or treat the field as experimental and undocumented.

## Hyper-useful quick matrix (artifact → schema?)

| Artifact | Schema in repo? | Stage validation? |
|----------|-----------------|-------------------|
| Envelope `artifacts` from LLM stages | Per-stage rows above | Yes |
| `understanding/analysis_state.json` | `analysis_state.schema.json` | Yes (GUI + `write_json`) |
| `understanding/sound_design_plan.json` | `sound_design_plan.schema.json` | Yes (init + Wave 5 persist) |
| `understanding/sonic_context.json` | `sonic_context.schema.json` | Yes (`sonic_context_build` + cross-validate) |
| `understanding/soundscape_policy.json` | `soundscape_policy.schema.json` | Yes (`soundscape_policy_build`) |
| `sound_design/mmaudio_qa.json` | `mmaudio_qa.schema.json` | Yes (post-`mmaudio_sfx_flow*`) |
| `sound_design/musicgen_candidates.json` | `musicgen_candidates.schema.json` | Yes (`mmaudio_sfx`) |
| `master/underbed_ab_qc.json` | `underbed_ab_qc.schema.json` | Yes (`mix`) |
| `sound_design/placement_adjustments.json` | `placement_adjustments.schema.json` | Yes (mix-time QA hints) |
| `understanding/source_acoustic_profile.json` | `source_acoustic_profile.schema.json` | Yes (`source_acoustic_profile` stage + GUI) |
| `run_meta.json` | `run_meta.schema.json` | Yes (`write_json`) |
| `mastering/homunculus/*.json` | ledger/persona/judgment (jsonl for issues/admitted) | 0.1.0 brain — [mastering-homunculus.md](./mastering-homunculus.md) |
| `ingest/checksums.json` | `ingest_checksums.schema.json` | Yes (`ingest` stage) |
| `transcript/corrections.json` | `transcript_corrections.schema.json` | Yes (transcript review + GUI) |
| `segments/manifest.json` | Same as manifest artifact | Via `segment_classification` output only |
| `master/selection.json` | Via `master_selection_artifact` shape | When produced by ranking stage |
| `master/edl_narrative_audit.json` | `edl_narrative_audit_artifact.schema.json` | Yes (`edl_narrative_audit`) |
| `master/edl.json` | `edl.schema.json` (BUILD-067) | Yes (`edl` + `tools/verify_edl.py`) |
| `show_notes/show_description.json` | Via `show_description_artifact` | Flow 3 LLM stage |
| `segments/nle_edits.json` | `nle_edits.schema.json` | Yes (`save_nle` + `write_json`) |
| `transcript/review_queue.json` | `transcript_review.schema.json` | Yes (`write_json`) |

## OpenAI strict schema lint (LLM stages)

Every LLM stage that uses `analysis.structured_outputs` sends a composed strict `json_schema` to OpenAI. Invalid schemas (e.g. arrays without `items`) fail with HTTP 400 **before** inference.

**Guards (CI + runtime):**

1. **Artifact schemas** under `json-schemas/artifacts/` must define `items` for every `array` field used in LLM output.
2. **`tools/codegen_openai_schemas.py`** regenerates `json-schemas/composed/*.openai.json` — run after schema edits; `tests/test_codegen_openai_schemas_fresh.py` fails if the cache is stale.
3. **`interview_mux.openai_schema_lint`** lints composed schemas (`lint_openai_strict_schema` / `assert_openai_strict_schema`).
4. **`compose_envelope_schema`** and **`resolve_response_format`** call the linter when `strict: true`; `strictify_schema` raises if any array lacks `items`.
5. **`tests/test_openai_structured_output.py`** parametrizes all `STAGE_ARTIFACT_SCHEMAS` keys for compose + lint.

**Workflow after editing a stage artifact schema:**

```bash
python tools/codegen_openai_schemas.py
python tools/codegen_zod_schemas.py
cd frontend && npm run build   # if GUI bundle should ship updated Zod
pytest tests/test_openai_schema_lint.py tests/test_codegen_openai_schemas_fresh.py tests/test_codegen_zod.py tests/test_openai_structured_output.py -q
pip install -e .               # restart web runner so site-packages picks up code + schemas
```

**Wave 3 follow-ups (non-blocking):** `deterministic_lint` vs `narrative_plan` chapter shape; `null_field_policy` `speakers[].label` vs speakers schema; Zod null unions for optional fields.

## Related

- [artifact-layout.md](./artifact-layout.md) — paths
- [segment-schema.md](./segment-schema.md) — segment shapes and flags (alignment topic #2)
- [prompts/README.md](../prompts/README.md) — prompt ↔ schema conventions
- [config-keys.md](./config-keys.md) — runtime caps that drive validation and context
