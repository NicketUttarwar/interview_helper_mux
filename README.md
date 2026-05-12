# interview_helper_mux

Design notes and specs for **one long interview recording → analyzable text, ranked segments, optional edits, and a muxed podcast-style master** (personal / single-operator use). Implementation can follow later; **`docs/` is the source of truth.**

---

## At a glance

| | |
|--|--|
| **Goal** | Re-order, trim, bridge, process, and master using **audio + transcripts + manifests**—not re-interviewing—unless you explicitly add synthetic lines. |
| **Where to start** | [docs/INDEX.md](docs/INDEX.md) · [docs/README.md](docs/README.md) |
| **End-to-end stories** | [docs/execution/README.md](docs/execution/README.md) |
| **Orchestration vs components** | [docs/execution/orchestration-component-map.md](docs/execution/orchestration-component-map.md) |

---

## Repository structure (high level)

```text
interview_helper_mux/
├── README.md              ← this file (keep short; edit as the repo grows)
├── db/                    ← canonical SQLite schema + Python `mux_store` (see db/README.md)
├── data/                  ← default local database file (gitignored); created by sync tool
├── tools/                 ← e.g. sync Markdown + specs into SQLite
└── docs/
    ├── INDEX.md           ← flat link hub
    ├── README.md          ← how to read the doc tree
    ├── execution/         ← presets, mux nightmares, automation, gating, optional ML overlays
    ├── pipeline/          ← capture → ingest → … → mastering (stage READMEs + leaf topics)
    ├── workflows/         ← loops, idempotency, parallel runs, human overrides
    ├── versions/          ← low-risk vs high-risk capability posture
    └── cross-cutting/     ← segment schema, evaluation metrics
```

Heavy assets, secrets, and generated audio stay **out of git** (see [docs/README.md](docs/README.md)).

---

## Architecture (very high level)

**Single backbone** every product story still hangs on:

**capture → ingest → transcription → segmentation → scoring & selection → snippet store → audio editing → assembly & mux → mastering & export**

Human review is a **control plane** (approve, reorder, gates)—not a duplicate physics pipeline. Details per stage: [docs/pipeline/](docs/pipeline/).

---

## Orchestration ideas (very high level)

These are the **ideas** the execution docs spell out; treat this block as **summary only**—update it when presets or policy change.

1. **Frozen backbone, parameterized tools** — The orchestrator adjusts **configs and allowed tools**; it does not invent arbitrary new pipeline stages at runtime ([docs/execution/automation-and-prompt-orchestration.md](docs/execution/automation-and-prompt-orchestration.md)).
2. **Presets (“archetypes”)** — From simple **highlight reel** through **timeboxed director’s cut**, **nonlinear graph story**, **bilingual/code-switch**, **DSP polish**, **speech-to-speech**, and **custom rankers**—each is a named slice you could ship as one button ([docs/execution/complexity-ladder-end-to-end-ideas.md](docs/execution/complexity-ladder-end-to-end-ideas.md)).
3. **Difficult mux as first-class** — Bad **joins** (level, room tone, overlap, narrative whiplash) get **edge costs**, search/bridges, and human escalation when needed ([docs/execution/difficult-segment-combinations.md](docs/execution/difficult-segment-combinations.md)).
4. **High-risk gating** — First use of destructive or novel capabilities (S2S, separation, custom checkpoints, **optional** spectrogram-YOLO / Wav2Vec overlays) stops once per profile until approved ([docs/execution/high-risk-first-use-gating.md](docs/execution/high-risk-first-use-gating.md)).
5. **Optional parallel enrichments** — e.g. **spectrogram YOLO11** (hazard localization) and **Wav2Vec** embeddings (dedup / continuity hints) attach **after ingest**, feed **scoring & mux** only, and stay **versioned tool calls** ([docs/execution/spectrogram-yolo-wav2vec-orchestration.md](docs/execution/spectrogram-yolo-wav2vec-orchestration.md)).

For **which doc covers what** and **conformance** of each preset against the component library, use the map: [docs/execution/orchestration-component-map.md](docs/execution/orchestration-component-map.md).
