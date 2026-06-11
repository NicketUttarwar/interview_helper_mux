# LLM arbiter contract

**Status: implemented (BUILD-073)** — JSON returned by the economy-tier arbiter after each primary LLM call. See [llm-orchestration.md](../../cross-cutting/llm-orchestration.md).

**System prompt:** [arbiter.system.txt](./arbiter.system.txt)

---

## Purpose

Judge whether a **primary** stage response is good enough to merge into `analysis_state.json` and persist artifacts — or whether to retry with a higher tier, decompose into shards, or enqueue an investigation.

The arbiter is **not** an editorial rewrite pass; it only routes.

---

## Arbiter inputs (user message body)

Structured JSON or markdown sections provided by the runner (compact):

| Field | Description |
|-------|-------------|
| `stage_key` | Pipeline stage being judged |
| `envelope_summary` | `status`, `confidence`, `reasoning_summary`, artifact keys and row counts |
| `schema_errors` | List of validation messages (empty if clean) |
| `context_chars` | Approximate volley size |
| `truncation_flags` | e.g. `transcript_capped`, `segments_dropped`, `max_stage_data_chars` |
| `stage_expectations` | `severity`, `default_tier`, `decompose_eligible` from matrix |
| `accept_criteria` | From per-stage rubric JSON — conditions that must hold to `accept` |
| `reject_patterns` | From rubric — known failure signatures that block `accept` |
| `min_confidence_on_accept` | Rubric floor (typically `0.75`) for arbiter `confidence` on `accept` |
| `deterministic_lint_keys` | Pre-arbiter lint ids already evaluated (see `deterministic_lint_errors`) |
| `attempt_number` | Current inner-loop attempt |

**Excluded:** full transcript, full `analysis_state.json`, raw audio references.

**Rubric source:** `docs/prompts/_shared/arbiter-rubrics/<stage_key>.json` loaded by `arbiter_expectations.py`. Index: [arbiter-stage-rubrics.md](./arbiter-stage-rubrics.md).

---

## Response schema

Return a single JSON object (no markdown fence required if `response_format` is used):

```json
{
  "verdict": "accept",
  "confidence": 0.85,
  "gaps": [],
  "shard_plan": [],
  "suggested_investigation": null,
  "reasoning_summary": "Artifacts cover all segments; schema clean."
}
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `verdict` | enum | yes | `accept` \| `retry_uptier` \| `decompose` \| `enqueue_investigation` |
| `confidence` | number 0–1 | yes | Arbiter certainty in this verdict |
| `gaps` | string[] | yes | Human-readable issues (may be empty on accept) |
| `shard_plan` | object[] | yes | Required when `verdict=decompose`; else `[]` |
| `suggested_investigation` | object \| null | yes | When `enqueue_investigation`; else `null` |
| `reasoning_summary` | string | yes | One short paragraph for audit log |

### `shard_plan[]` items

| Field | Type | Description |
|-------|------|-------------|
| `label` | string | e.g. `batch_1_of_3` |
| `segment_ids` | string[] | Segments in this shard (preferred) |
| `start_ms` | number | Optional for boundary shards |
| `end_ms` | number | Optional for boundary shards |

Max **8** items per plan.

### `suggested_investigation` (when enqueueing)

| Field | Type | Description |
|-------|------|-------------|
| `kind` | string | e.g. `theme_unmapped`, `gap_unresolved`, `segment_ambiguity` |
| `question` | string | What to resolve |
| `suggested_action.stage` | string | Stage to re-run (optional) |
| `blocking` | boolean | Default true for arbiter-driven enqueue |

---

## Verdict rules

| Verdict | Use when |
|---------|----------|
| `accept` | Stage intent met; schema acceptable; no material truncation blind spots |
| `retry_uptier` | Response parseable but weak; primary tier below flagship; fix likely with stronger model |
| `decompose` | `decompose_eligible` and evidence too large or partial coverage across timeline |
| `enqueue_investigation` | Cross-stage fix needed, operator input, or non-eligible stage needs another pass |

**Do not** return `decompose` with an empty `shard_plan`. **Do not** return `accept` when required artifacts are missing.

---

## Examples

### Good — accept

```json
{
  "verdict": "accept",
  "confidence": 0.9,
  "gaps": [],
  "shard_plan": [],
  "suggested_investigation": null,
  "reasoning_summary": "gap_evaluations present for 42 segments; no schema errors."
}
```

### Good — decompose

```json
{
  "verdict": "decompose",
  "confidence": 0.88,
  "gaps": ["Only 35 of 80 segments evaluated; max_gap_evaluations cap hit."],
  "shard_plan": [
    { "label": "seg_001-040", "segment_ids": ["seg_001", "seg_002"] },
    { "label": "seg_041-080", "segment_ids": ["seg_041", "seg_042"] }
  ],
  "suggested_investigation": null,
  "reasoning_summary": "Split gap pass into two batches then collate."
}
```

### Bad — accept despite truncation

```json
{
  "verdict": "accept",
  "confidence": 0.6,
  "gaps": ["transcript tail not in context"],
  "shard_plan": [],
  "suggested_investigation": null,
  "reasoning_summary": "Looks fine."
}
```

Runner should treat low-confidence accept with material `gaps` as `retry_uptier` or `decompose` per stage rules (implementation detail).

### Bad — accept below rubric confidence floor

```json
{
  "verdict": "accept",
  "confidence": 0.55,
  "gaps": [],
  "shard_plan": [],
  "suggested_investigation": null,
  "reasoning_summary": "Brief looks complete."
}
```

When `confidence < min_confidence_on_accept` (from `stage_expectations`) or any `reject_patterns` match the envelope summary, runner downgrades to `retry_uptier` or blocks merge per `deterministic_lint` (`confidence_gte_min`).

### Bad — decompose without plan

```json
{
  "verdict": "decompose",
  "confidence": 0.9,
  "gaps": [],
  "shard_plan": [],
  "suggested_investigation": null,
  "reasoning_summary": "Too big."
}
```

Runner must fall back to `enqueue_investigation`.

---

## Stage rubric fields (in `stage_expectations`)

Loaded from `arbiter-rubrics/<stage_key>.json` and passed in the arbiter user payload:

| Field | Type | Description |
|-------|------|-------------|
| `accept_criteria` | string[] | Editorial conditions that must hold for `accept` (≥3 per rubric) |
| `reject_patterns` | string[] | Failure signatures → `retry_uptier`, `decompose`, or `enqueue_investigation` |
| `min_confidence_on_accept` | number | Arbiter `confidence` floor on `accept` (typically `0.75`) |

The arbiter judges semantic fit against these lists; `deterministic_lint.py` enforces machine checks (`deterministic_lint_keys`) before the arbiter call. See [arbiter-rubrics/README.md](./arbiter-rubrics/README.md).

---

## Related

- [llm-stage-model-matrix.md](../../cross-cutting/llm-stage-model-matrix.md)
- [arbiter-stage-rubrics.md](./arbiter-stage-rubrics.md)
- [analysis-orchestration-loop.md](../../workflows/analysis-orchestration-loop.md)
