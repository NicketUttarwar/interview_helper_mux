# Value map — shared ingest + transcribe

## 1. Intent

Turn raw capture into **time-aligned language** that preserves **who said what, when**—so every downstream stage can optimize for listener trust and idea clarity, not only literal word match.

## 2. Signals used today (context only)

Ingest normalizes audio; local MLX STT produces word-level transcript and diarization labels. Downstream expects `transcript/full.json`-shaped artifacts per [stt-and-diarization.md](../../transcription/stt-and-diarization.md).

## 3. Value hypotheses (not in repo as first-class)

| Hypothesis | One-line thesis |
|------------|-----------------|
| H-ING-01 | SSL sliding-window embeddings expose **idea-density curves** independent of word errors. |
| H-ING-02 | Multitrack **energy / coherence asymmetry** improves speaker-attribution hints before explicit roles. |
| H-ING-03 | **Quality trajectories** (MOS-like dims over time) flag listener-trust dips, not only low ASR confidence. |
| H-ING-04 | Alternate ASR + **forced alignment** tier improves micro-timing for emotional sync in clips (research path). |

## 4. Listener / idea / creator (primary axis each)

| ID | LEX | COM | CRE |
|----|-----|-----|-----|
| H-ING-01 | ● | ● | ○ |
| H-ING-02 | ○ | ● | ● |
| H-ING-03 | ● | ● | ○ |
| H-ING-04 | ● | ○ | ● |

● primary ○ secondary

## 5. Moonshot tier

| ID | Tier |
|----|------|
| H-ING-01 | T0 |
| H-ING-02 | T0 |
| H-ING-03 | T0 |
| H-ING-04 | T1 |

## 6. Spike artifacts

- JSON time series: SSL stats, quality dims, optional stem ratios per window.
- Listener Likert on **trust** windows flagged top vs bottom decile.
- Operator marks “mis-attributed speaker” segments with/without multitrack hints.

## 7. Spike winner (fixture sprint)

**Promote:** H-ING-03 NISQA-class quality trajectories — [spike-results § shared-ingest](../spike-results-and-winners.md#shared-ingest-transcribe). Fixture: `tests/fixtures/value_analysis/spike_shared_ingest_transcribe.json`. Metric: [value-metrics-library §2 — MOS-like predictor](../value-metrics-library.md#2-model-proxies-allowed-with-caveats).

**Park (T0 spike):** H-ING-01 SSL idea-density — [spike-results § H-ING-01 T0](../spike-results-and-winners.md#h-ing-01-t0-spike--ssl-idea-density). Command 8 gate not met (fixture sprint did not recommend SSL); no `torch`/`transformers` merged.

## Related

- [future-proofing.md](../../../roadmap/future-proofing.md)
- [moonshot-model-families.md](../moonshot-model-families.md) — Families 1–3, 6
- [spike-results-and-winners.md](../spike-results-and-winners.md#shared-ingest-transcribe)
