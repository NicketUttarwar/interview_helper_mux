# Tools not in repo — landscape by value lever

Catalog of **directions** and representative tools/libraries/services **not first-class in this repository today**, grouped by **value lever** (what gets better for listener, idea, or creator). This is not a gap list against v1.

**Audio-only.** For model families, see [moonshot-model-families.md](./moonshot-model-families.md). For guardrails and idea themes, see [future-proofing.md](../../roadmap/future-proofing.md).

**When a spike ships code:** Pin exact versions in [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md#optional-research--spike-libraries-not-in-default-lock), refresh `requirements.lock`, run `pip-audit`, and use **Context7** at that version before writing integrations.

---

## Lever A — Find the emotional authentic peak

| Direction | Examples (research) | Primary axis |
|-----------|---------------------|--------------|
| Paralinguistic events | Laughter/applause detectors, PANNs, YAMNet-class | LEX |
| Prosody / affect features | openSMILE eGeMAPS, SpeechBrain emotion recipes | LEX |
| SSL trajectory peaks | Wav2Vec2-state statistics | LEX |

## Lever B — Surface the ideational hinge

| Direction | Examples | Primary axis |
|-----------|----------|----------------|
| Thought-boundary fusion | SSL + transcript change-points | COM |
| Retrieval by concept in sound | CLAP / Microsoft CLAP text queries over windows | COM |
| Cognitive-load proxies | Speaking rate + pause structure | COM |

## Lever C — Compress operator cognitive load

| Direction | Examples | Primary axis |
|-----------|----------|----------------|
| Communicative salience ranking | Combine acoustic stress with text “idea risk” | CRE |
| Forced alignment tooling | WhisperX-style for micro-edit handles | CRE |
| Quality heatmaps | NISQA / DNSMOS-class regional scores | CRE |

## Lever D — Protect intelligibility under interference

| Direction | Examples | Primary axis |
|-----------|----------|----------------|
| Stem-ratio features | Demucs vocals vs rest as analysis inputs | LEX / COM |
| Music bleed tagging | AudioSet-class detectors | COM |

## Lever E — Long-run coherence (memory)

| Direction | Examples | Primary axis |
|-----------|----------|----------------|
| Chunked audio embeddings | Tile + pool for “spine” signals | COM |
| Anomaly triggers | Acoustic surprise + text ambiguity | CRE |

## Lever F — Moonshot interpretability

| Direction | Examples | Primary axis |
|-----------|----------|----------------|
| Audio LM captions / risk maps | Research APIs | COM / CRE |

---

## How to use this doc

1. Pick a **lever** aligned to your spike sprint.
2. Map tools to a row in [future-proofing.md](../../roadmap/future-proofing.md) *Idea directions* (add sparingly).
3. Score with [phase3-spike-framework.md](./phase3-spike-framework.md); record in [spike-results-and-winners.md](./spike-results-and-winners.md).
