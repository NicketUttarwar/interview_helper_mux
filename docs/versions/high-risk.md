---
id: version-high-risk
tier: high
status: spec
depends_on: []
---

# High-risk / late-stage product tier

Experimental path when you accept **complexity**, **higher cost**, and **non-determinism** in exchange for **best-of-breed** components and future **custom models**.

## Goals

- **Pluggable adapters** per capability (STT, diarization, separation, TTS/S2S, embedding models)—document each provider in its own leaf under pipeline stages, not one monolithic flow.
- **Multi-provider** STT or scoring: compare transcripts, confidence, or downstream salience.
- **Speaker embeddings** and clustering for diarization or “same voice” grouping across long files.
- **Speech-to-speech** or voice conversion for polish (personal use only—your own workflow choices).
- **Overlap repair**, source separation, denoise, music-bed injection where useful.

## Typical extensions

- Fine-tuned or domain-adapted models for your interview vocabulary.
- Parallel **segmentation strategies** with automatic or manual winner selection ([../workflows/parallel-segmentation-candidates.md](../workflows/parallel-segmentation-candidates.md)).
- Graph-based **assembly** beyond linear concat ([../pipeline/assembly-and-mux/dynamic-assembly-graph.md](../pipeline/assembly-and-mux/dynamic-assembly-graph.md)).

## Open decisions

- How much automation vs manual review for high-risk outputs.
- Budget and latency envelope per interview hour.

## Links

- [low-risk.md](low-risk.md)
- [capability-matrix.md](capability-matrix.md)
- [../execution/complexity-ladder-end-to-end-ideas.md](../execution/complexity-ladder-end-to-end-ideas.md)
- [../execution/speech-to-speech-and-trained-remix-models.md](../execution/speech-to-speech-and-trained-remix-models.md)
- [../execution/high-risk-first-use-gating.md](../execution/high-risk-first-use-gating.md)
- [../pipeline/scoring-and-selection/llm-assisted-ranking.md](../pipeline/scoring-and-selection/llm-assisted-ranking.md)
