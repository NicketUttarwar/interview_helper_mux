---
id: execution-readme
tier: both
status: spec
depends_on: []
---

# Execution (end-to-end ideas)

This folder is about **whole-product stories**: how far you can push **one interview recording** through slice–dice–score–mux to get a **polished podcast-like master**, at different **complexity levels**, including nasty **segment combination** problems.

It complements **pipeline/** (mechanics) and **versions/** (low vs high risk).

## In this folder

| Topic | File |
|-------|------|
| **Orchestration vs component library (read first)** | [orchestration-component-map.md](orchestration-component-map.md) |
| Simple → extreme “lovable” full runs | [complexity-ladder-end-to-end-ideas.md](complexity-ladder-end-to-end-ideas.md) |
| Hard mux / edit combinatorics | [difficult-segment-combinations.md](difficult-segment-combinations.md) |
| Spectrogram YOLO11 + Wav2Vec (optional I–J) | [spectrogram-yolo-wav2vec-orchestration.md](spectrogram-yolo-wav2vec-orchestration.md) |
| Mostly automatic runs + prompts | [automation-and-prompt-orchestration.md](automation-and-prompt-orchestration.md) |
| Pause before first use of a high-risk tool | [high-risk-first-use-gating.md](high-risk-first-use-gating.md) |
| S2S, per-language paths, custom LLM for script/score | [speech-to-speech-and-trained-remix-models.md](speech-to-speech-and-trained-remix-models.md) |
| Full localized dub (e.g. Marathi → English), MT guard rails + voice clone + master | [full-localized-dub-orchestration.md](full-localized-dub-orchestration.md) |

## North star

Use **information already in the audio** (and its transcripts/derivatives) as the primary material: **re-order**, **trim**, **bridge**, **process**, and **master**—not re-interviewing—unless you explicitly add synthetic voice lines later.

## Open decisions

- How many **archetypes** you implement as runnable presets vs one mega-graph.

## Links

- [orchestration-component-map.md](orchestration-component-map.md)
- [../versions/low-risk.md](../versions/low-risk.md)
- [../versions/high-risk.md](../versions/high-risk.md)
- [../INDEX.md](../INDEX.md)
