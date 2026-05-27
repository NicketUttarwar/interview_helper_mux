# Long interviews — context caps and chunking policy

When a recording is **long or dense**, LLM stages may hit **token / character caps** defined in `config/app.defaults.json` → `analysis.context` and injected into the volley builder (`src/interview_mux/context_volley.py`). See [context-padding.md](../cross-cutting/context-padding.md) for what each stage receives.

This document is the **policy** for operators and implementers: what to expect, what breaks, and how to recover **without** silently losing fidelity.

**Target (spec only):** automatic **shard → collate** when the arbiter returns `decompose` for eligible stages (`missing_framing`, `segment_classification`, `boundary_detection`) — [llm-orchestration.md](../cross-cutting/llm-orchestration.md). **Not implemented in v1.**

---

## Caps (authoritative keys)

| Key | Role | If too low / mis-set |
|-----|------|----------------------|
| `transcript_excerpt_chars` | Snippet of transcript in some stages | Themes miss tail of interview |
| `transcript_full_chars` | Full transcript cap for early stages | Boundary/content passes truncated; wrong splits |
| `segment_text_max_chars` | Per-segment text in compact lists | Gap pass blind to long answers |
| `max_segments_in_context` | Max segments passed into some stages | Tail segments never scored in that call |
| `max_segments_in_gap_pass` | Gap evaluation window | Far-end gaps skipped in one pass |
| `max_gap_evaluations` | Rows in missing-framing batch | Some segments not evaluated until re-run |
| `max_stage_data_chars` | Total JSON payload to model | Envelope truncated / validation odd |
| `interviewer_sample_lines` | Lines fed into transitions stage | Weaker bridge tone match |

**Guard:** Raising caps increases **cost and latency**; lowering caps increases **blind spots**. Document any production change in release notes.

---

## Operator expectations (honest)

1. **v1:** No automatic shard/collate — only what `context_volley` strips and caps. Very long files may produce **partial coverage** in a single pass unless stages re-run with investigations.
2. **`investigation_queue.json` + `follow_up_investigations`** exist partly to surface “we need another pass on region X” — watch for `theme_unmapped`, `segment_ambiguity`, `gap_unresolved`.
3. **Profile verification** (`meta.operator_verified`) before Flow 1 extended reduces wasted extended passes on wrong themes — see [operator-gates.md](./operator-gates.md).

---

## Strategies (pick one or combine)

| Strategy | When | Rerun boundary | Tradeoff |
|----------|------|----------------|----------|
| **Raise caps in config** | You have model headroom + budget | None if still single pass | $$; may hit model max context |
| **Re-run from a mid pipeline stage** | After fixing G0 / manifest / profile | `--from-stage` per [idempotent-runs.md](./idempotent-runs.md) | Downstream invalidated |
| **Operator edits + targeted re-run** | A theme is wrong but transcript OK | e.g. `--from-stage segment_classification` | Fastest when root cause is classification |
| **Split into two executions** (manual) | Two logical “halves” of same recording | Two `run_id`s; merge in NLE later (advanced) | Editorial burden outside tool |
| **Shard/collate (target)** | Arbiter `decompose` on eligible stages | Same stage after collate | Spec: [llm-orchestration.md](../cross-cutting/llm-orchestration.md) — **not in v1 code** |

---

## Rerun boundaries (minimal invalidation)

| Goal | Typical `--from-stage` |
|------|-------------------------|
| Fix transcript only | `transcript_review` sign-off then `speaker_roles` or full `analysis` |
| Fix segmentation only | `boundary_detection` (invalidates downstream) |
| Fix gaps only | `missing_framing` after manifest stable |
| Fix Flow 1 order only | `full_master_ranking` (requires upstream Flow 1 artifacts) |

See [feedback-loops-and-reruns.md](./feedback-loops-and-reruns.md).

---

## Red flags (investigate)

- Coverage audit shows **systematic** `missing_coverage` for tail topics.
- `max_segments_in_context` hit in logs (if logged) or obvious omission of high-`end_ms` segments in stage input.
- Many `partial` envelopes with `reasoning_summary` citing “truncated input”.

**Action:** Increase relevant cap **or** split work / re-run with corrected upstream artifacts — do not only re-prompt.

---

## Related

- [context-padding.md](../cross-cutting/context-padding.md)
- [llm-stage-model-matrix.md](../cross-cutting/llm-stage-model-matrix.md) — decompose eligibility
- [operator-stage-checklists.md](./operator-stage-checklists.md)
- [gui-surface-map.md](./gui-surface-map.md)
