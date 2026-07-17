# Holistic fabrication fallback

Global LLM-backed (and deterministic-first) repair ladder for blocked LLM stages. Runs when a stage would otherwise halt on arbiter reject, lint failure, or incomplete envelope — using **stage inputs**, **volley context**, and **current artifacts** to fabricate grounded patches.

## When it runs

Holistic fabrication triggers automatically (config: `analysis.holistic_fabrication.enabled`) at:

1. **`apply_resilience_and_persist`** — before partial/full persist when envelope is blocked or lint/schema errors exist
2. **`bridge_adaptation_to_itr`** — before ITR auto-resolve on adaptation exhaustion / signature repeat
3. **`_try_good_enough_before_gate`** — before LLM gate halt in the stage retry loop

It applies to **all LLM stages** when `stages: "*"` (default).

## Ladder

1. **Collect gaps** — lint errors, schema errors, `status=blocked`, arbiter gaps
2. **Load context** — stage contract inputs + known fallbacks (`content_brief`, manifest, delivery brief, …)
3. **Deterministic repair** (when `deterministic_first: true`) — stage-specific rules, no API call
4. **LLM repair** (when `llm_enabled: true`) — economy-tier call via `run_prompt_envelope`, prompt `_shared/holistic-fabrication.system.txt`
5. **Re-lint / re-validate** — if clean, set `holistic_fabrication_cleared` and optionally override arbiter to `accept`

## Topic coverage (`topic_coverage_audit`)

Deterministic repair:

- Maps **orphan `segment_id`s** to nearest brief topic using segment text + `topic_tags`
- Synthesizes **`key_claims`** in `content_brief.json` from topic summaries when empty
- Builds **`claim_mappings`** from claims
- Recomputes **`coverage_score`**

This addresses the common failure mode: empty upstream claims + orphan intro segments → arbiter `enqueue_investigation`.

## Provenance

Repairs are recorded on the artifact:

```json
"_meta": {
  "holistic_fabrication": {
    "cleared_at": "...",
    "actions": ["map_orphan:seg_003->...", "synthesize_key_claims:6"]
  }
}
```

Envelope routing meta: `_routing_meta.holistic_fabrication_cleared: true`

## Config (`analysis.holistic_fabrication`)

| Key | Default | Purpose |
|-----|---------|---------|
| `enabled` | `true` | Master switch |
| `llm_enabled` | `true` | Use LLM when deterministic repair insufficient |
| `deterministic_first` | `true` | Run code-first repairs before API |
| `model_tier` | `economy` | LLM tier for fabrication calls |
| `max_calls_per_stage_attempt` | `2` | Cap LLM calls per attempt |
| `override_arbiter_on_clear` | `true` | Treat cleared envelopes as persistable |
| `allow_upstream_patches` | `true` | Write patches to input files (e.g. `content_brief.json`) |
| `stages` | `"*"` | Allowlist; `"*"` = all stages |

## Relationship to other ladders

| Layer | Role |
|-------|------|
| `llm_null_policy` / `llm_fabricate` | Benign defaults for **nullable optional** fields; defers evidentiary paths to holistic |
| `micro_gap_fill` | Targeted path patches from sufficiency engine |
| **Holistic fabrication** | Cross-field, context-aware repair including segment ids, claims, coverage |
| `partial_persist` | Saves valid fields while blocked; holistic runs **before** persist plan |

## Operator visibility

Log action ids:

- `holistic_fabrication.cleared`
- `holistic_fabrication.llm_failed`
- `itr.bridge.holistic_cleared`

After clear, re-run is optional — stage should persist as **full** when lint passes.

See also: [llm-output-normalization.md](./llm-output-normalization.md)
