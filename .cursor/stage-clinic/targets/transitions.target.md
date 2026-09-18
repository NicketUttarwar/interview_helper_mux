# Target Spec — transitions

brain: 0.2.0 | target_status: applied

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| LLM ok | guarded transitions persist | Completes |
| LLM exhaust | refuse/incomplete OR empty persist (min_rows 0) | Completes with empty OK |
| G1 open/skip | pair freeze stamp | Continues to VO/G1 |
| empty ok? | **YES** — min_rows 0 (operator binding) | Completes |

## Rules set

- admit / schema+guard ok
- refuse / LLM fail (or empty commit on final attempt)
- incomplete / hollow that breaks edl glue
- precise invalidate / declared list
- **B1 KEEP:** empty transitions allowed (min_rows 0)

## Complexity subtraction

- Keep post-filters; avoid dual writers

## Non-goals

- Wave 1 patches; no refine ghost revive

## Acceptance checks

- spoken_copy_guard; pair freeze; no thrash on order repair
- sufficiency min_rows 0 pin

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | answered | KEEP empty OK (min_rows 0) | contract pin | 2,5 | n/a kept |
| B2 | P1 | unambiguous | Align hard inputs with payload needs | contract | 2 | no |
| B3 | P1 | unambiguous | ADG invalidates match contract | ADG test | 7 | no |

## Defaults inventory impact

- G1 skip → pair freeze landmine for vo_synthesize
- Empty transitions allowed under Full-auto (B1 KEEP)

## target_status

`applied`
