# Target Spec — information_package_plan

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| corpus ok | audit + optional plan patch | Completes |
| corpus missing | would_commit false + warning; still audit | Completes (or incomplete if decided) |
| disabled | empty packages + episode_close | Completes |

## Rules set

- always write audit; episode_close always
- regroup only if allow_regroup
- no LLM

## Complexity subtraction

- Drop llm_execute lifecycle claim

## Acceptance checks

- commit_music_vo default; require_corpus warn path

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| IPP-B1 | P1 | unambiguous | Drop llm_execute from lifecycle | YAML | 7 | no |
| IPP-B2 | P1 | needs_you | Incomplete vs warn on empty corpus | require_corpus | 2,5 | yes |
| IPP-B3 | P2 | unambiguous | Document commit_music_vo Full-auto default | contract/docs | 7 | no |

## Defaults inventory impact

- information_packages.enable/mode/require_corpus landmines

## target_status

`draft`
