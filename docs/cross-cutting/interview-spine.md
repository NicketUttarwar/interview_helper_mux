# Interview comprehension spine

**Artifact:** `understanding/interview_spine.json` (+ optional `understanding/interview_spine/embeddings.npz`)  
**Stage:** `interview_spine_build` (after G0 + `source_acoustic_profile`)  
**Hypothesis:** H-ORC-01 — **Promote** (shipped)

## Problem

LLM stages need **time-indexed** local evidence (pauses, speaker turns, acoustic stress) without sending full audio or running per-run model fine-tuning. The spine is a deterministic + optional CLAP retrieval index over corrected transcript windows.

## Principles

1. **Word-aligned windows** — built from `transcript/full.json` after G0 review, paced by SAP `pace_class`.
2. **Boundary event fusion** — silence valleys, pause ladder, speaker turns, trust dips, prosody shifts, topic-shift hints.
3. **Fail-open CLAP** — when MMAudio venv or CLAP deps are missing, spine JSON still ships; `retrieval.enabled: false`. No `SystemExit` on missing optional embeddings (MEC-D ≥ 3).
4. **Idempotent rebuild** — skip when `derived_from` hashes match ingest WAV, preclean isolated WAV (if present), transcript, and SAP.

## Artifact shape

See [json-schemas/interview_spine.schema.json](./json-schemas/interview_spine.schema.json).

| Section | Purpose |
|---------|---------|
| `windows[]` | Time spans with RMS, pause, WPM, optional `f0_median_hz` |
| `boundary_events[]` | Fused hinge points with `confidence` and `sources[]` |
| `retrieval` | CLAP sidecar metadata when embeddings built |
| `speaker_stats[]` | Per-speaker aggregates from windows |

Sidecar `embeddings.npz`: float matrix + `window_ids` for cosine retrieval.

## Invalidation

Re-run `interview_spine_build` when any `derived_from` input changes (ingest WAV, preclean isolated, transcript, SAP). GUI: **POST** `/api/runs/{id}/recompute-interview-spine`.

Downstream LLM stages do not auto-invalidate on spine-only recompute in v1; operator may redo from `speaker_roles` if window policy materially changed.

## Consumers

| Consumer | Use |
|----------|-----|
| `boundary_detection` | Compact boundary events + speaker stats in volley |
| `context_volley` | Per-stage `_compact_interview_spine` padding — [context-padding.md](./context-padding.md) |
| `value_analysis` / H-ORC-03 | H-ORC-02 trust dip investigations; long-run coherence via [coherence-orc03.md](./coherence-orc03.md) (30m gate) |
| `analysis_state.themes[].evidence_windows` | H-G0-03 retrieval-backed theme evidence |
| `local_volley_framer` | Top-3 CLAP hits in framer user blob |
| `source_acoustic_profile.prosody_summary` | F0 quartile bands from spine windows when present |
| Flow 2 quotability | Optional spine boundary boost (`flow2_quotability_enabled`) |

## Explicit non-goals

- **Per-run Llama/MLX weight fine-tuning** on audio + transcript — rejected; use retrieval + deterministic features instead.
- **Default SSL/Wav2Vec stack** — H-ING-01 remains opt-in only (`ssl_enabled: false`).
- **Replacing AWS Transcribe** with local ASR.

## Appendix — SSL opt-in (H-ING-01)

`interview_spine.ssl_enabled` defaults to **false**. When enabled in a future spike, a Wav2Vec merge path may populate `encoders.ssl` and optional window features — **not** merged into the default shipped pipeline. Torch/Wav2Vec dependencies stay out of the core `.venv` unless explicitly opted in and documented in [anchored-toolchain.md](./anchored-toolchain.md).

## Related

- [pipeline/understanding/interview-spine.md](../pipeline/understanding/interview-spine.md) — operator README
- [source-derived-sonic-mix-profile.md](./source-derived-sonic-mix-profile.md) — SAP + prosody
- [analysis-memory.md](./analysis-memory.md) — spine vs `analysis_state`
