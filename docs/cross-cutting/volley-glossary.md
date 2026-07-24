# Volley glossary

**Status:** canonical. Bare ambiguous `volley` in new docs/prompts/schemas is a defect.

Two legitimate meanings exist in this repo. Always qualify.

---

## Speaker volley

**Speaker volley** = a stretch of **conversation between speakers in the interview audio** that is selected, ordered, and preserved into the **final podcast** speech timeline (`master/master.wav`).

- Multi-turn (or multi-party) back-and-forth with high-level relation (topic, Q→A, reaction).
- First-class atom: `speaker_volleys[]` on `understanding/episode_structure.json`.
- Operator-facing copy and narrative/timeline code use this meaning.
- Integrity: ranking / transitions / EDL must not split a locked speaker volley mid-block.

Aliases (only when paired): “conversation volley”, “speaker exchange volley”. Prefer **speaker volley** in schemas and identifiers (`speaker_volley_id`, `speaker_volley_density`).

---

## LLM volley

**LLM volley** = the **constructed message stack** (system / user / assistant / related turns) that builds the **full context packet** passed to a large language model for one stage call.

- How messages are assembled, compacted, framed (local framer), and recorded.
- Code: `compact_*_for_volley` / `compact_for_llm_volley`, `local_volley_framer`, `split_messages_for_volley`, LLM call records.
- Not an operator gate on the default v2 path. Max **2** LLM attempts per stage, then hard stop.

---

## NORTH_STAR wording

When NORTH_STAR lists “volley” under non-goals, it means **no LLM-arbiter / investigation-queue product UI** on the default journey — **not** “no speaker conversation structure” and **not** “erase LLM message-packet assembly.”

Flow 2 / Flow 3 / G2 remain permanently excluded from the volley architecture work.

---

## Anti-patterns

| Bad | Good |
|-----|------|
| “run a volley” (ambiguous) | “run an LLM volley” or “preserve the speaker volley” |
| Calling show-description copy a speaker volley | LLM volley → copy artifact |
| Splitting a Q→A pair in ranking | Keep speaker volley atomic |
| Bare `volley` in new operator UI | **Speaker volley** or **LLM volley review** |

---

## Related

- [stage-volley-matrix.md](./stage-volley-matrix.md) — every stage’s relation
- [episode-architecture-spine.md](./episode-architecture-spine.md) — speech timeline spine
- [mix-house-chain.md](./mix-house-chain.md) — engineering order (Track B)
