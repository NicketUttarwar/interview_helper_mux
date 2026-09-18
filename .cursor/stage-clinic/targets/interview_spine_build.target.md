# Target Spec — interview_spine_build

brain: 0.2.0 | target_status: draft  

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| enabled=true (default) | valid spine.json + done | unattended |
| enabled=false | explicit skip stub primary OR seed omit | must not stall |

## Rules set

- admit / when enabled and SAP+transcript complete
- refuse / incomplete SAP
- incomplete / never force-heal without primary or stub
- auto_resolve_default / defaults keep enabled=true

## Complexity subtraction list

- heal_or_refuse_mark(force) without stub when disabled

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| B1 | P0 | confirmed | KEEP skip-stub in seed when disabled (4B) | stub + heal; stay in seed | 1,2,5 | no if stub |
| B2 | P1 | unambiguous | Until B1: disabled path must not call refuse-heal without writing stub | unit test disabled path marks done | 1,2 | no |

## Defaults inventory impact

- interview_spine.enabled default true (landmine if flipped)

## target_status

`draft` — Wave 2 applied ISB-B2 (disabled skip stub); ISB-B1 still `needs_you`
