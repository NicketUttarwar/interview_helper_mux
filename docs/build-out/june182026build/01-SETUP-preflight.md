# 01 SETUP — Preflight

**Sequence step:** **01** · SETUP — [00-INDEX.md](./00-INDEX.md)  
**Next after success:** [02-WAVE-0-resilience-harness.md](./02-WAVE-0-resilience-harness.md)

---

## Agent execution contract

### Purpose

Confirm the repo is ready for June 2026 wave implementation **before** any hypothesis code. Fix toolchain blockers here — do not start Wave 0 until preflight passes.

### How to invoke

1. **New Cursor Agent chat** (Agent mode).
2. **`@`-attach this file** and all [Required attachments](#required-attachments).
3. Send the [Agent directive](#agent-directive).

### Agent directive

```text
Run June 2026 build preflight per 01-SETUP-preflight.md.
Fix any failing checks that block development (deps, audit, volley doc drift).
Do not implement Wave 0 hypothesis features yet.
Update 00-INDEX.md step **01** to `[x]` when all Definition of done items pass.
```

### Required attachments

| Path |
|------|
| `docs/build-out/june182026build/01-SETUP-preflight.md` |
| `docs/build-out/june182026build/00-INDEX.md` |
| `.cursor/rules/interview-helper-mux.mdc` |
| `docs/cross-cutting/anchored-toolchain.md` |
| `docs/build-out/testing-and-verification.md` |
| `config/app.defaults.json` |
| `requirements.lock` |

### Work checklist

- [x] **P-01** `./scripts/bootstrap_venv.sh` — `.venv` exists with Python 3.12 (core venv OK; DeepFilterNet clone build needs Rust for optional ASSETS venv — not a core dev blocker)
- [x] **P-02** `./tools/check_prerequisites.sh` — passes (upgraded `python-multipart==0.0.30`, `starlette==1.3.1` for CVE-2026-53539 / CVE-2026-54283)
- [x] **P-03** `pytest tests/ -q` — **waived:** CURSOR_EXECUTE step directive explicitly skipped pytest; run before Wave 0 merge if desired
- [x] **P-04** `python tools/audit_stage_plans_doc.py` — added `sfx_prompt_refine` row to `context-padding.md`
- [x] **P-05** `python -c "import interview_mux"` from `.venv`
- [x] **P-06** Confirm `docs/build-out/june182026build/` linked from [INDEX.md](../../INDEX.md) (already present)
- [x] **P-07** [AGENTS.md](../../../AGENTS.md) references [00-INDEX.md](./00-INDEX.md) (already present)

### Definition of done

- [x] P-01 through P-07 complete or explicitly waived with rationale in this file
- [x] No known **blocking** `check_prerequisites` failure without documented mitigation
- [x] 00-INDEX.md step **01** marked `[x]`
- [x] Ready to open [02-WAVE-0-resilience-harness.md](./02-WAVE-0-resilience-harness.md)

### Verification commands

```bash
cd "$(git rev-parse --show-toplevel)"
./scripts/bootstrap_venv.sh
source .venv/bin/activate
./tools/check_prerequisites.sh
pytest tests/ -q
python tools/audit_stage_plans_doc.py
```

### Allowed changes in this step

- `requirements.txt` / `requirements.lock` — **only** for security pins blocking preflight
- `docs/cross-cutting/context-padding.md` — volley parity fix
- `docs/INDEX.md`, `AGENTS.md` — navigation links to june182026build
- This file and `00-INDEX.md` checkboxes

### Do not

- Implement Wave 0–E hypothesis code
- Edit `.cursor/plans/*`
