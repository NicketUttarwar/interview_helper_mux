# North Star — interview_helper_mux v2

> **Turn a long-form interview recording into a listener-ready mastered podcast (`master/master.wav`) the operator trusts.**

## Success criteria

| Criterion | Verification |
|-----------|----------------|
| Master loudness | `-16 LUFS` integrated, true peak within bounds — `python tools/verify_master.py <path>/master/master.wav` |
| Narrative + sound | Ordered speech, VO bridges where recorded, SDP beds/stingers via MMAudio mix |
| Operator friction | Hard stops only for **G0 transcript fix**; **G1 gap VO** is optional; preclean is an optional offer |

## Operator stops (only these)

1. **G0 — Transcript review** (mandatory): fix STT before analysis continues.
2. **G1 — Gap VO** (optional): record pickup lines or **Skip — continue without gap VO**.
3. **Preclean offer** (optional): accept or dismiss; never auto-run.
4. **NLE edits** (optional): timeline trims before ranking/EDL when operator chooses.

## Non-goals (v2)

- Flow 2 highlights, Flow 3 show-description pipeline, G2 flow picker (**permanent**)
- Autopilot, ITR, Stage Decision Wizard (default off; see plan Track B if enabled)
- Local MLX tier as product gate; **LLM-arbiter / investigation-queue UI** (default off) — not the same as **speaker volley** (conversation units in the podcast). See [docs/cross-cutting/volley-glossary.md](docs/cross-cutting/volley-glossary.md)
- Holistic fabrication
- Disfluency G0.5, analysis profile gate
- Per-stage write approval, handoff acks between stages
- Debug / Story GUI tabs as required journey stops

## Volley lexicon (required reading)

| Term | Meaning |
|------|---------|
| **Speaker volley** | Conversation between speakers preserved in the final podcast timeline |
| **LLM volley** | System/user/assistant message packet for one stage LLM call |

Bare “volley” is ambiguous — always qualify.

## Pipeline shape

**32 automated stages:** 19 analysis + 13 delivery → `master/master.wav`.

See [docs/v2/port-manifest.csv](docs/v2/port-manifest.csv) and [docs/workflows/operator-journey.md](docs/workflows/operator-journey.md).
