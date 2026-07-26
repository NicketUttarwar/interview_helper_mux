# LLM output normalization

Canonical recovery order for every LLM gateway (`run_prompt_envelope`, `generate_local_chat`, resilience persist):

0. **Truncation scan** — `truncation_policy.scan_llm_input` at both gateways; tier.tier bump or block before accept. See [truncation-integrity.md](truncation-integrity.md).
1. **Parse** — `normalize_envelope` / JSON extract
2. **Normalize** — `llm_output_normalizer.normalize_llm_response` (omit → fabricate → block per field)
3. **Verify** — `verify_llm_response` on post-normalized payload
4. **Retry** — schema errors fed back into the prompt; max 2 attempts total (`llm_simple.py`)
5. **Fabricate batch** — mid-tier / deterministic benign defaults (`llm_fabricate`)
6. **Block** — critical null → hard stop (holistic fabrication was removed; v2 is fail-closed)
8. **Resilience** — `apply_resilience_and_persist`
9. **Acceptance** — `stage_acceptance`, `complete_llm_stage_or_halt`
10. **Persist** — artifact write + `mark_done` (only when artifact complete)

## Field tiers

See `field_necessity_registry.py`, `normalization_decision.py`, and `null_field_policy.py`:

- **nullable / commentary** (`notes`, …) → **omit** (strip key, record `_meta.null_acknowledged`)
- **fabricatable** (low-risk placeholders) → deterministic or mid-tier fabricate
- **unknown optional** (permissive default) → **fabricate** benign default, not block
- **critical / NEVER_FABRICATE** (`thesis`, `role`, `segment_ids`, …) → block → one retry, then hard stop for the operator

### Decision tree (`normalization_decision.py`)

| Classification | Downstream automation |
|----------------|----------------------|
| OMIT | Strip key, `_meta.null_acknowledged`, continue |
| FABRICATE | `llm_fabricate` benign default, continue |
| BLOCK (evidentiary) | Retry once, then hard stop — micro gap fill was removed |

Config: `analysis.llm_null_policy.permissive_mode`, `auto_fabricate_unknown_optional`.

## UI truth (Track B)

Stage `status: incomplete` when `.stage_done` exists but artifacts are pending (T1). Frontend must not show Continue until `stageHasCommittedOutputs` is true.

## Config

`analysis.llm_null_policy` in `config/app.defaults.json`:

- `fabricate_enabled`, `prefer_omit_over_fabricate`, `fabricate_max_*`
