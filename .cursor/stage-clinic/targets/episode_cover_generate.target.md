# Target Spec — episode_cover_generate

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| image+vision ok | cover.jpg ≥1400 | Completes |
| API fail | show fallback jpg present | Completes honest |
| no artwork | refuse incomplete | No hollow done |

## Rules set

- incomplete missing jpg
- keep fail-open show fallback
- ownership ALLOW all writes

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | ALLOW cover_candidates or relocate | ownership | 7 | no |
| B2 | P1 | unambiguous | Contract tier reflect OpenAI | YAML | 7 | no |
| B3 | P2 | unambiguous | Assert min size at generate | body | 2 | no |

## Applied (Wave 2)

- B1: `publish/cover_candidates/**` ALLOW + `publish/cover_candidates/` StageInfo flush
- B2: `ALL_LLM_STAGES` → contract `llm_full` via bootstrap
- B3: `require_cover_min_size(dest, min_px=1400)` after square on OpenAI winner path

## Defaults inventory impact

- cover_image candidate_count=3 spend landmine (cost not stall)

## target_status

`draft`
