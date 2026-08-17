# North Star — interview_helper_mux v2

> **Turn a messy long-form interview into a listener-ready `master/master.wav` the operator trusts — structured so a first-time listener can follow and retain the important ideas, finish the episode, and recommend it.**

## Essence

Every native source is a **mess**: overlapping words, speakers, noise, false starts, buried digressions, uneven communicative weight. Humans speak that way.

**What this application is for:**

1. Find the **ideal way to communicate** what was spoken on that tape.
2. Find **golden nuggets** — passionate, information-dense native segments often drowned by surrounding talk.
3. Find **ideal cut points** so each keep is listenability-optimal and idea-intact.
4. Use spoken information **holistically** (including same-speaker concepts across time) to weave a **story**.
5. Realize that story as a **conversation**: native clips ↔ grounded synthetic voice ↔ music / SFX / intentional air — mastered in harmony.

**Editorial stance:** “Poorly spoken” means weak *idea weight*, not polishing guest filler. Synthetic inserts may **recombine concepts the same speaker already said**. Never invent unspoken claims or dialogue. Fight STT errors, Hinglish/Spanglish/code-switch, and domain nomenclature failures (G0 + lexicon/passion islands).

## Story architecture (structure-first mastering)

The product is not “glue leftover clips.” **Shape / Mastering Process** chooses storytelling architecture; then:

| Part | Role |
|------|------|
| Native segments | Proof on tape — golden nuggets at ideal in/out points |
| Synthetic voice | Conversational partners — orientation, bridges, grounded recombination |
| Music / SFX / air | Scene support under that structure |

**Combinations and mutations** (order, keeps, bridges, beds, duration toward soft ideal) exist to convey the **most information in the best manner**.

**Retention policy:** **aim band** for final `master/master.wav` (and selection proxy) = **0.45×–1.5×** of source duration. Soft pack toward delivery-brief **ideal** (~45% of source). **Hard floor ~10%** catastrophe net only; **hard ceiling 1.5×** (VO/music may expand past source, not unboundedly). Never a high retention lock (e.g. 35%) that blocks reshaping the episode.

**Sonic coverage bands** (Shape-owned soft targets, not remux theater):

| Band | Range |
|------|-------|
| Bed coverage | **0.28–0.88** |
| Hinge stinger coverage | **0.3–1.0** |

## Master construction strategy

Final shape is owned by the **[Mastering Process](docs/cross-cutting/mastering-process.md)** — **8-wave research** → Shape Composition Engine (mutation search over native/synthetic/sonic ensembles) → realization → `master/master.wav`.

First-class plan decisions: **`narrative_mode`** + **`montage_grammar`** ([narrative-mode-and-montage.md](docs/cross-cutting/narrative-mode-and-montage.md)) — realized through gap VO, selection, EDL, and mode-aware **musical** sound design (MusicGen motif family; no whoosh/tick/foley). TBIY is historical inspiration only ([tbiy-production-profile.md](docs/cross-cutting/tbiy-production-profile.md)).

## Success criteria

| Criterion | Verification |
|-----------|----------------|
| Master loudness | `-16 LUFS` integrated, true peak within bounds — `python tools/verify_master.py <path>/master/master.wav` |
| Narrative + sound | Ordered speech, VO bridges where recorded, SDP beds/stingers via MMAudio mix — bound to Mastering Process plan when present |
| Listen delight | `mastering/listen_delight_audit.json` + scorecard + human rubric — **authoritative ship gate** (blocks finalize quality + publish when floors fail) |
| Idea transmission | First-time listener can retell thesis / main claims; nuggets audible; cuts do not shred meaning |
| Operator friction | Hard stops for **G0 transcript fix** and **gap-framing gate ladder**; **G1 gap VO** remains skippable; preclean is an optional offer |
| Refinement Pass | L0/L1 second analyses; one second-run per function, never dead-ends G1/delivery — [refinement-passes.md](docs/cross-cutting/refinement-passes.md) |
| Research + Shape FT | `research_dossier` (or explicit partial/skip) + `mastering_plan` with `plan_status`; Shape failure degrades — never dead-ends G1 |

### Human listen rubric (ship checklist)

Use in smoke-test / sign-off. Machine delight floors mirror these; failures **block ship** when listen_delight mode is authoritative:

1. Hook / intent clear in first ~30s (or intentional sparse open)
2. Mode audible and coherent through the episode
3. VO↔clip grammar makes sense (no VO that only restates the next clip)
4. No invented claims / credentials / unspoken dialogue attributed to anyone
5. Fatigue acceptable (would finish)
6. Would recommend to a first-time listener
7. Loudness/intelligibility acceptable (`verify_master` + ears)
8. Golden nuggets not drowned; cut edges listenability-clean
9. Grounded synthesis only (recombined same-speaker concepts attributable to tape)

### Interim segment quality scale

Until a unified density score lands, operable signals include: `self_explanatory` / segment flags · gap severity · ranking excludes · passion/lexicon STT priors · pack retention vs brief ideal · junction/seam autopsy · listener scorecard · **authoritative listen_delight** dims (`nugget_retention`, `cut_integrity`, `conversation_fit`, `sonic_weave`, `mode_coherence`, `finishability`, `recommendability`).

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
- New spend / timeout / remint / attempt caps for Shape excellence without evidence

## Volley lexicon (required reading)

| Term | Meaning |
|------|---------|
| **Speaker volley** | Conversation between speakers preserved in the final podcast timeline |
| **LLM volley** | System/user/assistant message packet for one stage LLM call |
| **Nugget** | High communicative-weight native span (passion and/or idea density) recoverable into the master or grounded synthetic framing |

Bare “volley” is ambiguous — always qualify.

## LLM volley packets (quality covenant)

User packets must contain **this tape’s meaning** (transcript, segment excerpts, spine windows, must-keep IDs as editorial constraints). Forbidden: path-exists flags, `.stage_done`, fingerprint dumps, e2e heal notes. Spec: [docs/cross-cutting/llm-volley-context.md](docs/cross-cutting/llm-volley-context.md).

**Must-keep clips** (gap-framing primaries, vernacular/low-conf, ideal-cuts, talking-point must-keeps) stay in `ordered_segment_ids`. **E2E must not stub QC green** (`INTERVIEW_MUX_E2E_SOFT` default off). **Resume** does not `clear_from` past a frozen gap spine.

## Quality spine (all hard)

`verify_master` (−16 LUFS) · junction snip QA authoritative residuals · listener scorecard / post_master_quality · **listen_delight** (authoritative).

## Pipeline shape

Research waves + Shape + analysis/delivery stages (**65** total) → `master/master.wav`. Canonical order: [`src/interview_mux/v2/config.py`](src/interview_mux/v2/config.py).

**Brains:** **0.1.0** (default — latest registered homunculus). **0.0.0** remains the original linear walk on the Start slider — [docs/cross-cutting/mastering-homunculus.md](docs/cross-cutting/mastering-homunculus.md).

See [docs/v2/port-manifest.csv](docs/v2/port-manifest.csv) and [docs/workflows/operator-journey.md](docs/workflows/operator-journey.md).
