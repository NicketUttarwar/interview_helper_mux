# RSTM (Reachable Stage Trajectory Matrix) — Wave-B

**Campaign:** `RSTM-2026-09-09`  
**Merges:** `FAILURE_CATALOG-2026-09-09`  
**Doctrine:** HEAD-only, no `exec_*`, mock LLM/ML, `MUX_FORENSICS=0`

## Commands

```bash
# enumerate + coverage gate
.venv/bin/python -m tests.rstm.enumerate_matrix

# Wave 8 Done-when scorecard (catalog A–G proofs)
MUX_FORENSICS=0 .venv/bin/pytest tests/rstm/test_residual_cluster_scorecard.py -q --tb=short

# run all cells
MUX_FORENSICS=0 .venv/bin/pytest tests/rstm/ -q --tb=line

# regression packs (after patches)
.venv/bin/pytest tests/test_stage_completion.py tests/test_delivery_guardrails.py \
  tests/test_partial_auto_mode.py tests/test_delivery_thrash_hardening.py -q
```

## Outputs

| Path | Role |
|------|------|
| `CAMPAIGN_META.json` | Wave-B start/finish |
| `matrix.json` / `matrix.md` | Cell list |
| `<repo>/rstm-results/summary.json` | Pass/fail aggregates |
| `<repo>/rstm-results/cells/*.json` | Per-cell (outside `.cursor/` — bulk payload is not IDE-indexed) |
| `../rstm_holistic_report.md` | Wave-A ∪ Wave-B report |
