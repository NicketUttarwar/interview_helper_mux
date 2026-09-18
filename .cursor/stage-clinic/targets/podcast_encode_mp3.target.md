# Target Spec — podcast_encode_mp3

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| master present + publishable | audio.mp3 | Completes |
| missing/empty mp3 | incomplete | Honest |

## Rules set

- incomplete empty/missing mp3
- refuse missing wav / non-publishable when required

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P1 | unambiguous | incompleteness for missing/empty mp3 | stage_completion | 2 | no |

## Applied (Wave 2)

- B1: `_podcast_encode_mp3_incompleteness` — missing/≤1024-byte `publish/audio.mp3` refuses heal/done (`encode_missing`)

## Defaults inventory impact

- none

## target_status

`draft`
