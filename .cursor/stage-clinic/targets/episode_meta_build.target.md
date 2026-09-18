# Target Spec — episode_meta_build

brain: 0.2.0 | target_status: applied

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| selection+LLM | real title/description | Completes |
| LLM fail / empty / Untitled | refuse incomplete | Honest |
| empty selection | refuse or incomplete | No Untitled lie |

## Rules set

- incomplete empty/Untitled title
- refuse LLM exhaust
- hard-require selection (align contract)

## Complexity subtraction

- Drop Untitled soft-success

## Acceptance checks

- ≤2 attempts; no hollow done; denylist

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Refuse empty/Untitled title | _persist_meta | 2,4 | yes |
| B2 | P1 | unambiguous | Align hard selection | contract+body | 7 | no |
| B3 | P2 | unambiguous | Stop transcript→meta ADG invalidate | ADG | 7 | no |

## Defaults inventory impact

- EMB-B1: hollow Untitled no longer ships as done (may stall Full-auto until LLM yields real title)

## Wave 2 apply log

- B2 applied: body refuses missing selection before LLM; soft brief+narrative in dependency_data + bootstrap YAML; pin `test_episode_meta_build_requires_selection`
- B3 applied: `_PROPAGATION_SEEDS` + dependency_data propagation = podcast_publish only; pin `test_master_transcript_invalidates_exclude_episode_meta`
- B1 applied (6B): refuse empty/Untitled in `_persist_meta`; pin `test_episode_meta_build_refuses_untitled`

## target_status

`applied`
