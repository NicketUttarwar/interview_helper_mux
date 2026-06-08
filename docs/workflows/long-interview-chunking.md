# Long interviews — context caps and chunking policy

When a recording is **long or dense**, LLM stages may hit **token / character caps** defined in `config/app.defaults.json` → `analysis.context` and injected into the volley builder (`src/interview_mux/context_volley.py`). See [context-padding.md](../cross-cutting/context-padding.md) for what each stage receives.

This document is the **policy** for operators and implementers: what to expect, what breaks, and how to recover **without** silently losing fidelity.

**Shard → collate (BUILD-073/084, shipped):** when the arbiter returns `decompose` for eligible stages, the runner shards evidence and collates — [llm-orchestration.md](../cross-cutting/llm-orchestration.md).

**Proactive decompose (`content_context`):** when transcript length exceeds `proactive_decompose_chars` (default 72k, aligned with `transcript_full_chars`), the runner skips the single primary pass and goes straight to shard/collate before the arbiter.

---

## Caps (authoritative keys)

| Key | Role | If too low / mis-set |
|-----|------|----------------------|
| `transcript_excerpt_chars` | Legacy single-excerpt fallback for `speaker_roles` | Truncated evidence in mid-pipeline stages |
| `transcript_full_chars` | Full transcript cap for `content_context` / `boundary_detection` | Boundary/content passes truncated; wrong splits |
| `speaker_roles_sample_chars` | Total budget for opening/middle/closing `transcript_samples` | Role inversion on long interviews |
| `max_transcript_shards` | Max shard calls per transcript or segment batch | Tail of long interviews still blind |
| `proactive_decompose_chars` | Auto shard/collate threshold for `content_context` | Very long interviews hit single-pass truncation |
| `segment_text_max_chars` | Per-segment text in compact lists | Gap pass blind to long answers |
| `max_segments_in_context` | Max segments passed into some stages | Tail segments never scored in that call |
| `max_segments_in_gap_pass` | Gap evaluation window | Far-end gaps skipped in one pass |
| `max_gap_evaluations` | Rows in missing-framing batch | Some segments not evaluated until re-run |
| `max_stage_data_chars` | Total JSON payload to model | Envelope truncated / validation odd |
| `interviewer_sample_lines` | Lines fed into transitions stage | Weaker bridge tone match |

**Guard:** Raising caps increases **cost and latency**; lowering caps increases **blind spots**. Document any production change in release notes.

---

## Decompose-eligible stages (shipped)

| Stage | Shard strategy |
|-------|----------------|
| `content_context` | Transcript text chunks (proactive when over `proactive_decompose_chars`) |
| `boundary_detection` | Time batches or segment batches |
| `segment_classification` | Segment batches |
| `content_brief_reanchor` | Segment batches |
| `missing_framing` | Gap segment batches |
| `topic_coverage_audit` | Segment batches |
| `full_master_ranking` | Chapter or segment batches |
| `highlight_selection` | Candidate segment batches |

---

## Operator expectations (honest)

1. **Shard/collate (BUILD-073 + BUILD-084):** When the arbiter returns `decompose` on eligible stages (or proactive decompose fires for `content_context`), the runner runs sequential shard calls then one collate call. Memory and artifacts merge only after a successful collate (or arbiter `accept`). Rejected primaries do not pollute `analysis_state.json`.
2. **Two-pass content brief:** `content_context` extracts thesis/topics/claims/hypotheses; `content_brief_reanchor` (after `segment_classification`) grounds `segment_ids` and `topic_relationships`. A **complete** `content_brief.json` after analysis requires both passes.
3. **`investigation_queue.json` + `follow_up_investigations`** surface “we need another pass on region X” — watch for `theme_unmapped`, `segment_ambiguity`, `gap_unresolved`, `context_truncated`.
4. **Profile verification** (`meta.operator_verified`) before Flow 1 extended reduces wasted extended passes on wrong themes — see [operator-gates.md](./operator-gates.md).

---

## Strategies (pick one or combine)

| Strategy | When | Rerun boundary | Tradeoff |
|----------|------|----------------|----------|
| **Raise caps in config** | You have model headroom + budget | None if still single pass | $$; may hit model max context |
| **Re-run from a mid pipeline stage** | After fixing G0 / manifest / profile | `--from-stage` per [idempotent-runs.md](./idempotent-runs.md) | Downstream invalidated |
| **Operator edits + targeted re-run** | A theme is wrong but transcript OK | e.g. `--from-stage segment_classification` | Fastest when root cause is classification |
| **Split into two executions** (manual) | Two logical “halves” of same recording | Two `run_id`s; merge in NLE later (advanced) | Editorial burden outside tool |
| **Shard/collate** | Arbiter `decompose` on eligible stages (or deterministic plan when truncated) | Same stage after collate | [llm-orchestration.md](../cross-cutting/llm-orchestration.md) |

---

## Rerun boundaries (minimal invalidation)

| Goal | Typical `--from-stage` |
|------|-------------------------|
| Fix transcript only | `transcript_review` sign-off then `speaker_roles` or full `analysis` |
| Fix semantic brief only | `content_context` (invalidates reanchor + downstream) |
| Fix timeline anchors / topic links | `content_brief_reanchor` (after manifest exists) |
| Fix segmentation only | `boundary_detection` (invalidates downstream) |
| Fix gaps only | `missing_framing` after manifest stable |
| Fix Flow 1 order only | `full_master_ranking` (requires upstream Flow 1 artifacts) |

See [feedback-loops-and-reruns.md](./feedback-loops-and-reruns.md).

---

## Red flags (investigate)

- Coverage audit shows **systematic** `missing_coverage` for tail topics.
- `max_segments_in_context` hit in logs (if logged) or obvious omission of high-`end_ms` segments in stage input.
- Many `partial` envelopes with `reasoning_summary` citing “truncated input”.
- `content_brief.json` complete after `content_context` but **partial** after full analysis — missing `topic_relationships` or `topics[].segment_ids` until `content_brief_reanchor` runs.

**Action:** Increase relevant cap **or** split work / re-run with corrected upstream artifacts — do not only re-prompt.

---

## Related

- [context-padding.md](../cross-cutting/context-padding.md)
- [llm-stage-model-matrix.md](../cross-cutting/llm-stage-model-matrix.md) — decompose eligibility
- [operator-stage-checklists.md](./operator-stage-checklists.md)
- [gui-surface-map.md](./gui-surface-map.md)
