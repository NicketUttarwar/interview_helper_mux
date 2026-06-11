# Transcript quality rubric

How upstream STT quality flows into LLM stages. Operators fix text at **G0**; fillers are cataloged at **G0.5**. Downstream prompts must treat both signals as first-class constraints — not optional warnings.

**Code:** `transcript_quality_for_ctx()` in `src/interview_mux/context_volley.py`  
**G0 spec:** [transcript-review.md](../../pipeline/transcription/transcript-review.md)  
**G0.5 spec:** [disfluency-extract.md](../../pipeline/transcription/disfluency-extract.md)

---

## G0 — flagged chunks

After `transcript_review_build`, low-confidence regions are ranked for operator review. Chunks with `needs_review: true` or mean word confidence below the queue threshold (default **0.85**) become `transcript_quality.flagged_chunks` in stage input.

### Shape (volley injection)

```json
{
  "transcript_quality": {
    "low_confidence_threshold": 0.85,
    "flagged_chunks": [
      {
        "chunk_id": "chunk_014",
        "start_ms": 312000,
        "end_ms": 318400,
        "confidence": 0.71,
        "text": "… clipped excerpt ≤120 chars …"
      }
    ],
    "note": "Lower confidence on flagged regions — avoid inventing facts; flag uncertainty in artifacts."
  }
}
```

Cap: **25** flagged chunks per volley (weakest first). Stages receiving this block: `content_context`, `boundary_detection`, `segment_classification`, `content_brief_reanchor`.

### Rubric — what LLM stages must do

| Severity | Condition | Required behavior |
|----------|-----------|-------------------|
| **Block** | Claim or entity appears only inside flagged text | Do not assert as fact; `confidence ≤ 0.5` or omit |
| **Downgrade** | Topic spans flagged + clean regions | `confidence` proportional to clean coverage; note in `reasoning_summary` |
| **Boundary caution** | Flagged chunk mid-utterance | Do not split boundary inside chunk unless recovering obvious STT fragmentation |
| **Reanchor** | Pass-1 brief topic anchored only to flagged segments | `content_brief_reanchor` must not increase confidence without G0 resolution |

### Good pattern

```json
{
  "name": "EU expansion timeline",
  "segment_ids": ["seg_022"],
  "confidence": 0.45,
  "notes": "seg_022 partially overlaps flagged chunk_014 (conf 0.71); treat date as uncertain until G0 cleared"
}
```

### Bad pattern

```json
{
  "name": "Series C closed Q3 2024",
  "segment_ids": ["seg_022"],
  "confidence": 0.92
}
```

When `seg_022` falls entirely inside a flagged chunk and G0 is not complete — violates transcript-only rule.

### Operator ↔ LLM contract

| G0 state | Pipeline | LLM behavior |
|----------|----------|--------------|
| Pending | `speaker_roles` blocked by preflight | No analysis LLM calls |
| Complete, flagged chunks remain | Volley includes `transcript_quality` | Uncertainty required in artifacts |
| Complete, corrections applied | Flagged list shrinks or empties | Normal confidence rules |

Preflight enforces G0 before `speaker_roles` and `content_context` (`llm_preflight.py` → `check_transcript_review_pending`).

---

## G0.5 — disfluency catalog

`disfluency_extract` writes `transcript/disfluencies.json`. After operator **disfluency_review**, confirmed events are summarized as `disfluency_catalog` in analysis volley (see [analysis-preamble.system.txt](./analysis-preamble.system.txt)).

### Shape (stage input)

```json
{
  "disfluency_catalog": {
    "confirmed_count": 42,
    "by_segment": {
      "seg_008": { "um": 3, "uh": 1 },
      "seg_015": { "like": 2 }
    },
    "restore_policy": "flow1_optional"
  }
}
```

### Rubric — catalog usage by stage

| Stage | Use catalog | Rule |
|-------|-------------|------|
| `content_context` | Optional | Do not treat fillers as semantic content; ignore in thesis/claims |
| `boundary_detection` | Yes | Pauses with only fillers may merge with adjacent speech |
| `segment_classification` | Yes | High filler density ≠ `low_value`; tag `disfluency_heavy` if helpful |
| `missing_framing` | No | Fillers don't create comprehension gaps |
| `sound_design_palettes` | Yes | Dense filler segments → sparser beds (SAP density hint) |
| `full_master_ranking` | Optional | Don't penalize authentic speech disfluency unless operator requests polish |
| `mix_flow1` / restore | Yes | [disfluency-restore.md](../../pipeline/assembly_and_mux/disfluency-restore.md) splices confirmed fillers post-ranking |

### Good pattern — boundary merge

Two segments separated by 400 ms gap containing only `um` + breath → single boundary at outer edges; rationale cites `disfluency_catalog.by_segment`.

### Bad pattern — filler as claim

`key_claims[].text: "Um, we raised Series B"` — filler must not become claim text.

### Bad pattern — false precision

Inventing `disfluency_catalog` counts not present in stage input.

---

## Combined quality score (informal)

Stages may reason about an informal **transcript trust band**:

| Band | G0 flagged % | G0.5 density | Guidance |
|------|--------------|--------------|----------|
| **A** | <5% duration flagged | Low | Normal confidence |
| **B** | 5–15% flagged | Medium | Downgrade isolated claims |
| **C** | >15% flagged or G0 skipped items | High | Prefer `needs` / investigations over bold artifacts |

No single numeric field is emitted today; bands are derived from `transcript_quality` + operator sign-off metadata.

---

## Investigations triggered by quality

| kind | Trigger | Suggested rerun |
|------|---------|-----------------|
| `segment_ambiguity` | Boundary inside flagged chunk | `boundary_detection` |
| `theme_unmapped` | Topic only in flagged regions | G0 first, then `content_brief_reanchor` |
| `gap_unresolved` | Comprehension risk in noisy region | G0 + `missing_framing` |

---

## Examples in prompt packs

- [content-context.examples.md](./examples/content-context.examples.md) — bad: ignores `transcript_quality`
- [boundary-detection.examples.md](./examples/boundary-detection.examples.md) — fragmentation recovery
- [content-brief-reanchor.examples.md](./examples/content-brief-reanchor.examples.md) — confidence after segmentation

**Related:** [interview-scenario-atlas.md](./interview-scenario-atlas.md) (noisy_room) · [stage-quality-scorecard.md](../../cross-cutting/stage-quality-scorecard.md)
