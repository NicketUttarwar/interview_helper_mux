# Long-run coherence (H-ORC-03)

**Artifact:** `understanding/coherence_report.json`  
**Memory:** `analysis_state.coherence_risks[]`  
**Hypothesis:** H-ORC-03 — **Promote** (shipped)

## Problem

Interviews longer than ~30 minutes accumulate narrative risks that single-pass LLM stages miss: topic drift without acoustic confirmation, contradictory claims across the timeline, and topics that are introduced early but never revisited. H-ORC-03 scores these risks deterministically on top of the [interview spine](./interview-spine.md) and wires them into investigations, volleys, and operator review.

## Activation gate

Coherence detection runs only when **all** of the following hold:

1. `coherence.enabled: true`
2. `value_analysis.orc03_enabled: true` (master `value_analysis.enabled` must also be on)
3. Interview duration ≥ `coherence.min_duration_ms` (**1_800_000 ms = 30 minutes**)

Below the gate: no report risks, no investigations, no volley slices. The spine may still build; naive speaker-turn `topic_shift_hint` stubs are suppressed when `coherence.replace_stub_topic_shift_hints: true`.

**Rationale:** Multi-topic long-form interviews enter volley truncation territory around 30 minutes; composite drift signals become actionable without spamming short clips.

## Signals

| Signal | Module | Output |
|--------|--------|--------|
| Acoustic novelty | `novelty.py` | Adjacent-window CLAP cosine delta; RMS/prosody fallback |
| Theme alignment | `theme_alignment.py` | Window text vs `content_brief.topics[]` |
| Topic drift | composite | `drift_score` + novelty gate → `topic_drift` risk |
| Claim contradiction | `claim_contradiction.py` | Later windows vs `key_claims` + `contradicts` relationships |
| Missing callback | `missing_callback.py` | `returns_to` / second-half coverage scan |

Composite **topic_drift** requires:

```
drift_score >= topic_drift_threshold
AND (NOT require_acoustic_novelty OR novelty_score >= novelty_min_delta)
```

## Investigation kinds

| Kind | Default rerun | Blocking |
|------|---------------|----------|
| `topic_drift` | `content_brief_reanchor` | no |
| `claim_contradiction` | `content_brief_reanchor` | yes when `blocking_claim_contradiction` |
| `missing_callback` | `topic_coverage_audit` | no |

Capped by `coherence.max_investigations_per_run`; deduped by `(kind, stage, window_id|risk_id)`.

## Hook phases

| Phase | Trigger | Passes |
|-------|---------|--------|
| `post_content_context` | end of `content_context` | theme alignment only |
| `post_reanchor` | end of `content_brief_reanchor` | full report write |
| `post_coverage` | end of `topic_coverage_audit` | reconcile with coverage audit |

## Volley consumers

`coherence_summary` is attached (via `compact_for_volley`) to:

- `topic_coverage_audit`
- `narrative_arc_plan`
- `content_brief_reanchor`
- `missing_framing`
- `REMOVED_podcast_show_description` (blocking contradictions only)

See [`analysis.context.*`](./config-keys.md#analysiscontext) for per-stage caps.

## Relationship to other hypotheses

- **H-ORC-01 (spine):** windows, embeddings, boundary fusion — required input
- **H-ORC-02 (trust dip):** orthogonal; acoustic anomaly investigations remain in value analysis

## Non-goals

- Per-run Llama/MLX fine-tune on audio + transcript
- Default SSL/Wav2Vec (`interview_spine.ssl_enabled` stays false)
- Replacing the local MLX STT backend

## Promotion criteria (Park → Promote)

1. 30m fixture `tests/fixtures/runs/coherence_30m_planted_drift/` detects planted contradiction, missing callback, and ignores decoy speaker turn
2. Unit + integration tests pass (`tests/test_coherence_*.py`)
3. Spike doc updated; operator GUI panel on stage detail

## Related

- [interview-spine.md](./interview-spine.md)
- [analysis-memory.md](./analysis-memory.md)
- [json-schemas/coherence_report.schema.json](./json-schemas/coherence_report.schema.json)
