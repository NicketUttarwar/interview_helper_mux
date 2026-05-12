---
id: execution-full-localized-dub
tier: high
status: idea
depends_on: [execution-readme, execution-s2s-trained]
---

# Full localized dub: source-language interview → translated, voice-cloned master

**Archetype K** on the [complexity ladder](complexity-ladder-end-to-end-ideas.md): same **information** as the original recording, but the **delivered episode** is a **new language** (example below uses **Marathi → English**; the pattern generalizes to any high-quality STT/MT pair).

This is **hard** because you stack **transcription accuracy**, **translation fidelity**, **duration alignment**, **synthetic voice risk**, and the **normal mux/master** problems on one spine. Treat it as **H-level ops** plus **G-level generative audio** gates, not “just run Google Translate.”

## Outcome

- **Playable master** in the target language (podcast-shaped loudness, chapters optional).
- **Reproducible manifest**: immutable source audio, Marathi (or source) transcript revision, English (or target) script revision, per-span TTS/clone outputs with model IDs, and the same [timeline / EDL](../pipeline/assembly-and-mux/timeline-and-edl.md) shape as other orchestrations—only **clip bodies** are often **fully synthetic**.

## Assumed component set (translation + voice)

You already have (or will add) **small, testable services**, not one monolith:

| Component | Role |
|-----------|------|
| **Source STT** | High-quality ASR in the **source** language (e.g. Marathi-capable model or provider adapter); [word-level timestamps](../pipeline/transcription/word-level-timestamps.md) where possible. |
| **Segmentation** | Stable spans aligned to **breaths / pauses / topics** so translation and dubbing do not split mid-thought ([silence / pause splits](../pipeline/segmentation/silence-and-pause-splits.md), [topic boundaries](../pipeline/segmentation/topic-embedding-boundaries.md) when needed). |
| **MT primary** | Machine translation **source → target** text per segment (or sentence batch inside a segment). |
| **MT secondary / checker** | Independent engine or **back-translation** target → source for **semantic drift** flags ([automation-and-prompt-orchestration.md](automation-and-prompt-orchestration.md) patterns apply). |
| **Glossary / entities** | Locked list for names, places, product terms; **human confirm** on first hit per episode ([human review](../pipeline/human-review-ui/README.md)). |
| **Literal / policy guard** | Rules for numbers, dates, currency, “do not translate X,” profanity policy, and **low-confidence** MT spans → forced review or **hold original clip** (rare) with a VO disclaimer—policy choice, not silent failure. |
| **Length planner** | Target language is often **longer or shorter**; plans **compression** (tighter copy), **micro-extensions** (allowed filler), or **time-stretch** only where the mux graph allows ([speech-to-speech-and-trained-remix-models.md](speech-to-speech-and-trained-remix-models.md) “duration drift” applies to TTS too). |
| **Voice identity** | **Voice cloning / instant voice** (e.g. **ElevenLabs** or equivalent) **per speaker** with **licensed** voice profile; optional **separate clone** per speaker if diarization is solid ([diarization](../pipeline/transcription/diarization.md)). |
| **TTS render** | Emits **new audio assets** per segment with prosody controls; each file is a **new artifact** in the [snippet store](../pipeline/snippet-store/README.md) with [provenance](../pipeline/snippet-store/provenance-retranscribe.md). |

Everything after TTS re-enters the **normal backbone**: [audio editing](../pipeline/audio-editing/README.md), [assembly / mux](../pipeline/assembly-and-mux/README.md), [mastering / export](../pipeline/mastering-and-export/README.md).

## Guard rails (buffer for errors)

Order matters: **cheap checks before expensive audio**.

1. **STT confidence + OOV spikes** → re-run STT with alternate model or human fix **before** MT spends credibility.
2. **MT agreement** → primary vs secondary disagree → flag segment; optional **third** tiny model for tie-break **text-only**.
3. **Back-translation** → paraphrase detector; fails if restored meaning diverges from source clause (glossary wins on entities).
4. **Named-entity lock** → glossary hits must appear **verbatim** in target; numbers normalized with locale rules.
5. **Read-aloud sanity** → LLM or template check: “does this sentence contradict the previous segment?” (narrative only; not a fact oracle).
6. **First synthetic listen** → [high-risk-first-use-gating.md](high-risk-first-use-gating.md): block publish until **spot-listen** passes for **each new voice profile** and **each episode’s** first full render.

Synthetic segments get **new `segment_id` suffixes** (never overwrite source-linked IDs) so A/B and legal rollback stay trivial.

## How it composes with the rest of the system

- **Scoring / selection** still picks **which** parts of the interview matter; you are not forced to dub dead air or retakes. [Diversity](../pipeline/scoring-and-selection/diversity-constraints.md) and [LLM rank](../pipeline/scoring-and-selection/llm-assisted-ranking.md) apply to **which spans enter the dub graph**.
- **Nonlinear (D)** is possible but brutal: translated callbacks must **still** refer to the same facts; add explicit **script graph** review.
- **Room / breath polish (F)** is **high value** after TTS: synthetic stems often need **room tone** and **crossfade** love to sit next to **retained** non-speech beds (music licensed separately).
- **I–J** (spectrogram / wav2vec) can still annotate **where not to cut** if you **mix** a little original atmos under dubbed speech—optional, not required for K.

## Stress cases (what breaks naive pipelines)

- **Code-switch** inside Marathi (English tech terms): wrong language tag → wrong voice or wrong MT direction; reuse **E** discipline ([orchestration-component-map.md](orchestration-component-map.md) § E).
- **Prosody mismatch** after aggressive trim: translated line **too long** for the video/audio slot → visible **rush** or **dead air**; length planner + mux edge costs must cooperate.
- **Voice clone misuse** → legal / ethical failure; keep **consent artifacts** beside the voice profile ID in the manifest.
- **Hallucinated** content in MT or in **TTS** “improvisation” if the vendor model is chatty—**lock** to approved script bytes for release builds.

## Library stance

No new **top-level pipeline folder** is required if **translation**, **glossary**, and **TTS/clone adapters** are documented as **orchestrated tools** with clear I/O and versioning (same pattern as **gated** S2S in [speech-to-speech-and-trained-remix-models.md](speech-to-speech-and-trained-remix-models.md)). If three+ concrete providers force it, split a dedicated **translation** leaf under `pipeline/` later—until then, keep contracts in this execution note + [STT adapters](../pipeline/transcription/stt-provider-adapters.md).

## Open decisions

- **Lip-sync / video** out of scope for audio-only mux—if video ships later, K becomes a **separate** timeline with forced duration solvers.
- Whether **one** English voice is acceptable for all guests (cheap) vs **per-speaker clone** (expensive, higher gate).
- Default on **untranslatable humor**: footnote VO, subtitle-style chapter note, or **drop** segment from the localized preset.

## Links

- [complexity-ladder-end-to-end-ideas.md](complexity-ladder-end-to-end-ideas.md)
- [orchestration-component-map.md](orchestration-component-map.md)
- [high-risk-first-use-gating.md](high-risk-first-use-gating.md)
- [../pipeline/snippet-store/provenance-retranscribe.md](../pipeline/snippet-store/provenance-retranscribe.md)
- [../pipeline/mastering-and-export/final-loudness-limiting.md](../pipeline/mastering-and-export/final-loudness-limiting.md)
