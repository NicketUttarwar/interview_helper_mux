# Value map — Flow 1 sound + mix (sonic storytelling)

## 1. Intent

Use sound design to **underline ideas** and emotional truth—never decoration that obscures speech—so the mastered episode feels intentional to the listener.

## 2. Signals used today (context only)

`podcast_sfx_brief`, MMAudio generation, v1 mux limits per [sound-design.md](../../../cross-cutting/sound-design.md) and [podcast-quality-roadmap.md](../../../cross-cutting/podcast-quality-roadmap.md).

**Optional (tooling):** When `value_analysis.enabled`, `tools/extract_value_features.py` may write `understanding/value_features.json` (transcript/audio proxies) to inform spikes — not consumed by the default pipeline.

## 3. Value hypotheses

| Hypothesis | One-line thesis |
|------------|-----------------|
| H-F1S-01 | **CLAP-style retrieval** matches stinger *meaning* to narrative beat, not only topic keywords. |
| H-F1S-02 | **Laughter / applause** windows constrain sting placement to protect intelligibility. |
| H-F1S-03 | **SSL tension curve** suggests bed entry/exit for sonic storytelling. |

## 4. Listener / idea / creator

| ID | LEX | COM | CRE |
|----|-----|-----|-----|
| H-F1S-01 | ● | ● | ● |
| H-F1S-02 | ● | ○ | ● |
| H-F1S-03 | ● | ○ | ○ |

## 5. Moonshot tier

| ID | Tier |
|----|------|
| H-F1S-01 | T1 |
| H-F1S-02 | T0 |
| H-F1S-03 | T2 |

## 6. Spike artifacts

- A/B same narrative with sting placement informed vs uninformed by events.
- Listener LEX-B (sonic trust) + COM-A after clip.
- Optional prep: with `value_analysis.enabled`, run `tools/extract_value_features.py` on the run to populate `understanding/value_features.json` (transcript/audio proxies) before scoring hypotheses in [phase3-spike-framework.md](../phase3-spike-framework.md); the default mux path does not read this file.

## 7. Spike winner (fixture sprint)

**Promote:** `sdp_craft_path` (SDP + OpenAI craft + MMAudio) — [spike-results § flow1 sound](../spike-results-and-winners.md#flow1-sound-and-mix). Fixture: `tests/fixtures/value_analysis/spike_flow1_sound.json`. Metric: [value-metrics-library §1.4 — Clip A/B](../value-metrics-library.md#4-clip-ab-protocol) (LEX-B sonic trust).

## Related

- [future-proofing.md](../../../roadmap/future-proofing.md)
- [moonshot-model-families.md](../moonshot-model-families.md) — Families 4–5
- [spike-results-and-winners.md](../spike-results-and-winners.md#flow1-sound-and-mix)
