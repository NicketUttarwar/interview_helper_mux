# 07 FINISH — Sign-off

**Sequence step:** **07** · FINISH — [00-INDEX.md](./00-INDEX.md)  
**Previous:** Steps **01–06** must be `[x]`  
**Reference:** [definition-of-done-signoff.md](../definition-of-done-signoff.md)

---

## Agent execution contract

### Purpose

Close the June 2026 build sequence: confirm waves shipped coherently, docs indexed, manual sign-off path clear, and no regression vs shipped BUILD waves 1–7.

### Prerequisite gate

- [x] 00-INDEX.md steps **01–06** are `[x]`
- [x] Each wave spec’s promotion gate sections satisfied or waived with rationale

### How to invoke

1. **New Cursor Agent chat** (docs + light fixes only — no large new features).
2. **`@`-attach** this file and [Required attachments](#required-attachments).
3. Send the [Agent directive](#agent-directive).

### Agent directive

```text
Complete June 2026 build finish per the attached 07-FINISH-signoff.md.

Verify cross-wave consistency: 00-INDEX.md steps **01–06** marked `[x]`; step-file todos closed or waived;
INDEX.md and AGENTS.md link june182026build, pytest green, audit_stage_plans_doc.py clean.
Update definition-of-done-signoff.md checkboxes where automated checks already pass.
Document any remaining manual listen / nine-scenario items for the operator.
```

### Required attachments

| Path | Role |
|------|------|
| `docs/build-out/june182026build/07-FINISH-signoff.md` | **This session** |
| `docs/build-out/june182026build/00-INDEX.md` | Status |
| `docs/build-out/june182026build/02-WAVE-0-resilience-harness.md` | Wave 0 gate reference |
| `docs/build-out/june182026build/06-WAVE-D-output-resilience.md` | Nine-scenario / recovery |
| `docs/build-out/definition-of-done-signoff.md` | Release checklist |
| `docs/build-out/testing-and-verification.md` | Verify layers |
| `docs/build-out/repository-map.md` | Doc ↔ code gaps |
| `docs/INDEX.md` | Hub links |
| `AGENTS.md` | Agent navigation |
| `.cursor/rules/interview-helper-mux.mdc` | Constraints |

### Finish checklist

- [x] **F-01** `00-INDEX.md` steps **01–06** all `[x]`
- [x] **F-02** `pytest tests/ -q` green (727 passed, 2026-06-18)
- [x] **F-03** `python tools/audit_stage_plans_doc.py` passes
- [x] **F-04** `./tools/check_prerequisites.sh` passes or waivers documented in `anchored-toolchain.md`
- [x] **F-05** [INDEX.md](../../INDEX.md) links `june182026build/00-INDEX.md`
- [x] **F-06** [AGENTS.md](../../../AGENTS.md) lists June 2026 build path
- [x] **F-07** [implementation-guide.md](../implementation-guide.md) references june182026build (optional paragraph)
- [x] **F-08** No open **operator-facing** rows in [repository-map.md](../repository-map.md) for June 2026 scope
- [x] **F-09** [definition-of-done-signoff.md](../definition-of-done-signoff.md) — operator completes manual sections 1–5 when ready (agent documents what remains)
### Cross-wave regression smoke

```bash
source .venv/bin/activate
pytest tests/ -q
python tools/audit_stage_plans_doc.py
./tools/check_prerequisites.sh
# Optional on real exec_* fixture:
# python tools/run_analysis.py --run-id <exec_*>
# python tools/run_delivery.py --flow flow1 --run-id <exec_*>
# python tools/verify_master.py <run>/master/master.wav
```

### Definition of done

- [x] F-01 through F-09 complete or explicitly listed as **operator manual follow-up**
- [x] 00-INDEX.md step **7** marked `[x]`
- [ ] Maintainer sign-off record in [definition-of-done-signoff.md](../definition-of-done-signoff.md) (operator initials / date when manual listen done)

### Operator manual follow-up (after code complete)

June 2026 steps **01–07** code and automated CI are complete. The operator or maintainer still completes these on a real `exec_*` fixture:

| Item | Doc | Action |
|------|-----|--------|
| ASSETS picker + resume | [definition-of-done-signoff.md](../definition-of-done-signoff.md) §1 | GUI new execution, ingest, stop/restart server |
| G2 all three flows | §2 | flow1 / flow2 / flow3 GUI + CLI |
| Master listen + LUFS | §3 | `verify_master.py` on flow1/2 masters; beds/VO audible |
| Pre-clean offers | §4 | At least one dismiss; optional accept |
| Nine-scenario listen | §6 | Spot-check atlas buckets on real runs (automated fixture subset already green) |
| Prosody diversity | [02-WAVE-0 §4](./02-WAVE-0-resilience-harness.md#4-prosody--delivery-guardrails) SC-12 | ≥2 hard-listener clips (quiet/disfluent/noisy) |
| COM retell / LEX-B / Flow 2 hook | [06-WAVE-D](./06-WAVE-D-output-resilience.md) D-W29–31 | Post-ship listen protocols |
| Wave D Shipped default-on | [06-WAVE-D §13](./06-WAVE-D-output-resilience.md#13-wave-d-promotion-gate-for-shipped-default-on) | No config flip until nine-scenario listen + §13 on fixture |

### After this step

June 2026 sequential build is **complete** for code. Remaining work is **operator manual** sign-off (nine-scenario listen, fresh-clone smoke on three flows) per definition-of-done.
