---
name: stage-clinic
description: >-
  Stage Clinic for interview_helper_mux: Wave 0–3 discover/target/implement/readiness
  under brain 0.2.0. Code is king; analysis-first; no product patches in Wave 1;
  Full-auto-on-defaults end-state. Invoke with /stage-clinic-* paste commands.
disable-model-invocation: true
---

# Stage Clinic

Campaign SSOT: [.cursor/plans/stage_clinic.plan.md](../../plans/stage_clinic.plan.md)  
Pack root: [.cursor/stage-clinic/](../../stage-clinic/)

## Non-negotiable doctrine

- Brain **0.2.0 only**. No other brain ids. No control-plane revival framing.
- **Code is king.** Docs/contracts/plans are claims. Tag: `IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN`.
- **Prior `exec_*` / forensics run dirs:** default ignore. At most messy hints if operator points; verify-or-drop on HEAD. Never browse `ASSETS/executions/` unprompted.
- **Local heavy ML ignored:** Chatterbox, MusicGen, MMAudio, DeepFilter, MLX STT, local LLM framer, CLAP-in-venv — one-line boundary note only; no tests; no venv work. Host honesty (done-without-artifact) still in scope.
- **OpenAI / external services in clinic:** prompts, schemas, retries (≤2), accept/hollow/done honesty, packet denylist.
- **Campaign end-state:** unattended **Full-auto on shipped defaults**. Partial is for seeing gates; do not ship partial-only fixes that regress Full-auto (`FULL_AUTO_REGRESSION_RISK`).
- **Wave split:** Wave 1 = analysis only (no product patches). Wave 2 = implement only on explicit `/stage-clinic-implement`. Wave 3 = readiness rollup (no patches, no exec_*).

## Evidence pack load order (every discover)

1. §5.0 index card on dossier  
2. Body + rails (authority)  
3. Contract / ADG / ownership (claims → verify)  
4. Schemas / StageInfo / OpenAI prompts  
5. Gates / GUI / partial lists  
6. Config flags touching this stage  
7. Tests + TEST_GAP (exclude local-ML tests)  
8. Write Possibility Map  

Pack complete only when index + body/rails + declared-vs-actual matrix + flag list + TEST_GAP exist (N/A with reason OK).

## Commands

### Discover (Wave 1)
```
/stage-clinic-discover STAGE=<id> BRAIN=0.2.0 MODE=partially_accelerated
L1 only. Code is king. Write maps/<id>.possibility.md. Include full-auto/defaults dimension. Ask sparingly. No patches.
```

### Target (Wave 1 draft OK)
```
/stage-clinic-target STAGE=<id>
Read map + canon claims. Prefer deterministic rules. Backlog rows: unambiguous|needs_you. Do not patch.
```

### Implement (Wave 2 only)
```
/stage-clinic-implement STAGE=<id>
Wave 2. Patch unambiguous backlog only; stop on needs_you unless answered. No local-ML tests. Update ledger.
```

### Continue
```
/stage-clinic-continue STAGE=<id> LAYER=L1|L2|L3
My answers (optional): ...
```

### Next analysis
```
/stage-clinic-next-analysis
Read queue + ledger. Next L1 incomplete stage. Discover only. No patches.
```

### Readiness (Wave 3)
```
/stage-clinic-readiness
Score §0.2 DoD into full_auto_readiness.md. No patches. No exec_* reads.
```

## Layer stop rules

| Layer | May write | Must not |
|-------|-----------|----------|
| L1 | `maps/`, dossier index, `notes/` Qs, ledger L1 | product code, targets as “done implement”, L3 |
| L2 | `targets/` draft, defaults_inventory impact notes | product code |
| L3 | product code per target backlog, ledger L3 | discover-scope expansion, local ML tests, fresh forensics |
| Wave 3 | `full_auto_readiness.md` | product code, exec archaeology |

Refuse `/stage-clinic-implement` unless Wave 2 intent is explicit and a map + target exist.

## Canon (claims)

- `NORTH_STAR.md`
- `docs/cross-cutting/mastering-process.md`
- `docs/cross-cutting/publishability-contract.md`
- `docs/cross-cutting/mastering-homunculus.md`
- `docs/workflows/operator-gates.md`
- Stage contract YAML + ownership (verify vs code)

## Verify (L3 only)

- Stage pytest **without** local heavy ML
- `./scripts/verify_artifact_contract.sh` if contracts/ownership touched
- No `MUX_FRESH` forensics to prove a single stage

## Ledger updates

After each layer, update `.cursor/stage-clinic/ledger.md` columns: wave, L1_map, L2_target, L3_patch, simplified_to_rules, open_questions, blocked_on.

See [reference.md](reference.md) for paste crib and template pointers.
