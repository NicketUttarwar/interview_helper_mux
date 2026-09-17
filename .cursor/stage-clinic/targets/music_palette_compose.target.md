# Target Spec — music_palette_compose

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| SDP assets + assembly | ≥1 bookend cue seated; compose JSON | Completes unattended |
| LLM empty | Deterministic cues OR incomplete | Honest — no hollow cue_count=0 with assets |
| no assembly | refuse incomplete (not done) | Wait seed |

## Rules set

- admit when assembly_preview present
- incomplete if assets>0 and cue_count=0
- refuse LLM exhaust without soft-done
- precise SDP cue rewrite only

## Complexity subtraction

- Keep det fallback; subtract dual-SSOT ambiguity via one primary compose + SDP sync rule

## Acceptance checks

- cue_count≥1 when theme assets exist
- MUSIC_REQUIRES_ASSEMBLY incompleteness
- OpenAI ≤2 then fallback/refuse

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Hollow cue_count=0 with assets → incomplete | incompleteness helper | 2 | no |
| B2 | P1 | needs_you | Contract hard producer palettes vs plan | dependency data | 7 | no |
| B3 | P2 | unambiguous | Fix consumers to include sfx_prompt_craft | YAML via data | 7 | no |

## Defaults inventory impact

- none new; music epoch assembly gate already landmine-adjacent

## target_status

`draft`
