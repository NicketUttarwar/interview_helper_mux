# North Star — interview_helper_mux v2

> **Turn a long-form interview recording into a listener-ready mastered podcast (`master/master.wav`) the operator trusts.**

## Master construction strategy

Final shape is owned by the **[Mastering Process](docs/cross-cutting/mastering-process.md)** — research lane → Shape Composition Engine → realization — producing a **bespoke** `mastering_plan` per podcast (no fixed five-act/TBIY template). TBIY is historical inspiration only ([tbiy-production-profile.md](docs/cross-cutting/tbiy-production-profile.md)).

## Success criteria

| Criterion | Verification |
|-----------|----------------|
| Master loudness | `-16 LUFS` integrated, true peak within bounds — `python tools/verify_master.py <path>/master/master.wav` |
| Narrative + sound | Ordered speech, VO bridges where recorded, SDP beds/stingers via MMAudio mix — bound to Mastering Process plan when present |
| Operator friction | Hard stops for **G0 transcript fix** and **gap-framing gate ladder** (recommended Yes + voice-cloned least-spoken host); **G1 gap VO** remains skippable; preclean is an optional offer |

## Operator stops (only these)

1. **G0 — Transcript review** (mandatory): fix STT before analysis continues.
2. **G-Framing ladder** (mandatory choice; recommended **Yes**): enable interviewer framing, confirm least-spoken pickup speaker, approve voice reference, choose Chatterbox clone (default) or record. Unattended/E2E may auto-accept product defaults.
3. **G1 — Gap VO** (optional once framing is on): synthesize/record pickup lines or **Skip — continue without gap VO**.
4. **Preclean offer** (optional): accept or dismiss; never auto-run.
5. **NLE edits** (optional): timeline trims before ranking/EDL when operator chooses.

## Non-goals (v2)

All of the below are **deleted from the codebase**, not disabled. Inventory: [docs/v2/drop-manifest.md](docs/v2/drop-manifest.md).

- Flow 2 highlights, Flow 3 show-description pipeline, G2 flow picker (**permanent**)
- Autopilot, ITR, Stage Decision Wizard
- **LLM-arbiter / investigation-queue UI** and shard/collate/arbiter routing — not the same as **speaker volley** (conversation units in the podcast). See [docs/cross-cutting/volley-glossary.md](docs/cross-cutting/volley-glossary.md)
- Local MLX tier as a product gate — the local framer and S2S runtimes stay, fail-open
- Holistic fabrication, micro gap fill
- Disfluency G0.5, analysis profile gate
- Per-stage write approval, handoff acks between stages
- Debug / Story / Volley GUI tabs
- Cloud STT (AWS Transcribe) and cloud audio APIs — STT, diarization, denoise, and SFX are local

## Volley lexicon (required reading)

| Term | Meaning |
|------|---------|
| **Speaker volley** | Conversation between speakers preserved in the final podcast timeline |
| **LLM volley** | System/user/assistant message packet for one stage LLM call |

Bare “volley” is ambiguous — always qualify.

## Pipeline shape

**33 automated stages:** 20 analysis + 13 delivery → `master/master.wav`. Canonical order: [`src/interview_mux/v2/config.py`](src/interview_mux/v2/config.py).

See [docs/v2/port-manifest.csv](docs/v2/port-manifest.csv) and [docs/workflows/operator-journey.md](docs/workflows/operator-journey.md).
