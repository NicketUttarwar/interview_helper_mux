---
id: execution-complexity-ladder
tier: both
status: spec
depends_on: [execution-readme]
---

# Complexity ladder: complete, simple, lovable ideas

Each row is a **full vertical slice** you could ship as a preset: same raw interview in; **polished episode** out. They differ by **moving parts**, **model risk**, and **how clever the mux is**.

**Conformance and stress-testing** (minimum components, deliberate skips, library gaps): [orchestration-component-map.md](orchestration-component-map.md). This page stays the **compact pitch**; the map is where each orchestration is **challenged** against the component library. **K** (full localized dub) is expanded in [full-localized-dub-orchestration.md](full-localized-dub-orchestration.md).

| # | Name | What you love about it | Automation | Human touch |
|---|------|------------------------|------------|-------------|
| A | **Highlight reel** | One STT pass, top-N silence-based chunks, crossfades, loudness—done. | Very high | Rare: “ban this clip.” |
| B | **Chapter podcast** | Linear story with auto chapter titles from headings in transcript. | High | Optional reorder in UI. |
| C | **Director’s cut (timeboxed)** | Target length (e.g. 28 min): solver picks segments + bridges under diversity rules. | High | Approve budget + one pass on order. |
| D | **Nonlinear story** | Flashbacks, “setup → payoff” reorder; needs graph EDL ([difficult-segment-combinations.md](difficult-segment-combinations.md)). | Medium–high | Approve graph once per template. |
| E | **Room and breath polish** | Denoise, de-reverb, gentle music bed, adaptive room-tone bridges. | Medium | Gate first use of heavy DSP stack ([high-risk-first-use-gating.md](high-risk-first-use-gating.md)). |
| F | **Bilingual / code-switch** | Detect spans; per-span STT locale; assemble with language-aware transitions. | Medium | Confirm language tags when low confidence. |
| G | **S2S “same words, cleaner performance”** | Keep transcript alignment; neural S2S re-renders selected spans for clarity. | Low–medium | Strong gate + spot-listen; see [speech-to-speech-and-trained-remix-models.md](speech-to-speech-and-trained-remix-models.md). |
| H | **Custom ranker + custom acoustic** | Fine-tuned LLM or LoRA for *your* interview style scoring; optional per-speaker S2S or VC. | Low (ops heavy) | Approve training data + first deploy of each new model class. |
| I | **Spectrogram hazard overlay (YOLO11)** | Mel/STFT “vision” finds overlap and non-speech hazards; **only** neighborhoods that stress mux get labeled—feeds edge costs and “do not cut here” masks. | Medium (GPU) | Confirm class taxonomy + first custom-weights deploy; spot-check false positives on new mics. |
| J | **Wav2Vec-assisted rank & continuity** | SSL embeddings dedupe near-identical clips, score **acoustic** continuity across reorder, optional code-switch hints next to text—pairs with I when YOLO fires often. | Medium | Approve when embedding clusters disagree with story labels; keep factual policy in transcript/scoring, not vectors alone. |
| K | **Full localized dub** | Source-language interview (e.g. **Marathi**) → scored segments → **MT stack + guard rails** → **voice clone / TTS** (e.g. ElevenLabs) → new stems → same mux/master path → **polished episode in another language**. | Low until gates pass (many API calls) | Strong gates: glossary/entities, MT disagreement, first-episode spot-listen per voice; legal consent on clones. See [full-localized-dub-orchestration.md](full-localized-dub-orchestration.md). |

**Lovable rule:** each tier should produce **one playable file** and a **manifest you can reproduce**—even if H takes a weekend of GPU time. **I–J** should still emit the same manifest shape with **extra annotations** ([spectrogram-yolo-wav2vec-orchestration.md](spectrogram-yolo-wav2vec-orchestration.md)). **K** adds **synthetic speech artifacts** per segment while keeping that manifest discipline ([full-localized-dub-orchestration.md](full-localized-dub-orchestration.md)).

## Open decisions

- Which single archetype becomes the default “**Auto episode**” button.

## Links

- [orchestration-component-map.md](orchestration-component-map.md)
- [spectrogram-yolo-wav2vec-orchestration.md](spectrogram-yolo-wav2vec-orchestration.md)
- [../pipeline/assembly-and-mux/dynamic-assembly-graph.md](../pipeline/assembly-and-mux/dynamic-assembly-graph.md)
- [automation-and-prompt-orchestration.md](automation-and-prompt-orchestration.md)
