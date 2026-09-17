# Target Spec — audio_probe_build

brain: 0.2.0 | target_status: draft  

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| build ok | 5 artifacts + done | shadow+fail_open as today unless honesty raised |
| build fail fail_open | empty artifacts + done vs refuse | decide honesty bar |
| ownership | producers list names audio_probe_build for zones/flows/probe_report | no DENY thrash |

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| B1 | P0 | unambiguous | Ownership producers for protected_zones/speaker_flows/probe_report/audio_tags include audio_probe_build (keep operational if needed) | ownership xcheck | 2,7 | no |
| B2 | P1 | needs_you | fail_open empty golden_facts: keep vs refuse | ship bar intent | 2 | yes if refuse |
| B3 | P2 | unambiguous | Drop unused soft inputs (master/edl/…) from contract | dependency data | 2 | no |

## target_status

`draft`
