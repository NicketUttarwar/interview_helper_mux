# Value map — shared segmentation (boundaries + classification)

## 1. Intent

Cut the timeline into **units of meaning** so ordering, gaps, and highlights respect how ideas actually unfold—**audio + text only** (no video).

## 2. Signals used today (context only)

LLM boundary and classification prompts; logic-tree pause heuristics (~700ms) as editorial guidance per [logic-tree.md](../../../logic-tree.md).

## 3. Value hypotheses

| Hypothesis | One-line thesis |
|------------|-----------------|
| H-SEG-01 | **Wav2Vec2-class states + transcript** suggest thought boundaries beyond pause rules. |
| H-SEG-02 | **Neural VAD pause ladder** replaces a single fixed pause threshold for split hints. |
| H-SEG-03 | **Acoustic novelty spikes** mark chapter hinges for long interviews. |

## 4. Listener / idea / creator

| ID | LEX | COM | CRE |
|----|-----|-----|-----|
| H-SEG-01 | ○ | ● | ● |
| H-SEG-02 | ● | ● | ● |
| H-SEG-03 | ● | ○ | ● |

## 5. Moonshot tier

| ID | Tier |
|----|------|
| H-SEG-01 | T0 |
| H-SEG-02 | T0 |
| H-SEG-03 | T1 |

## 6. Spike artifacts

- Human **boundary truth** marks on 5 hard segments; compare candidate splits.
- SectionFit dimension in [phase3-spike-framework.md](../phase3-spike-framework.md).

## 7. Spike winner (fixture sprint)

**Promoted (Partial → Promoted, Wave B 2026-06):** H-SEG-02 neural VAD pause ladder — shared constants in `interview_spine/constants.py`, SAP `pace_class` volley guidance, observability (`pause_ladder_oversplit_risk`). Fixture: `tests/fixtures/value_analysis/spike_shared_segmentation.json`. Metric: [value-metrics-library §1.1 — Listener Likert](../value-metrics-library.md#11-listener-likert-1-5) (boundary truth).

## Related

- [future-proofing.md](../../../roadmap/future-proofing.md)
- [segment-schema.md](../../../cross-cutting/segment-schema.md)
- [spike-results-and-winners.md](../spike-results-and-winners.md#shared-segmentation)
