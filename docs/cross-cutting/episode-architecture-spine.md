# Episode architecture spine (speaker-volley centered)

Listener shape (sparse — components are candidates, not a mandatory checklist):

```
Cold open (hook) → Host preface → Speaker volley(s) → Transition at boundary → more volleys → optional payoff/outro
→ mix / master (−16 LUFS)
```

**Atom:** [speaker volley](./volley-glossary.md) — conversation between speakers preserved intact through ranking, transitions, EDL, preview, and master speech.

**Parallel:** every LLM stage builds an [LLM volley](./volley-glossary.md) (message packet) separately; never confuse the two.

**Dynamic brain:** topology → TBIY conformance → delivery brief (`speaker_volley_density`) → episode structure (`speaker_volleys[]`).

See [stage-volley-matrix.md](./stage-volley-matrix.md) · [episode-structure-catalog.md](./episode-structure-catalog.md) · [mix-house-chain.md](./mix-house-chain.md).
