# LLM arbiter contract

**Status: spec only** — JSON returned by the economy-tier arbiter after each primary LLM call. See [llm-orchestration.md](../../cross-cutting/llm-orchestration.md).

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
| `attempt_number` | Current inner-loop attempt |

**Excluded:** full transcript, full `analysis_state.json`, raw audio references.

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

## Related

- [llm-stage-model-matrix.md](../../cross-cutting/llm-stage-model-matrix.md)
- [analysis-orchestration-loop.md](../../workflows/analysis-orchestration-loop.md)
