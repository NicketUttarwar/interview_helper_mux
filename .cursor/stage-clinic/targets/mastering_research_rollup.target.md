# Target Spec — mastering_research_rollup

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| research.llm off | Stub routing + dossier; done if schema-valid | Completes |
| shape-core thin at Pass1 | Consumers refuse resume rollup; rollup re-probes | Unattended may wait on Shape until probes ready — not human |
| stale thin dossier | Rollup incomplete until re-run | same |
| hollow rollup | incomplete | same |

## Rules set

- admit / always after waves seed position
- incomplete / HM-1 + A-01 thin/stale
- refuse / N/A soft-success on thin when Shape binding
- auto_resolve_default / N/A

## Complexity subtraction

- Dual dossier/rollup identical payload writers → single write helper

## Contract deltas

- Add gap consumers to YAML or drop from RESEARCH_CONSUMER doc claim

## Non-goals

- Enabling research.llm by default

## Acceptance checks

- stale latch clears after one re-run; thin refuse pins Shape not EDL

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Keep A-01 refuse; never soft-done thin when Shape binding | existing tests | 1,2 | no |
| B2 | P1 | needs_you | Align contract consumers with RESEARCH_CONSUMER | yaml regen | 7 | no |
| B3 | P2 | unambiguous | Single write for dossier+rollup | unit | 7 | no |

## Defaults inventory impact

- Stage-local: A-01 thin can delay Shape/gap under Full-auto (not human stall)

## target_status

`draft` — Wave 2 applied MRRoll-B1/B3; MRRoll-B2 still `needs_you`
