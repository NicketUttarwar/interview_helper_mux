# North Star — interview_helper_mux v2

> **Turn a long-form interview recording into a listener-ready mastered podcast (`master/master.wav`) the operator trusts — and a first-time listener would find coherent, compelling, worth finishing, and worth recommending.**

## Master construction strategy

Final shape is owned by the **[Mastering Process](docs/cross-cutting/mastering-process.md)** — **8-wave research lane** → two-pass Shape Composition Engine → realization — producing a **bespoke** `mastering_plan` per podcast (no fixed five-act/TBIY template).

First-class plan decisions: **`narrative_mode`** + **`montage_grammar`** ([narrative-mode-and-montage.md](docs/cross-cutting/narrative-mode-and-montage.md)) — realized through gap VO, selection, EDL, and mode-aware **musical** sound design (MusicGen motif family; no whoosh/tick/foley). TBIY is historical inspiration only ([tbiy-production-profile.md](docs/cross-cutting/tbiy-production-profile.md)).

## Success criteria

| Criterion | Verification |
|-----------|----------------|
| Master loudness | `-16 LUFS` integrated, true peak within bounds — `python tools/verify_master.py <path>/master/master.wav` |
| Narrative + sound | Ordered speech, VO bridges where recorded, SDP beds/stingers via MMAudio mix — bound to Mastering Process plan when present |
| Listen delight | Shape critics + `mastering/listen_delight_audit.json` + **human listen rubric** (below) — **always advisory**; never blocks `master.wav` |
| Operator friction | Hard stops for **G0 transcript fix** and **gap-framing gate ladder** (recommended Yes + voice clone; prefer least-spoken host, any on-tape speaker when needed); **G1 gap VO** remains skippable; preclean is an optional offer |
| Refinement Pass | L0/L1 second analyses (gap recompose et al.); one second-run per function, never dead-ends G1/delivery — [refinement-passes.md](docs/cross-cutting/refinement-passes.md) |
| Research + Shape FT | `research_dossier` (or explicit partial/skip) + `mastering_plan` with `plan_status`; Shape failure degrades — never dead-ends G1 |

### Human listen rubric (operational delight check)

Use in smoke-test / sign-off (pass/fail per item; failures are **warnings**, not hard stops):

1. Hook / intent clear in first ~30s (or intentional sparse open)
2. Mode audible and coherent through the episode
3. VO↔clip grammar makes sense (no VO that only restates the next clip)
4. No invented claims / credentials / unspoken dialogue attributed to anyone
5. Fatigue acceptable (would finish)
6. Would recommend to a first-time listener
7. Loudness/intelligibility acceptable (`verify_master` + ears)

## Operator stops (only these)

1. **G0 — Transcript review** (mandatory): fix STT before analysis continues.
2. **G-Framing ladder** (mandatory choice; recommended **Yes**): enable interviewer framing, confirm preferred pickup speaker (least-spoken default), approve voice reference + **per-speaker clone consent**, choose Chatterbox clone (default) or record. Unattended/E2E may auto-accept product defaults. Any on-tape speaker may be consented when needed.
3. **G1 — Gap VO** (optional once framing is on): synthesize/record pickup lines or **Skip — continue without gap VO**.
4. **Preclean offer** (optional): accept or dismiss; never auto-run.
5. **NLE edits** (optional): timeline trims before ranking/EDL when operator chooses.

No mandatory operator gate for narrative mode — Shape chooses automatically (two-pass).

## Non-goals (v2)

All of the below are **deleted from the codebase**, not disabled. Inventory: [docs/v2/drop-manifest.md](docs/v2/drop-manifest.md).

- Flow 2 highlights, Flow 3 show-description pipeline, G2 flow picker (**permanent**)
- Autopilot, ITR, Stage Decision Wizard
- **LLM-arbiter / investigation-queue UI** and shard/collate/arbiter routing — not the same as **speaker volley** (conversation units in the podcast). See [docs/cross-cutting/volley-glossary.md](docs/cross-cutting/volley-glossary.md)
- Local MLX tier as a product gate — the local framer and S2S runtimes stay, fail-open
- Holistic fabrication of unspoken interview dialogue, micro gap fill
- Disfluency G0.5, analysis profile gate
- Per-stage write approval, handoff acks between stages
- Debug / Story / Volley GUI tabs
- Cloud STT (AWS Transcribe) and cloud audio APIs — STT, diarization, denoise, and SFX are local
- New spend / timeout / remint / attempt caps for Shape excellence
- Making listen delight / mode_consistency a hard mechanical blocker equal to `verify_master`

## Volley lexicon (required reading)

| Term | Meaning |
|------|---------|
| **Speaker volley** | Conversation between speakers preserved in the final podcast timeline |
| **LLM volley** | System/user/assistant message packet for one stage LLM call |

Bare “volley” is ambiguous — always qualify.

## Pipeline shape

Research waves + two-pass Shape soft-gate + analysis/delivery stages (**57** total) → `master/master.wav`. Canonical order: [`src/interview_mux/v2/config.py`](src/interview_mux/v2/config.py).

See [docs/v2/port-manifest.csv](docs/v2/port-manifest.csv) and [docs/workflows/operator-journey.md](docs/workflows/operator-journey.md).
