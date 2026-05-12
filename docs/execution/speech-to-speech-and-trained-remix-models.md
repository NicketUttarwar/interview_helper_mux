---
id: execution-s2s-trained
tier: high
status: idea
depends_on: [execution-readme]
---

# Speech-to-speech and trained remix models

Stretch goal: treat **audio segments as plastic**—not only cut and level, but **re-synthesize** speech while preserving **content** (and ideally speaker identity), optionally **per locale** or **per register**.

## Modes (increasing danger / power)

1. **Light denoise / declick:** still the same waveform class; usually not “training.”
2. **Voice conversion (same language):** timbre cleanup; watch neighbor mismatch ([difficult-segment-combinations.md](difficult-segment-combinations.md)).
3. **S2S “same text, new performance”:** conditioned on transcript + prosody hints; can fix mumbling if model is good—can also hallucinate words—**gate hard** ([high-risk-first-use-gating.md](high-risk-first-use-gating.md)).
4. **Per-language specialist heads:** e.g. Spanish vs English interview segments each routed through a locale-tuned acoustic stack; multilingual alignment layer stitches transcript tokens across code-switch boundaries.
5. **Custom LLM (or LoRA) for scoring and show script:** not audio, but steers **which** segments and **how** bridges are worded if you add micro voiceover or chapter copy.

## Training assumptions (personal lab)

- You may **fine-tune** on **your own transcripts and labels** (what was “good” vs “dull”) to personalize salience—not necessarily on raw waveform.
- Acoustic fine-tune needs **clean pairs** (noisy clip → desired clip), which is expensive to collect; often start with **off-the-shelf S2S/VC** before custom training.

## Practical sequencing

- Always keep **immutable source** + **aligned transcript revision**; S2S outputs become **new artifacts** with new `segment_id` suffixes so you can A/B in the mux.

## Open decisions

- Whether S2S is allowed to **change duration** (time-stretch vs generative pacing).

## Links

- [../pipeline/transcription/stt-provider-adapters.md](../pipeline/transcription/stt-provider-adapters.md)
- [../pipeline/snippet-store/provenance-retranscribe.md](../pipeline/snippet-store/provenance-retranscribe.md)
- [orchestration-component-map.md](orchestration-component-map.md)
- [complexity-ladder-end-to-end-ideas.md](complexity-ladder-end-to-end-ideas.md)
- [full-localized-dub-orchestration.md](full-localized-dub-orchestration.md) (archetype **K**: translate + TTS/clone → new-language master)
