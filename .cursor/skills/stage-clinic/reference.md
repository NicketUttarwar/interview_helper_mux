# Stage Clinic — reference

## Paste crib

**Discover**
```
/stage-clinic-discover STAGE=<id> BRAIN=0.2.0 MODE=partially_accelerated
Follow .cursor/skills/stage-clinic/SKILL.md
Dossier: .cursor/stage-clinic/dossiers/<id>.md
Write: .cursor/stage-clinic/maps/<id>.possibility.md
Canon: NORTH_STAR.md + docs/cross-cutting/mastering-homunculus.md + docs/cross-cutting/mastering-process.md
L1 only. Code is king. No patches. No ASSETS/executions/.
```

**Target**
```
/stage-clinic-target STAGE=<id>
Follow .cursor/skills/stage-clinic/SKILL.md
Read maps/<id>.possibility.md. Write targets/<id>.target.md (draft OK).
Tag backlog unambiguous|needs_you. Flag FULL_AUTO_REGRESSION_RISK. No patches.
```

**Implement (Wave 2)**
```
/stage-clinic-implement STAGE=<id>
Wave 2 explicit. Read map + target. Patch unambiguous rows only.
Verify without local heavy ML. Update ledger.
```

**Next analysis**
```
/stage-clinic-next-analysis
Follow .cursor/skills/stage-clinic/SKILL.md
```

**Readiness**
```
/stage-clinic-readiness
Follow .cursor/skills/stage-clinic/SKILL.md
```

## Paths

| Artifact | Path |
|----------|------|
| Plan SSOT | `.cursor/plans/stage_clinic.plan.md` |
| Queue | `.cursor/stage-clinic/queue-partial-020.md` |
| Ledger | `.cursor/stage-clinic/ledger.md` |
| Defaults | `.cursor/stage-clinic/defaults_inventory.md` |
| Cross-stage | `.cursor/stage-clinic/cross_stage_patterns.md` |
| Readiness | `.cursor/stage-clinic/full_auto_readiness.md` |
| Templates | `.cursor/stage-clinic/templates/` |
| Per-stage | `dossiers/`, `maps/`, `targets/`, `notes/` |

## Bootstrap

```bash
python tools/bootstrap_stage_clinic.py
```

Idempotent: does not overwrite non-empty maps/targets/notes.

## L1 forced dimensions (reminder)

1. Input completeness  
2. Upstream freshness  
3. Partial-accel gate posture  
4. Execution outcomes  
5. Side effects  
6. Complexity traps (OpenAI/host; not local ML internals)  
7. Contract honesty (declared-vs-actual)  
8. External service variance  
9. **Full-auto / defaults path (required)**  

## Reliability DoD (§0.2)

1. Progression  2. Honesty  3. Stalls  4. OpenAI variance  
5. Defaults  6. Ship bar  7. Cross-stage  

Wave 3 scores each `pass|fail|partial|unknown`.
