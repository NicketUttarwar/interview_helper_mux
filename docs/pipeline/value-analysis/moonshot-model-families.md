# Moonshot model families (audio-only)

**Not OpenAI Chat routing:** This doc covers **audio ML research families** (SSL, CLAP, etc.), not LLM stage tiers. For Chat Completions routing, arbiter, and tiers, see [llm-orchestration.md](../../cross-cutting/llm-orchestration.md).

**Scope:** single or multitrack **interview audio** + transcript text. **No video ingest.** No computer vision or object detection (including YOLO-class stacks).

Each family below follows the same structure in spikes:

1. **Hypothesis** — listener (LEX), idea (COM), or creator (CRE) value.
2. **Interview fit** — when it helps vs noise.
3. **Spike shape** — e.g. 30 min asset, 3 operators, blind A/B clips, retell protocol.

## Tiering

| Tier | Expectation |
|------|-------------|
| **T0** | Research spike without product rewrite. |
| **T1** | New artifacts + operator concepts. |
| **T2** | Heavy GPU / partnership; document “why worth a bet.” |

---

## Family 1 — Wav2Vec 2.0 / HuBERT / data2vec-audio (SSL speech)

| Field | Content |
|-------|---------|
| Directions | Frame-level hidden states; clustering “speech modes”; change-point detection on state statistics. |
| Value hooks | Latent **idea switches**; unsupervised “energy of argument”; boundary hints paired with transcript. |
| Interview fit | Strong when guests have long monologues; weak when heavy music under bed. |
| Spike shape | Export 20 Hz–level stats (mean \|h\|, delta) aligned to transcript; human mark “should have cut here”; correlate. |

## Family 2 — Large audio foundations (e.g. BEATs, AudioMAE-class)

| Field | Content |
|-------|---------|
| Directions | Patch- or frame-level embeddings from spectrogram or raw waveform. |
| Value hooks | **Arc energy** / novelty curves for chapter *feel* from **audio alone**. |
| Interview fit | Useful for tonal shifts (room, energy); may confound with mic moves. |
| Spike shape | Plot novelty vs time; operator marks chapter vibes; rank correlation. |

## Family 3 — Whisper-class + forced aligners (e.g. WhisperX pattern)

| Field | Content |
|-------|---------|
| Directions | ASR + phoneme / CTC alignment for word-level timing. |
| Value hooks | **Micro-edits** that preserve intelligibility; clip handles for emotional sync. |
| Interview fit | High when word timestamps drive mux; alignment quality vs AWS path is empirical. |
| Spike shape | Compare alignment jitter to listener preference on 10 micro-cuts. |

## Family 4 — CLAP / AudioCLIP / LAION-style (audio–text joint space)

| Field | Content |
|-------|---------|
| Directions | Embed audio windows and text queries; cosine similarity retrieval. |
| Value hooks | “Find the moment that **sounds** like a breakthrough” for Flow 2; semantic SFX bed search for Flow 1. |
| Interview fit | Transformative for highlight discovery; watch for query drift. |
| Spike shape | 5 fixed queries per episode; blind rank CLAP top-3 vs text-only top-3. |

## Family 5 — Audio event / paralinguistics (PANNs, YAMNet-class, laughter-specific)

| Field | Content |
|-------|---------|
| Directions | Weak-label or strong event detection; laughter, applause, cough, music bleed. |
| Value hooks | Authentic **emotion peaks**; protect speech from ill-timed stings; montage energy. |
| Interview fit | Podcast-native; calibrate false positives on room tone. |
| Spike shape | Precision/recall vs human clip tags on 15 min dense social audio. |

## Family 6 — Separation-informed analysis (e.g. Demucs stems as features)

| Field | Content |
|-------|---------|
| Directions | Vocals vs other stems as **features** (not only denoise): music bleed ratio, nonspeech energy. |
| Value hooks | Windows where **ideas get lost** under interference; prioritize for COM fixes. |
| Interview fit | Music in green room, bleed from intro track; less useful in dry studio. |
| Spike shape | Correlate bleed score with listener “hard to follow” Likert. |

## Family 7 — Generative audio understanding (large audio LMs, research line)

| Field | Content |
|-------|---------|
| Directions | Models that ingest audio context and emit structured labels, captions, or risk maps. |
| Value hooks | Zero-shot **tension curve** or “listener confusion” narrative for editor. |
| Interview fit | T2; validate hallucination rate on domain interviews before any product claim. |
| Spike shape | Frozen prompts; human rate usefulness vs harm on 10 clips. |

## Family 8 — Multimodal LLM (audio in + text prompt, still no video)

| Field | Content |
|-------|---------|
| Directions | Single model sees **waveform or mel** + operator question. |
| Value hooks | One-call **comprehension risk** or “what would confuse a first-time listener?” |
| Interview fit | T2; governance for data handling and cost. |
| Spike shape | Same rubric as Family 7 with stricter LEX-B / COM-A veto thresholds. |

---

## Minimum coverage

This annex documents **≥6 audio-only families** (here: eight). Extend with new rows (e.g. self-supervised **Silero VAD**-class, **NISQA**-class MOS) only if they pass the same hypothesis / fit / spike structure.
