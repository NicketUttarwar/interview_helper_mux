---
id: execution-difficult-combos
tier: high
status: spec
depends_on: [execution-readme]
---

# Difficult segment combinations (mux nightmares)

These are **execution** problems: locally each clip sounds fine, but **concatenating or interleaving** them breaks the illusion of a single produced show.

## Acoustic and temporal

- **Ambience jump:** outdoor → kitchen → car without a transition; need room-tone match or short under-bed.
- **Level / noise profile jump:** one segment heavily denoised next to raw air tone.
- **Mic distance change:** same speaker sounds “teleported”; may need gentle EQ match or crossfade through music.
- **Overlap in source:** two speakers talked over each other; cutting one voice mutilates the other—requires separation model or keep overlap intact.
- **Mid-word boundary:** STT word times lied; audible click or consonant crop—needs boundary snap + micro fade.

## Model-assisted detection (optional)

When heuristics and STT disagree on **where** the ear will object, escalate with **spectrogram YOLO11** (localize overlap, laughter, handling bumps, music-heavy bands) and/or **Wav2Vec-family** embeddings (near-duplicate spans, continuity across cuts, soft hints for code-switch boundaries). Use them to **feed edge costs and scoring**, not to invent new pipeline stages ad hoc—see [spectrogram-yolo-wav2vec-orchestration.md](spectrogram-yolo-wav2vec-orchestration.md) and archetypes **I–J** in [orchestration-component-map.md](orchestration-component-map.md).

## Narrative and structure

- **Non-monotonic time:** “answer before question” reorder for drama; must not confuse listener—needs bridge VO (optional TTS) or explicit signpost in retained speech.
- **Callback far apart:** segment A references segment Z minutes later; pure reorder may lose setup—graph mux may **duplicate** a micro-setup clip (cost: redundancy vs clarity).
- **Contradiction pair:** two clips assert different facts; automatic assembly can embarrass—scoring should tag **mutual exclusion sets** and pick one.
- **Emotional whiplash:** tragedy clip adjacent to joke without spacing—needs interstitial music or longer crossfade.

## Multilingual and voice

- **Code-switching inside one answer:** single segment needs two STT locales or one multilingual model; cuts must not split mid-code-switch.
- **S2S or VC on some spans only:** timbre mismatch between processed and unprocessed neighbors—needs global voice “glue” pass or process whole speaker track.

## “Impossible” asks (still worth modeling)

- **Same words, shorter airtime:** aggressive time-compression without chipmunk (signal processing + optional S2S).
- **Remove disfluencies but keep emotion:** cut “um” chains while preserving prosody—often needs dedicated model or careful rules + crossfade atoms.

## Mitigation pattern

1. **Classify** each edge `(segment_i → segment_j)` with a cost model (acoustic delta, narrative risk).
2. **Search** order / small inserts (tone pad, music sting) to minimize cost under duration budget—see [../pipeline/assembly-and-mux/edge-cost-bridging-and-order-search.md](../pipeline/assembly-and-mux/edge-cost-bridging-and-order-search.md).
3. **Escalate** to human only when cost > threshold or a **new high-risk tool** is required ([high-risk-first-use-gating.md](high-risk-first-use-gating.md)).

## Open decisions

- Whether edge costs are **learned** (ranker on past manual fixes) or **handcrafted** first.

## Links

- [../pipeline/assembly-and-mux/timeline-and-edl.md](../pipeline/assembly-and-mux/timeline-and-edl.md)
- [../pipeline/assembly-and-mux/edge-cost-bridging-and-order-search.md](../pipeline/assembly-and-mux/edge-cost-bridging-and-order-search.md)
- [../pipeline/audio-editing/crossfades-room-tone.md](../pipeline/audio-editing/crossfades-room-tone.md)
- [../pipeline/scoring-and-selection/diversity-constraints.md](../pipeline/scoring-and-selection/diversity-constraints.md)
- [orchestration-component-map.md](orchestration-component-map.md)
- [spectrogram-yolo-wav2vec-orchestration.md](spectrogram-yolo-wav2vec-orchestration.md)
