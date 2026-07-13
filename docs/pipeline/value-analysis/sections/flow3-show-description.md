# Value map — Flow 3 show description

## 1. Intent

Turn shared interview understanding into **distribution copy** that increases listen-through — optimized for hook, stakes, and audience fit, not for audio editing.

## 2. Signals used today (context only)

LLM `REMOVED_podcast_show_description` with flagship tier; rich user/assistant volley per [context-padding.md](../../../cross-cutting/context-padding.md). Prompt: [podcast-show-description.system.txt](../../../prompts/publishing/podcast-show-description.system.txt).

## 3. Value hypotheses

| Hypothesis | One-line thesis |
|------------|-----------------|
| H-F3-01 | **Evidence-anchored hype** (claims tied to `segment_ids`) reduces embarrassing show notes vs generic LLM blurbs. |
| H-F3-02 | **Third-person editorial voice** performs better on podcast directories than first-person host copy generated from the same transcript. |
| H-F3-03 | **Flagship + full volley** beats economy one-shot on click-through proxy (A/B on platform analytics). |

## 4. Listener / idea / creator

| ID | LEX | COM | CRE |
|----|-----|-----|-----|
| H-F3-01 | ○ | ● | ● |
| H-F3-02 | ● | ● | ○ |
| H-F3-03 | ● | ○ | ● |

## 5. Moonshot tier

| ID | Tier |
|----|------|
| H-F3-01 | T0 |
| H-F3-02 | T0 |
| H-F3-03 | T0 |

## 6. Spike artifacts

- Blind ranking: operator picks best blurb among flagship volley vs economy one-shot.
- Factual error count vs `content_brief.key_claims` (human audit).

## 7. Spike winner (fixture sprint)

**Promote:** H-F3-01 evidence-anchored show notes — [spike-results § flow3](../spike-results-and-winners.md#flow3-show-description). Fixture: `tests/fixtures/value_analysis/spike_flow3_show_description.json`. Metric: [value-metrics-library §1.3 — Operator timed task](../value-metrics-library.md#13-operator-timed-task-cre-b) (CRE-C explainability vs `key_claims`).

## Related

- [future-proofing.md](../../../roadmap/future-proofing.md)
- [publishing/README.md](../../publishing/README.md)
- [spike-results-and-winners.md](../spike-results-and-winners.md#flow3-show-description)
