# Speech-to-text (STT) and diarization — options and source of truth

This repo’s **implemented** path is **local MLX STT + diarization** via **mlx-audio** in `ASSETS/local_speech/venv` — see [README.md](./README.md) and `src/interview_mux/stages/transcribe_local.py`. Bootstrap: `./scripts/bootstrap_venv.sh` (step 4/5). AWS Transcribe was removed — `transcribe_aws.py` no longer exists. Catalog options below are **not** locked unless added to the toolchain doc.

---

## Terminology

| Term | Meaning |
|------|---------|
| **STT / ASR** | Speech-to-text: audio → text (often word- or segment-level timestamps). |
| **Diarization** | “Who spoke when?” — labels segments or words with `spk_0`, `spk_1`, … |
| **Word timestamps** | Per-word `start`/`end` times — needed for clip review, boundary detection, mux. |
| **Channel separation** | Stereo with interviewer on one channel — cheap “diarization” if recording setup allows. |

---

## What interview_helper_mux expects on disk (contract)

Regardless of vendor, downstream stages expect something **like** today’s `transcript/full.json` + `transcript/speakers.json`: **time-aligned words** and **usable speaker differentiation**. Any new adapter must **normalize** into that shape (or extend the schema + docs in the same change).

---

## Implemented: Amazon Transcribe

| Dimension | Notes |
|-----------|--------|
| **Strengths** | Solid general-purpose ASR; built-in **diarization**; integrates with S3; predictable batch API. |
| **Weaknesses** | Cloud-only; upload latency for huge files; diarization can confuse crosstalk; pricing per minute. |
| **Ops** | Requires `aws` CLI, bucket, IAM, region — see [troubleshooting](../../workflows/troubleshooting.md#transcription-aws). |

---

## Cloud managed APIs (paid / usage-based)

Strong when you want **high uptime**, **fast integration**, and **optional** extras (punctuation, summarization, custom vocabulary).

| Family | Typical strengths | Watch-outs |
|--------|-------------------|------------|
| **Deepgram** | Low-latency streaming; Nova models; diarization options | SaaS data path; key rotation |
| **AssemblyAI** | Developer-friendly JSON; features (redaction, summarization) | SaaS data path |
| **Google Cloud Speech-to-Text** | Enterprise footprint; multi-region | Billing complexity; diarization as add-on |
| **Microsoft Azure Speech** | Enterprise; custom endpoints | Same |
| **Rev.ai** | Human + AI hybrid tiers | Cost / latency for human path |
| **OpenAI** (`whisper-1` etc.) | Simple API for some workloads | Diarization not same as multi-speaker specialist APIs; check latest product limits |

**Selection rule:** Prefer vendors that expose **word-level timestamps** + **speaker labels** (or channels) matching your mux pipeline.

---

## Local and open-source (offline-first)

Good for **privacy**, **repeatable dev**, and **no per-minute bill**; you own **GPU/CPU** ops.

| Option | Typical use | Diarization |
|--------|-------------|-------------|
| **faster-whisper** (CTranslate2) | Fast local Whisper-class ASR | Combine with separate diarization |
| **whisper.cpp** | Edge / CPU-friendly | Same |
| **OpenAI Whisper** (reference impl) | Research / small batch | Same |
| **Vosk** | Lightweight; embedded | Limited speaker ID |
| **Kaldi / Icefall** | Max control, ASR research stacks | Often paired with **x-vectors** / diarization pipelines |

**Diarization add-ons (OSS / research):**

| Approach | Notes |
|----------|--------|
| **pyannote.audio** | Strong diarization; **model weights are gated** — accept license terms before production. |
| **NVIDIA NeMo** | End-to-end ASR + diarization toolkits in some recipes | GPU-heavy |
| **simple heuristics** | Energy/VAD + clustering | Fragile on overlap |

---

## Separation of concerns (recording-time vs post)

| Technique | What it fixes |
|-----------|----------------|
| **Dual-mic / multitrack** | True isolation: mix minus, separate WAV per speaker — best diarization “for free” if feasible at capture. |
| **Stereo channel mapping** | If interviewer is always L and guest R, map channels before STT. |

---

## Operational checklist (any vendor)

1. **Sample rate / format** — normalize to project ingest (see [ingest](../ingest/README.md)).
2. **Crosstalk** — expect diarization errors; flag in segmentation (`heavy_crosstalk`) and G0.
3. **Domain vocabulary** — use custom vocabulary / hints where the API supports it.
4. **Failure strings** — log full provider `FailureReason` / HTTP body — see [troubleshooting](../../workflows/troubleshooting.md).

---

## Related

- [transcript-review.md](./transcript-review.md) — G0 human correction
- [source-separation-and-enhancement.md](./source-separation-and-enhancement.md) — denoise / separation before STT
- [audio_preclean](../audio_preclean/README.md) — product-level optional isolation
- [troubleshooting](../../workflows/troubleshooting.md)
