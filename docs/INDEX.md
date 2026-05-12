# Documentation index

Flat hub for [interview_helper_mux](../README.md). Personal, individual use—see [README.md](README.md).

## Execution (end-to-end ideas)

- [execution/README.md](execution/README.md)
- [execution/orchestration-component-map.md](execution/orchestration-component-map.md)
- [execution/complexity-ladder-end-to-end-ideas.md](execution/complexity-ladder-end-to-end-ideas.md)
- [execution/difficult-segment-combinations.md](execution/difficult-segment-combinations.md)
- [execution/automation-and-prompt-orchestration.md](execution/automation-and-prompt-orchestration.md)
- [execution/high-risk-first-use-gating.md](execution/high-risk-first-use-gating.md)
- [execution/speech-to-speech-and-trained-remix-models.md](execution/speech-to-speech-and-trained-remix-models.md)
- [execution/spectrogram-yolo-wav2vec-orchestration.md](execution/spectrogram-yolo-wav2vec-orchestration.md)
- [execution/full-localized-dub-orchestration.md](execution/full-localized-dub-orchestration.md)

## Versions

- [versions/low-risk.md](versions/low-risk.md)
- [versions/high-risk.md](versions/high-risk.md)
- [versions/capability-matrix.md](versions/capability-matrix.md)

## Workflows

- [workflows/README.md](workflows/README.md)
- [workflows/feedback-loops-and-reruns.md](workflows/feedback-loops-and-reruns.md)
- [workflows/idempotent-runs.md](workflows/idempotent-runs.md)
- [workflows/human-overrides-and-rescore.md](workflows/human-overrides-and-rescore.md)
- [workflows/parallel-segmentation-candidates.md](workflows/parallel-segmentation-candidates.md)

## Cross-cutting

- [cross-cutting/segment-schema.md](cross-cutting/segment-schema.md)
- [cross-cutting/evaluation-metrics.md](cross-cutting/evaluation-metrics.md)

## Pipeline

### Capture

- [pipeline/capture/README.md](pipeline/capture/README.md)
- [pipeline/capture/phone-recording-assumptions.md](pipeline/capture/phone-recording-assumptions.md)
- [pipeline/capture/backup-and-integrity.md](pipeline/capture/backup-and-integrity.md)
- [pipeline/capture/clipping-and-headroom.md](pipeline/capture/clipping-and-headroom.md)

### Ingest

- [pipeline/ingest/README.md](pipeline/ingest/README.md)
- [pipeline/ingest/normalization-and-format.md](pipeline/ingest/normalization-and-format.md)
- [pipeline/ingest/checksums-and-lineage.md](pipeline/ingest/checksums-and-lineage.md)
- [pipeline/ingest/chunking-long-interviews.md](pipeline/ingest/chunking-long-interviews.md)

### Transcription

- [pipeline/transcription/README.md](pipeline/transcription/README.md)
- [pipeline/transcription/word-level-timestamps.md](pipeline/transcription/word-level-timestamps.md)
- [pipeline/transcription/stt-provider-adapters.md](pipeline/transcription/stt-provider-adapters.md)
- [pipeline/transcription/diarization.md](pipeline/transcription/diarization.md)

### Segmentation

- [pipeline/segmentation/README.md](pipeline/segmentation/README.md)
- [pipeline/segmentation/silence-and-pause-splits.md](pipeline/segmentation/silence-and-pause-splits.md)
- [pipeline/segmentation/topic-embedding-boundaries.md](pipeline/segmentation/topic-embedding-boundaries.md)

### Scoring and selection

- [pipeline/scoring-and-selection/README.md](pipeline/scoring-and-selection/README.md)
- [pipeline/scoring-and-selection/salience-heuristics.md](pipeline/scoring-and-selection/salience-heuristics.md)
- [pipeline/scoring-and-selection/llm-assisted-ranking.md](pipeline/scoring-and-selection/llm-assisted-ranking.md)
- [pipeline/scoring-and-selection/diversity-constraints.md](pipeline/scoring-and-selection/diversity-constraints.md)

### Snippet store

- [pipeline/snippet-store/README.md](pipeline/snippet-store/README.md)
- [pipeline/snippet-store/segment-manifest-and-storage.md](pipeline/snippet-store/segment-manifest-and-storage.md)
- [pipeline/snippet-store/provenance-retranscribe.md](pipeline/snippet-store/provenance-retranscribe.md)

### Audio editing

- [pipeline/audio-editing/README.md](pipeline/audio-editing/README.md)
- [pipeline/audio-editing/cut-boundaries-samples.md](pipeline/audio-editing/cut-boundaries-samples.md)
- [pipeline/audio-editing/crossfades-room-tone.md](pipeline/audio-editing/crossfades-room-tone.md)
- [pipeline/audio-editing/loudness-targets-lufs.md](pipeline/audio-editing/loudness-targets-lufs.md)

### Assembly and mux

- [pipeline/assembly-and-mux/README.md](pipeline/assembly-and-mux/README.md)
- [pipeline/assembly-and-mux/timeline-and-edl.md](pipeline/assembly-and-mux/timeline-and-edl.md)
- [pipeline/assembly-and-mux/dynamic-assembly-graph.md](pipeline/assembly-and-mux/dynamic-assembly-graph.md)
- [pipeline/assembly-and-mux/edge-cost-bridging-and-order-search.md](pipeline/assembly-and-mux/edge-cost-bridging-and-order-search.md)

### Mastering and export

- [pipeline/mastering-and-export/README.md](pipeline/mastering-and-export/README.md)
- [pipeline/mastering-and-export/final-loudness-limiting.md](pipeline/mastering-and-export/final-loudness-limiting.md)
- [pipeline/mastering-and-export/chapters-metadata-export.md](pipeline/mastering-and-export/chapters-metadata-export.md)

### Human review UI

- [pipeline/human-review-ui/README.md](pipeline/human-review-ui/README.md)
- [pipeline/human-review-ui/approval-and-reorder.md](pipeline/human-review-ui/approval-and-reorder.md)
- [pipeline/human-review-ui/force-include-exclude.md](pipeline/human-review-ui/force-include-exclude.md)
