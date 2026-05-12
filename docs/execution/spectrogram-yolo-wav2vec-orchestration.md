---
id: execution-spectrogram-wav2vec
tier: high
status: spec
depends_on: [execution-readme]
---

# Spectrogram YOLO11 and Wav2Vec in difficulty orchestration

This page is **optional machinery**: it only pays off when plain STT + silence segmentation **miss** hazards that break mux, scoring, or human trust. Treat both as **gated tools** with stable tool ids ([high-risk-first-use-gating.md](high-risk-first-use-gating.md)) when you ship custom weights or change checkpoint hashes.

## Why these two sit together

- **Spectrogram YOLO11** answers “**where** in time–frequency does something structurally weird happen?” (overlap bands, handling thumps, laugh bursts, strong music bleed). It is a **localizer** on a 2D view derived from audio.
- **Wav2Vec-family** models (wav2vec 2.0, XLS-R, etc.) answer “**how similar** is this span to that span in representation space?”—useful for **dedup**, **speaker-consistent chains**, and **soft language / register hints** when text alone is ambiguous.

They are **orthogonal**: YOLO proposes **candidate intervals**; Wav2Vec can **re-score or cluster** those intervals (and neighbors) so the orchestrator does not treat every detection as a hard block.

## Contracts (what each emits)

### Spectrogram YOLO11 overlay

| | |
|--|--|
| **Inputs** | Normalized waveform or STFT/mel pipeline agreed in ingest; fixed hop and window so boxes map to sample time. |
| **Outputs** | Axis-aligned boxes in `(time_start, time_end, freq_low, freq_high)` plus **class** labels you define (e.g. `double_talk`, `laughter`, `mic_tap`, `music_dominant`). Downstream: merge to **segment manifest** annotations ([../cross-cutting/segment-schema.md](../cross-cutting/segment-schema.md)). |
| **Failure modes** | Domain shift (new mic, new room); over-triggering blocks good cuts; under-triggering lets bad edges through. Version **weights + mel params** in lineage. |

### Wav2Vec embeddings

| | |
|--|--|
| **Inputs** | Same audio chunks as segments (or sliding windows); respect chunking policy ([../pipeline/ingest/chunking-long-interviews.md](../pipeline/ingest/chunking-long-interviews.md)). |
| **Outputs** | Fixed-dim vectors per span (mean-pool or learned head); optional **pairwise similarity** or **cluster id** for orchestration only—not a transcript. |
| **Failure modes** | “Sounds alike” ≠ “same factual claim”; embeddings favor **acoustic** nearness. Never use alone for mutual-exclusion policy ([difficult-segment-combinations.md](difficult-segment-combinations.md)). |

## Difficulty orchestration loop (when to run what)

1. **Cheap path:** existing `stt → seg → score` ([orchestration-component-map.md](orchestration-component-map.md)).
2. **Escalation A — hazard map:** if edge-cost search ([../pipeline/assembly-and-mux/edge-cost-bridging-and-order-search.md](../pipeline/assembly-and-mux/edge-cost-bridging-and-order-search.md)) or heuristics report **high acoustic delta** or **overlap** suspicion, run **YOLO on spectrograms** for those neighborhoods only (not whole file if you can window).
3. **Escalation B — embedding pass:** on YOLO-positive windows **and** their ±N-second context, compute **Wav2Vec** embeddings; use for (a) **dedup / near-duplicate** suppression in scoring, (b) **continuity** cost between adjacent picks, (c) optional **language-boundary hint** alongside text for code-switch ([difficult-segment-combinations.md](difficult-segment-combinations.md)).
4. **Human:** when YOLO and transcript/diarization **disagree** on “speech vs overlap” or when embedding clusters **split** what the editor thought was one story—surface in review UI, do not auto-silence.

Using **only YOLO** is valid for “find bad splice neighborhoods.” Using **only Wav2Vec** is valid for “rank without extra LLM calls.” **Together** reduces false blocks: YOLO finds candidates; Wav2Vec down-weights benign lookalikes (e.g. room tone band mistaken for music).

## Where this sits in the backbone DAG

Neither replaces `transcription` or `segmentation`. They are **parallel enrichments** after [ingest](../pipeline/ingest/README.md), feeding **scoring**, **snippet store** metadata, and **mux** edge costs:

`ingest → (optional parallel: spectro_yolo, wav2vec_embed) → stt → seg → score → … → mux`

The orchestrator **parameterizes** runs (window lists, model versions); it does not add ad-hoc stages outside this contract ([automation-and-prompt-orchestration.md](automation-and-prompt-orchestration.md)).

## Links

- [difficult-segment-combinations.md](difficult-segment-combinations.md)
- [orchestration-component-map.md](orchestration-component-map.md)
- [complexity-ladder-end-to-end-ideas.md](complexity-ladder-end-to-end-ideas.md)
- [../pipeline/assembly-and-mux/edge-cost-bridging-and-order-search.md](../pipeline/assembly-and-mux/edge-cost-bridging-and-order-search.md)
- [../cross-cutting/evaluation-metrics.md](../cross-cutting/evaluation-metrics.md)
