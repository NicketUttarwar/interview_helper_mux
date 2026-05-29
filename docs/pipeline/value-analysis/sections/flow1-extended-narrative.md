# Value map — Flow 1 extended narrative (coverage + arc + ranking + transitions)

## 1. Intent

Shape a **full-episode narrative** so every important idea has a place, order serves comprehension, and bridges feel human—maximizing what a dedicated listener carries away.

## 2. Signals used today (context only)

LLM stages: topic coverage audit, narrative arc plan, full master ranking, transitions per [pipeline.md](../../../pipeline.md).

## 3. Value hypotheses

| Hypothesis | One-line thesis |
|------------|-----------------|
| H-F1N-01 | **Lexical graph + audio pacing curve** fusion suggests ordering hints humans miss. |
| H-F1N-02 | Weight coverage by **acoustic emphasis** so “quietly said but vital” claims surface. |
| H-F1N-03 | **Breath / pause before topic shifts** informs transition line placement and length. |

## 4. Listener / idea / creator

| ID | LEX | COM | CRE |
|----|-----|-----|-----|
| H-F1N-01 | ● | ● | ● |
| H-F1N-02 | ○ | ● | ● |
| H-F1N-03 | ● | ○ | ● |

## 5. Moonshot tier

| ID | Tier |
|----|------|
| H-F1N-01 | T1 |
| H-F1N-02 | T1 |
| H-F1N-03 | T0 |

## 6. Spike artifacts

- Blind chapter order A/B; arc coherence scorecard.
- Optional: pacing curve PNG + ranked segment list for operator workshop.

## 7. Spike winner (fixture sprint)

**Promote:** H-F1N-02 acoustic emphasis coverage weighting — [spike-results § flow1 narrative](../spike-results-and-winners.md#flow1-extended-narrative). Fixture: `tests/fixtures/value_analysis/spike_flow1_extended_narrative.json`. Metric: [value-metrics-library §1.2 — Retell protocol](../value-metrics-library.md#12-retell-protocol-com-a-com-b) (blind chapter order).

## Related

- [future-proofing.md](../../../roadmap/future-proofing.md)
- [moonshot-model-families.md](../moonshot-model-families.md) — Families 1–2
- [spike-results-and-winners.md](../spike-results-and-winners.md#flow1-extended-narrative)
