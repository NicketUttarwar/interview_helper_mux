# Target Spec — mix

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| edl+SDP+theme+no live incomplete | Seated assembly.wav | Completes |
| live incomplete cuts | Refuse; junction-first | Progresses via junction then mix |
| music_omitted beds | Not treated as missing SFX | Continues |
| completeness fail | incomplete / hard — no hollow done | Honest |
| remaster → g_listen | Clear under Full-auto policy | No permanent human stall |

## Rules set

- admit with `_check_mix` + bookends + mmaudio/omit honesty
- refuse live incomplete cuts (junction_recut_precedes_mix)
- incomplete unseated assembly
- precise remaster without wipe EDL
- auto_resolve_default g_listen for Full-auto only (shared helper; Partial keeps block)

## Complexity subtraction

- Contract soft-edl lie → align hard inputs
- Cap remux; prefer one completeness SSOT
- Do not add Partial pauses to “fix” Full-auto

## Acceptance checks

- junction_recut_precedes_mix golden
- mix_outputs_seated before done
- omit excluded from missing SFX
- no infinite remux

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Align contract hard: edl+SDP | dependency data | 7 | no |
| B2 | P0 | unambiguous | Keep/assert junction-first incomplete-cut invariant | thrash tests | 1 | no |
| B3 | P0 | done | Full-auto g_listen auto-clear vs default warn | shared helper after mix arm + finalize | 3,5 | no (Full-auto fixed; Partial keeps block) |
| B4 | P1 | done | VO soft vs SFX hard under creative_delivery | keep as-is (operator) | 6 | no |
| B5 | P1 | unambiguous | Drop llm_execute from mix lifecycle | YAML | 7 | no |

## Defaults inventory impact

- g_listen_mode=block; post_listen block_mix; completeness_gate — landmines

## target_status

`draft`
