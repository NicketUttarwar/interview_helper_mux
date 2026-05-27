# Value map — Flow 2 highlights

## 1. Intent

Select a **small set of moments** that hook strangers fast, carry the thesis, and feel distinct from each other—optimized for shareable listening.

## 2. Signals used today (context only)

LLM `highlight_selection` with salience/clarity/emotion/quotability schema per [highlight-selection.system.txt](../../../prompts/selection/highlight-selection.system.txt) and artifact schemas under `docs/cross-cutting/json-schemas/`.

## 3. Value hypotheses

| Hypothesis | One-line thesis |
|------------|-----------------|
| H-F2-01 | **Text-query audio retrieval** finds clips text-only search misses (“sounds like a breakthrough”). |
| H-F2-02 | **Paralinguistic peaks × quotability** fusion improves hook strength. |
| H-F2-03 | **First-3s acoustic hook score** + diversity constraint reduces flat montages. |

## 4. Listener / idea / creator

| ID | LEX | COM | CRE |
|----|-----|-----|-----|
| H-F2-01 | ● | ● | ● |
| H-F2-02 | ● | ○ | ● |
| H-F2-03 | ● | ○ | ● |

## 5. Moonshot tier

| ID | Tier |
|----|------|
| H-F2-01 | T1 |
| H-F2-02 | T0 |
| H-F2-03 | T0 |

## 6. Spike artifacts

- Hook strength scorecard (first 3s); forced-choice vs alternate picks.
- Diversity metric across selected clips (topic + acoustic embedding spread).

## Related

- [future-proofing.md](../../../roadmap/future-proofing.md)
- [moonshot-model-families.md](../moonshot-model-families.md) — Families 4–5
