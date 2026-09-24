# Long interviews — context caps and chunking policy

When a recording is **long or dense**, LLM stages may hit **token / character caps** defined in `config/app.defaults.json` → `analysis.context`.

This document is the **policy** for operators and implementers: what to expect, what breaks, and how to recover **without** silently losing fidelity.

**v2 proactive batching (shipped):** when transcript length exceeds `proactive_decompose_chars` (default 72k), `content_context` and `talking_points_compose` run **contiguous overlapping shards** and merge artifacts (`transcript_shards.py`). `missing_framing` and `gap_framing_compose` batch by segment IDs when count exceeds `proactive_decompose_gap_segments` (default 20), with per-segment text from `segment_text_max_chars` (default 400). Sparse `missing_framing` shard outputs get a coverage pass plus deterministic low-severity fills. `full_master_ranking` receives a **compacted** `gap_report` (placement contract only — no full VO copy) so long interviews stay under model context. This is **deterministic classification-style batching** — not the deleted LLM-arbiter shard/collate product path.

**H-ORC-03 coherence (30m+):** when interview duration ≥ `coherence.min_duration_ms` (default 30 minutes), the coherence layer activates — drift/contradiction/callback risks are scored and padded into coverage/arc volleys. See [coherence-orc03.md](../cross-cutting/coherence-orc03.md).

---

## Caps (authoritative keys)

| Key | Role | If too low / mis-set |
|-----|------|----------------------|
| `transcript_excerpt_chars` | Legacy (unused in v2 builders) | — |
| `transcript_full_chars` | Legacy alias for older sample caps | Prefer `proactive_decompose_chars` |
| `speaker_roles_sample_chars` | Total budget for opening/middle/closing `transcript_samples` | Role inversion on long interviews |
| `max_transcript_shards` | Max shard calls per transcript | Tail of long interviews still blind |
| `proactive_decompose_chars` | Auto multi-pass threshold for `content_context` / `talking_points_compose` | Very long interviews hit single-pass context limits |
| `transcript_shard_overlap_ratio` | Overlap between contiguous transcript shards (default 0.08) | Lost boundary topics or duplicate spend |
| `segment_text_max_chars` | Per-segment text in compact manifests (wired) | Gap pass blind to long answers |
| `max_segments_in_context` | Documented ceiling for some stages | Tail segments never scored in that call |
| `max_segments_in_gap_pass` | Soft gap window ceiling | Prefer `proactive_decompose_gap_segments` |
| `proactive_decompose_gap_segments` | `missing_framing` / `gap_framing_compose` batch size (default 40) | Incomplete gap evals, oversized compose volleys, or context_length_exceeded |
| `max_gap_evaluations` | Rows in missing-framing batch | Some segments not evaluated until re-run |
| `max_stage_data_chars` | Total JSON payload to model | Envelope truncated / validation odd |
| `interviewer_sample_lines` | Lines fed into transitions stage | Weaker bridge tone match |

**Guard:** Raising caps increases **cost and latency**; lowering caps increases **blind spots**. Document any production change in release notes.

---

## Full-tape coverage stages (shipped)

| Stage | Shard strategy |
|-------|----------------|
| `content_context` | Contiguous transcript char/word windows when over `proactive_decompose_chars`; merge brief fields |
| `talking_points_compose` | Same; merge talking points by title (prefer higher importance) |
| `missing_framing` | Segment-ID batches of ≤`proactive_decompose_gap_segments` with fuller `segment_text_max_chars` excerpts |
| `segment_classification` | Segment-ID batches (`per_segment_shard_max` / `proactive_decompose_segments`) |
| `boundary_detection` | Full text + turns via `compact_transcript_for_boundaries` (words dropped only when huge) |

---

## VO conversation partner

Gap compose/recompose receive `prior_native_contexts`, `target_native_contexts`, `vo_missions`, and compact `talking_points`. Deterministic lint (`analysis.gap_framing.vo_value_gate`) requires rationale, blocks interruptive openers after impact, and fails high VO↔next-clip token overlap (north star: no VO that only restates the next clip).

---

## Operator recovery

1. Re-run from the truncated stage (`--from-stage content_context` / `talking_points_compose` / `missing_framing`).
2. If a single shard still fails context limits, lower `proactive_decompose_chars` or `proactive_decompose_gap_segments` so more, smaller batches run.
3. Do **not** silently accept truncated LLM markers — truncation integrity fail-closes.

See also: [truncation-integrity.md](../cross-cutting/truncation-integrity.md) · [config-keys.md](../cross-cutting/config-keys.md).
