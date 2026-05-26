# Source separation, denoise, and enhancement — options

**Separation** tries to split a mixed recording into **sources** (e.g., speech vs music). **Denoise / enhancement** reduces noise while keeping speech intelligible. They overlap (some models do both).

This repo’s **product-level optional** path for **speech isolation** is documented under [audio_preclean](../audio_preclean/README.md) (ElevenLabs + RNNoise fallback). **Ingest** still expects a sane `normalized.wav` for STT regardless of chain.

---

## Goals matrix

| Goal | Typical approach | Local? | Cloud? |
|------|------------------|--------|--------|
| Hiss / stationary noise | Classical DSP + RNNoise-class models | Yes | Some APIs |
| Reverb reduction | Dereverb models (specialized) | Partial | Yes |
| Music in background | Demucs-style separation; or gate music-heavy segments | Yes (OSS) | Yes (APIs) |
| “Make VO pickup cleaner” | Light denoise / isolation on **short** clips | Yes | ElevenLabs isolation (spec’d) |
| Broadcast polish | Full mastering chain (EQ, comp, limiter) — see [mastering_and_export](../mastering_and_export/README.md) | DAW / ffmpeg | Cloud mastering services |

---

## Open-source / local stacks (representative)

| Tool / family | Role | Notes |
|---------------|------|--------|
| **RNNoise** (via `ffmpeg` `arnndn`) | Fast speech denoise | Good for steady noise; can sound metallic if over-applied — product warns in [audio_preclean](../audio_preclean/README.md). |
| **DeepFilterNet** (and successors) | ML denoise | Strong quality; GPU/CPU tradeoffs; check license per version. |
| **Demucs / Hybrid Demucs** | Music + vocals separation | Use **vocals stem** as STT input only if musical interference dominates; beware phasing and STT artifacts. |
| **speechbrain** recipes | Research / custom pipelines | Build cost |

**Guard:** Do **not** stack aggressive denoise + isolation + heavy EQ before STT without A/B — each stage can remove **phoneme** information.

---

## Commercial / cloud APIs

| Service type | Role |
|--------------|------|
| **ElevenLabs Audio Isolation** | Speech-focused background reduction (same vendor as SFX) — see [audio_preclean](../audio_preclean/README.md). |
| **Adobe / iZotope / Acon Digital** | Pro denoise / dereverb in DAW | Operator manual path; not wired in repo. |
| **Cloud “speech enhancement” APIs** | Various vendors package RNNoise-class or bespoke models | Evaluate latency + data residency. |

---

## When to apply what (policy)

| Moment | Recommendation |
|--------|----------------|
| Before first STT | Optional full-source pre-clean if noise hurts WER — see roadmap gates. |
| After G0 | If many errors cluster in noisy regions, consider re-clean + re-transcribe. |
| G1 pickups only | Prefer **scoped** clean on `vo_pickup/*.wav` — do not force full interview reprocess. |
| Before final mux | Last-chance full-normalized clean if preview is noisy — invalidates downstream per docs. |

---

## Contract with downstream

Any preprocessing must preserve:

- **Time alignment** (same duration or documented trim policy).
- **Mono/stereo contract** expected by `ingest` and Transcribe.
- **Lineage** in `preclean/lineage.json` when the product writes it (BUILD-019+).

---

## Related

- [audio_preclean](../audio_preclean/README.md)
- [stt-and-diarization.md](./stt-and-diarization.md)
- [capture](../capture/README.md) — best capture beats best post
