---
id: transcription-adapters
tier: both
status: spec
depends_on: [pipeline-transcription]
---

# STT provider adapters

Treat each vendor as an **adapter** with a common output schema (audio id, tokens with times, confidence, language, raw response pointer).

## Adapter contract (conceptual)

- **Input:** normalized audio URI or bytes + config (language, model id).
- **Output:** `Transcript` JSON: utterances, words, confidence, diarization labels if any.
- **Errors:** retryable vs fatal; write partials when streaming.

## Open decisions

- Whether adapters live in one repo module per provider or subprocess CLIs.

## Links

- [../../versions/high-risk.md](../../versions/high-risk.md)
- [diarization.md](diarization.md)
