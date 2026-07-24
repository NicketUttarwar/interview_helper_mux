# Volley inventory (repo sweep)

Generated as part of the Episode Architecture / volley lexicon plan. Canonical definitions: [volley-glossary.md](./volley-glossary.md).

## Classes of hits

| Class | Meaning | Treatment |
|-------|---------|-----------|
| `compact_*_for_volley` / `compact_for_volley` | Digests into an **LLM volley** (message packet) | Docstring + alias `*_for_llm_volley` where added |
| `local_volley_framer` / `volley_turns` | LLM volley prep | Module docstring qualifies |
| `llm_call_record` / export tools | Reconstruct LLM volleys | Docstring qualifies |
| Prompt “see task in volley” | Historical LLM packet wording | Prefer “LLM volley” in new prompts |
| **Speaker volley** (new) | Conversation units in podcast | `speaker_volley.py`, `episode_structure.speaker_volleys`, EDL QC, GUI panels |
| NORTH_STAR “volley” non-goal | LLM-arbiter UI, not speaker structure | Clarified in NORTH_STAR + glossary |

## New modules

- `src/interview_mux/speaker_volley.py`
- `src/interview_mux/speaker_volley_sfx.py`
- `src/interview_mux/autopilot.py`
- `tools/check_volley_lexicon.sh`
- `tests/test_speaker_volley.py`

## Stage matrix

Full per-stage relations: [stage-volley-matrix.md](./stage-volley-matrix.md).
