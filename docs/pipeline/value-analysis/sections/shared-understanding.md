# Value map — shared understanding (speaker roles + content brief)

## 1. Intent

Infer **who** is speaking in role terms and **what the episode is about** at a level that supports narrative editing and gap detection—grounded in communicative truth, not only token patterns.

## 2. Signals used today (context only)

LLM stages `speaker_roles` and `content_context` consume transcript + memory envelope per [analysis-stage-matrix.md](../../../prompts/analysis-stage-matrix.md).

## 3. Value hypotheses

| Hypothesis | One-line thesis |
|------------|-----------------|
| H-UND-01 | **Prosodic clustering** yields “arc phase” labels that enrich `emotional_beats`. |
| H-UND-02 | **Turn overlap / interruption** metrics sharpen interviewer vs interviewee confidence. |
| H-UND-03 | **Acoustic validation** pass: text-derived beats vs waveform-supported tension. |

## 4. Listener / idea / creator

| ID | LEX | COM | CRE |
|----|-----|-----|-----|
| H-UND-01 | ● | ● | ○ |
| H-UND-02 | ○ | ● | ● |
| H-UND-03 | ● | ● | ○ |

## 5. Moonshot tier

| ID | Tier |
|----|------|
| H-UND-01 | T0 |
| H-UND-02 | T0 |
| H-UND-03 | T1 |

## 6. Spike artifacts

- Beat table: LLM-only vs LLM+acoustic; listener rates emotional truth.
- Role confusion matrix with/without overlap features.

## 7. Spike winner (fixture sprint)

**Promote:** H-UND-01/03 LLM beats + prosodic clustering validation — [spike-results § understanding](../spike-results-and-winners.md#shared-understanding). Fixture: `tests/fixtures/value_analysis/spike_shared_understanding.json`. Tool direction: [tools-not-in-repo § Lever A — prosody/affect](../tools-not-in-repo-landscape.md#lever-a--find-the-emotional-authentic-peak).

## Related

- [future-proofing.md](../../../roadmap/future-proofing.md)
- [moonshot-model-families.md](../moonshot-model-families.md) — Family 1
- [spike-results-and-winners.md](../spike-results-and-winners.md#shared-understanding)
