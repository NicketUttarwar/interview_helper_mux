# Target Spec — mmaudio_sfx

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| gen+QA pass | WAVs + qa complete | Unattended |
| ladder exhaust | music_omitted stamp; no stub | Mix may proceed excluding omitted |
| QA fail | incomplete / block mix per flag | Honest — no hollow done |
| G1.5 open | refuse gen | No fake WAVs |

## Rules set

- admit with assembly+prompts+approve
- incomplete without WAV parity
- refuse stub when fail_closed
- precise invalidate music epoch only via seal rules

## Complexity subtraction

- Align StageInfo/contract to MusicGen-first + omit; do not clinic model ladders

## Acceptance checks

- done iff QA parity or honest omit
- no creative stub under fail_closed
- mix sees omit set

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Drop llm_execute from contract lifecycle | dependency data | 7 | no |
| B2 | P0 | needs_you | creative_delivery vs omit-all ship policy | publishability | 6 | yes |
| B3 | P1 | unambiguous | StageInfo MusicGen-first copy | stages.py | 2 | no |

## Defaults inventory impact

- block_mix_on_mmaudio_qa_fail=true; fail_closed_on_stub=true — landmines

## target_status

`draft`
