# Possibility Map — sound_design_palettes

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | primary `understanding/sound_design_plan.json` | gate: none | OpenAI optional (`early_palettes_llm`) | seed 23

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| defaults path | early_palettes_llm=false → defer empty palettes + heal | `IN_CODE` | `sound_design_stages.py:35-75` |
| LLM path | Needs brief/manifest/sonic in payload | `IN_CODE` | L77-105 |
| sound_design.enabled=false | `_mark_skipped` heal | `IN_CODE` | L29-31, L654-660 |
| contract hard boundaries+sonic | Deferred path may not hard-fail if missing | `CODE_DOC_CONFLICT` | contract vs deferred |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | After sonic | `IN_CODE` | — |
| invalidated | By boundary/class/reanchor claims | `DOC_ONLY_UNVERIFIED` | — |

## 3. Partial-accel gate posture

N/A

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success (defaults) | Deferred coherence seed; empty palettes OK completeness | `IN_CODE` | L35-75 + artifact_completeness `_gaps_sound_design_plan` |
| clean success (LLM) | Persist palettes + provenance | `IN_CODE` | L107-130 |
| soft fail | N/A | — | — |
| hard fail | LLM StageError when early LLM on | `IN_CODE` | — |
| contract sufficiency palettes≥1 | Conflicts with deferred empty | `CODE_DOC_CONFLICT` | contract sufficiency vs code |

## 5. Side effects

- Writes/merges sound_design_plan.json (shared with later sound_design_plan stage)
- Dual invent obligation deferred to sound_design_plan

## 6. Complexity traps

- Early LLM optional vs delivery SDP invent
- Shared artifact dual writers
- Local heavy ML: N/A (MusicGen later — out of clinic)

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| llm_full | Default path skips LLM | `CODE_DOC_CONFLICT` |
| sufficiency palettes min 1 | Deferred allows empty | `CODE_DOC_CONFLICT` |
| hard boundaries+sonic | Soft in deferred path | `CODE_DOC_CONFLICT` |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| early LLM off | N/A OpenAI | `IN_CODE` | defaults early_palettes_llm=false |
| early LLM on | theme-palettes prompt ≤2 | `IN_CODE` | L123-130 |
| hollow palettes | Allowed when deferred | `IN_CODE` | completeness gaps |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | Skip early LLM; stamp deferred plan; continue | `IN_CODE` | early_palettes_llm=false |
| human stall? | No | `IN_CODE` | — |
| GUI-only? | No | `IN_CODE` | — |
| forcing early LLM as “fix” | Extra OpenAI variance / cost on Full-auto | `FULL_AUTO_REGRESSION_RISK` | — |

### §5.5 Flags

- sound_design.enabled true
- sound_design.early_palettes_llm **false** (shipped)

### §5.6 TEST_GAP

- `test_sound_design_stages.py`, `test_sonic_palette_keywords.py` (~20)
- Gaps: contract sufficiency vs deferred completeness parity

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

Top footgun: contract says palettes required; defaults deliberately heal with empty deferred palettes.

## Open questions for operator

1. Confirm deferred-empty remains the Full-auto contract (fix YAML sufficiency) — recommended.

## discovery_status

`complete`
