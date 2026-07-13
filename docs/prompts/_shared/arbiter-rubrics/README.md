# Arbiter rubrics

Per-stage quality rubrics for the economy-tier LLM arbiter. Each file names one `stage_key` from `STAGE_ARTIFACT_SCHEMAS` in `src/interview_mux/prompt_validation.py`.

The runner loads `docs/prompts/_shared/arbiter-rubrics/<stage_key>.json` and merges it into `stage_expectations` alongside severity and `decompose_eligible` from [llm-stage-model-matrix.md](../../../cross-cutting/llm-stage-model-matrix.md).

**Related:** [arbiter.system.txt](../arbiter.system.txt) · [llm-arbiter-contract.md](../llm-arbiter-contract.md) · [LLM-ANALYSIS-ARCHITECTURE.md](../../../../LLM-ANALYSIS-ARCHITECTURE.md) §11

---

## File naming

```
docs/prompts/_shared/arbiter-rubrics/<stage_key>.json
```

`<stage_key>` must match the pipeline stage id exactly (e.g. `content_context`, `full_master_ranking`).

---

## JSON format

Each rubric is a single JSON object:

```json
{
  "stage_key": "content_context",
  "severity": "high",
  "accept_criteria": [
    "Human-readable condition that must hold to accept",
    "At least three items per rubric"
  ],
  "reject_patterns": [
    "Human-readable failure mode that blocks accept",
    "At least three items per rubric"
  ],
  "min_confidence_on_accept": 0.75,
  "decompose_eligible": true,
  "deterministic_lint_keys": [
    "machine_check_id"
  ]
}
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `stage_key` | string | yes | Must equal the filename stem and `STAGE_ARTIFACT_SCHEMAS` key |
| `severity` | enum | yes | `low` \| `medium` \| `high` — editorial impact if this stage is wrong |
| `accept_criteria` | string[] | yes | Arbiter should `accept` only when all material criteria are met (≥3 items) |
| `reject_patterns` | string[] | yes | Known failure signatures → `retry_uptier`, `decompose`, or `enqueue_investigation` (≥3 items) |
| `min_confidence_on_accept` | number | yes | Arbiter `confidence` floor for `accept` (typically `0.75`; runner may downgrade low-confidence accepts) |
| `decompose_eligible` | boolean | yes | Whether arbiter may return `decompose` with a `shard_plan` for this stage |
| `deterministic_lint_keys` | string[] | yes | Pre-arbiter lint ids the runner evaluates without an LLM call |
| `min_segment_coverage_ratio` | number | no | Override default **0.85** for `segment_coverage_ratio` on decompose-eligible stages (uses **1.0** when manifest has &lt;5 segments) |

### Severity bands (this repo)

| Severity | Stages |
|----------|--------|
| **high** | `content_context`, `missing_framing`, `optimal_questions`, `topic_coverage_audit`, `narrative_arc_plan`, `full_master_ranking`, `edl_narrative_audit`, `REMOVED_highlight_selection`, `sound_design_plan`, `REMOVED_sdp_flow2`, `REMOVED_podcast_show_description` |
| **medium** | `boundary_detection`, `segment_classification`, `content_brief_reanchor` |
| **low** | `speaker_roles`, `sound_design_palettes`, `transitions`, `sfx_prompt_craft`, `podcast_sfx_brief`, `sfx_brief` |

### Decompose-eligible stages

`decompose_eligible: true` only for:

`content_context`, `boundary_detection`, `segment_classification`, `content_brief_reanchor`, `missing_framing`, `topic_coverage_audit`, `full_master_ranking`, `REMOVED_highlight_selection`

All other stages must set `decompose_eligible: false`. When `true` and `truncation_flags` indicate tail blind spots, prefer `decompose` over `accept`.

### `deterministic_lint_keys`

Stable ids for runner-side checks (schema validation, artifact completeness, preflight, cross-artifact gates). Common keys:

| Key | Meaning |
|-----|---------|
| `envelope_status_complete` | Envelope `status` is `complete` |
| `schema_errors_empty` | No material JSON Schema errors on stage artifacts |
| `producer_artifact_complete` | On-disk producer path is `complete` per `artifact_completeness` |
| `segment_coverage_ratio` | Fraction of manifest segments referenced in stage output |
| `truncation_flags_absent` | No `truncation_flags` on volley |
| `truncation_requires_decompose` | `truncation_flags` set and stage is decompose-eligible |
| `cross_artifact_refs_valid` | Referenced `segment_id`s exist in upstream manifest/boundaries |
| `upstream_artifacts_complete` | Preflight upstream paths are present and complete |
| `min_row_count_met` | Artifact list length meets stage minimum |
| `confidence_gte_min` | Envelope `confidence` ≥ stage `min_confidence_on_accept` |

Stage rubrics list the subset that applies to that stage. The runner may add computed values (e.g. actual coverage ratio) to the arbiter payload; the arbiter uses `accept_criteria` / `reject_patterns` for semantic judgment.

### Generic vs stage-specific lint

`deterministic_lint()` in `src/interview_mux/deterministic_lint.py` runs **two layers**:

1. **Generic** — all standard keys from `deterministic_lint_keys` implemented in `_lint_generic()`:
   `envelope_status_complete`, `schema_errors_empty`, `producer_artifact_complete`, `confidence_gte_min`, `upstream_artifacts_complete`, `cross_artifact_refs_valid`, `segment_coverage_ratio`, `min_row_count_met`, `truncation_requires_decompose`, `truncation_flags_absent`.
   Error strings are prefixed with the key (e.g. `confidence_gte_min: 0.6 < 0.75`, `segment_coverage_ratio: 0.1 < 0.85`).

2. **Stage-specific** — handlers in `_LINTERS` (e.g. `_lint_transitions`, `_lint_sound_design_plan`) for semantic rules that need stage artifact shape.

Rubrics should list generic keys that apply to every stage plus any stage-only ids documented in [stage-quality-scorecard.md](../../../cross-cutting/stage-quality-scorecard.md). Do not duplicate stage-specific rules as generic keys.

---

## Verdict mapping (arbiter)

| Situation | Typical verdict |
|-----------|-----------------|
| All `accept_criteria` met; no `reject_patterns`; lint keys pass | `accept` |
| Parseable but weak; flagship not yet used | `retry_uptier` |
| `decompose_eligible` and evidence too large or partial timeline coverage | `decompose` (non-empty `shard_plan`) |
| Wrong upstream stage, operator input, or non-decomposable truncation | `enqueue_investigation` |

Do **not** use rubrics to rewrite artifacts — routing only. See [llm-arbiter-contract.md](../llm-arbiter-contract.md).

---

## Maintenance

When adding a stage to `STAGE_ARTIFACT_SCHEMAS`:

1. Add `<stage_key>.json` in this directory.
2. Align severity and `decompose_eligible` with [llm-stage-model-matrix.md](../../../cross-cutting/llm-stage-model-matrix.md) unless intentionally overridden.
3. Derive `accept_criteria` / `reject_patterns` from the stage system prompt and examples under `docs/prompts/`.
4. Register new `deterministic_lint_keys` in the runner when implementing pre-arbiter lint.
