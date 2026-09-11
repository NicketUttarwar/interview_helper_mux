# Mode matrix — Manual / Full-auto / Partially accelerated

Brain: **0.1.0** (homunculus). Evidence: HEAD only.

## Detection (`automation_run.py`)

| Mode | Detection |
|------|-----------|
| Full-auto | `run_meta.full_auto` or `run_mode` ∈ `{full-auto,fullauto,auto,e2e}` or env `MUX_FULL_AUTO` / `MUX_BABA_E2E` |
| Partial | `run_meta.partial_auto` or `run_mode` ∈ `{partially-accelerated,partial-auto,…}` or env `MUX_PARTIAL_AUTO` |
| Shared driver | `automation_driver_run(meta)` true for either |

## Env / soft flags (`e2e_soft.py`, `identical_failures.py`)

| Flag | Effect |
|------|--------|
| `INTERVIEW_MUX_E2E_SOFT=1` | Gate auto-progress only (G0 / G-Framing / G-Publish) — **not** quality floors |
| `INTERVIEW_MUX_E2E_QUALITY_WAIVERS=1` or `run_meta.e2e_quality_waivers` | Opt-in quality ship waivers |
| `INTERVIEW_MUX_AUTO_ACCEPT_GATES=1` | Auto-accept gate defaults (Full-auto launch sets) |
| `MUX_FORENSICS=1` | **Legacy footgun:** `identical_failures.is_halted()` returns False — thrash can continue |

## Prepare order

| Mode | Early order |
|------|-------------|
| Manual / Full-auto | Typical: `audio_preclean` before ingest (offer still never auto without accept) |
| Partial | `PARTIAL_AUTO_PREPARE_UNTIL_G0` = `ingest → transcribe → transcript_review_build` only; **defers** `audio_preclean` until after G0 (`web/runner.py`) |

## Gate behavior summary

| Gate | Manual | Full-auto | Partial |
|------|--------|-----------|---------|
| G0 | Operator must review | Auto-accept when soft/auto_accept | **Never** auto-accept — operator required |
| G-Framing ladder | Operator Yes/No sticky | Auto-resolve Yes for hosted 1:1 when unset (0.1.0) + soft | Same driver stack; operator can still choose; sticky No protected |
| G1 | Optional skip/synth/record | Automation may synth via Chatterbox | `automation_pending` can suppress NEEDS YOU when chatterbox |
| G-Publish / S3 | Operator | Soft may prepare; S3 still consent when advisories | **Never** auto-upload |
| Overlay busy | N/A | Detached driver | `partialAcceleratedGuard` blocks mis-clicks except checkpoint gates |

## Driver share

Full-auto and Partial share `tools/full_auto_driver.py` / daemon launch. Audit driver **once**; differences are gate accept + S3 + prepare order + overlay.

### XC-MODE-01 — Partial G0 never auto vs Full-auto soft

- Surface: cross-cut / mode
- Modes: all three
- Call graph: `e2e_soft.e2e_soft_enabled` → gate accept paths; Partial checks in runner/gates
- Invariant: Partial never auto-clears G0
- Why weak: shared driver + soft env if mis-set on Partial launch could confuse operators
- Likelihood: L2 · Severity: S3 · Status: OPEN_RISK (config footgun)
- Fix-cluster: `mode-gate-honesty`
- Evidence: `automation_run.py`, `e2e_soft.py`, `web/runner.py` PARTIAL_AUTO_PREPARE_UNTIL_G0

### XC-MODE-02 — Forensics halt suppress legacy

- Surface: cross-cut
- Modes: any if env set
- Call graph: `identical_failures.forensics_mode` → `is_halted` returns False
- Invariant: production Manual/Full-auto/Partial must halt identical×3
- Why weak: leftover `MUX_FORENSICS=1` in shell disables halt
- Likelihood: L2 · Severity: S4 · Status: OPEN_RISK
- Fix-cluster: `identical-halt-honesty`
- Evidence: `identical_failures.py:forensics_mode`
