# JSON Schema coverage — gaps, fixes, and guards

This document answers: **which on-disk artifacts have a formal JSON Schema**, which do not yet, and how we keep contracts **resilient** (operators, code, and LLMs stay aligned).

## Problem: coverage vs. artifact layout

[artifact-layout.md](./artifact-layout.md) lists many files under a run workspace. Only a **subset** have schemas under `docs/cross-cutting/json-schemas/`. When a path has **no schema**:

- Operators and tools cannot cheaply validate shape before mux or export.
- Docs and code can drift without a failing check.
- Downstream stages may assume fields that upstream never guaranteed.

That is expected for **binary/audio** paths and for **spec-ahead** artifacts (e.g. `edl.json` before BUILD-067), but it should be **explicit** so nobody treats “mentioned in layout” as “schema-validated in CI.”

## What is validated today (hard guard)

Python validates LLM **`artifacts`** per stage using `interview_mux.prompt_validation.validate_stage_artifacts` and files under `docs/cross-cutting/json-schemas/` (see [evaluation-metrics.md](./evaluation-metrics.md)).

| Stage key | Schema file | Notes |
|-----------|---------------|--------|
| `speaker_roles` | `artifacts/speakers_artifact.schema.json` | |
| `content_context` | `artifacts/content_brief_artifact.schema.json` | |
| `boundary_detection` | `artifacts/boundaries_artifact.schema.json` | |
| `segment_classification` | `artifacts/manifest_artifact.schema.json` | Classification slice; see [segment-schema.md](./segment-schema.md) |
| `missing_framing` | `artifacts/gap_evaluations_artifact.schema.json` | |
| `optimal_questions` | `gap_report.schema.json` (repo root of json-schemas) | |
| `topic_coverage_audit` | `artifacts/coverage_audit_artifact.schema.json` | |
| `narrative_arc_plan` | `artifacts/narrative_plan_artifact.schema.json` | |
| `full_master_ranking` | `artifacts/master_selection_artifact.schema.json` | |
| `highlight_selection` | `artifacts/highlights_artifact.schema.json` | |
| `transitions` | `artifacts/transitions_artifact.schema.json` | |
| `podcast_sfx_brief` | `artifacts/podcast_sfx_artifact.schema.json` | |
| `sfx_brief` | `artifacts/sfx_montage_artifact.schema.json` | |
| `podcast_show_description` | `artifacts/show_description_artifact.schema.json` | Flow 3; planned BUILD-045 |

**Guard:** Any new LLM stage that writes structured JSON should register in `src/interview_mux/prompt_validation.py` → `STAGE_ARTIFACT_SCHEMAS` **and** add or extend a schema file. Missing registration = **silent** non-validation (worst case).

## Schemas that exist but are not tied to `validate_stage_artifacts`

These support docs, optional tooling, or future gates; they are **not** automatically run per LLM stage unless wired separately:

| Schema | Typical use |
|--------|-------------|
| [analysis_envelope.schema.json](./json-schemas/analysis_envelope.schema.json) | Envelope shape; preamble references it |
| [analysis_state.schema.json](./json-schemas/analysis_state.schema.json) | Profile / memory file |
| [segment.schema.json](./json-schemas/segment.schema.json) | Full timeline segment (timestamps + text); canonical reference |
| [transcript_review.schema.json](./json-schemas/transcript_review.schema.json) | `review_queue.json` shape |
| [investigation_queue.schema.json](./json-schemas/investigation_queue.schema.json) | Queue file |

**Guard:** When adding GUI import/export or a new validator, prefer reusing these files instead of duplicating field lists in prose-only docs.

## Artifacts in layout with **no** JSON Schema yet (explicit gap)

Treat these as **contract TBD** until a schema lands (and ideally a validator or mux-time check):

| Path | Why a schema matters | Target / ticket |
|------|----------------------|-----------------|
| `flow_1_master/edl.json` | Mux depends on timeline events | BUILD-067 |
| `segments/nle_edits.json` | Overrides selection / EDL | BUILD-068 |
| `run_meta.json` | Flow, preclean offers, timestamps | Consider `run_meta.schema.json` |
| `transcript/full.json` | AWS Transcribe export shape | Optional: external-shape schema |
| `transcript/corrections.json` | Operator edits | Small object schema |
| `ingest/checksums.json` | Lineage | Small object schema |
| `understanding/sound_design_plan.json` | SDP | BUILD-060 |
| `understanding/source_acoustic_profile.json` | Per-run pacing/mix profile | Spec: [source-derived-sonic-mix-profile.md](./source-derived-sonic-mix-profile.md) |
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
| `understanding/analysis_state.json` | `analysis_state.schema.json` | No (manual / future) |
| `segments/manifest.json` | Same as manifest artifact | Via `segment_classification` output only |
| `flow_1_master/selection.json` | Via `master_selection_artifact` shape | When produced by ranking stage |
| `flow_1_master/edl.json` | **No** | **No** |
| `flow_3_description/show_description.json` | Via `show_description_artifact` | When BUILD-045 ships |
| `segments/nle_edits.json` | **No** | **No** |
| `transcript/review_queue.json` | `transcript_review.schema.json` | No (unless wired) |

## Related

- [artifact-layout.md](./artifact-layout.md) — paths
- [segment-schema.md](./segment-schema.md) — segment shapes and flags (alignment topic #2)
- [build-out/README.md](../build-out/README.md) — tickets for EDL / SDP / NLE
- [prompts/README.md](../prompts/README.md) — prompt ↔ schema conventions
- [config-keys.md](./config-keys.md) — runtime caps that drive validation and context
