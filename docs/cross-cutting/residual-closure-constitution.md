# Residual closure constitution (post End-A…F)

Application-wide residual campaign after the End-A…F seal. Closes remaining one-shot residuals, ownership cousins, parity footguns, hollow seeds, heal mis-pins, and GUI/operator gaps across ingest→ship — **without** inventing End-G or greenwashing intentional gates.

**Status SSOT:** [exec-11630-major-errors-status.md](./exec-11630-major-errors-status.md)  
**Inventories:** [residual-inventories.md](./residual-inventories.md)  
**Seal ledger (do not reopen):** [predicate-families-endgame.md](./predicate-families-endgame.md)  
**Doctrine:** [NORTH_STAR.md](../../NORTH_STAR.md) · [publishability-contract.md](./publishability-contract.md) · [artifact-ownership.md](./artifact-ownership.md) · [operator-gates.md](../workflows/operator-gates.md)

---

## Intentional gates (never soft away)

| ID | Gate | Footgun if “fixed” |
|----|------|-------------------|
| #3 | HG-3 `missing_framing` batch_fill refuse | Fake LLM completeness |
| #8 | `stamp_pair_freeze` needs_sanitize flash | Freeze thrash / illegal mutate |
| #18 | Narrative QC-before-EDL | Soft-pass glue lies |
| #23 | `assembly_preview` needs `edl.json` | Hollow preview theater |
| #29 | `host_vo_duration` advisory | Auto-thicken vs freeze + narrative economy |
| #30 | S3 blocked on advisories | Bypass G-Publish consent |
| #31 | e2e brief on soft refuse | Hide production-parity refuse |
| — | Preclean never auto-run | Operator gate violation |
| — | Operator G-Framing **No** sticky | Override human choice |
| — | Catastrophic listen floors hard-stop | Soft-proceed below catastrophe |
| — | Tier-0 publishability (zero keeps, phantom VO, order, orientation) | Ship illegal master |
| — | Pending `master.wav` ≠ shipped | False ship bar |

---

## Anti-footgun constitution

A “fix” that violates any of these is rejected:

1. **No End-G / no reopen End-A…F** — cousins go to `tests/test_end_cousin_fixtures.py` or `tests/test_r*_*.py`.
2. **Producer heal only** — never soft-complete sealed `edl` / `mix` / `master_finalize` on hollow producers.
3. **No LAST_RESORT soft**, MusicGen stub, soft listenability, or e2e quality waivers in full-auto production parity.
4. **No floor lowering** (PMQ clarity, `host_vo_duration`) and no moving `omit_ledger_air_contract` into soft rubric.
5. **No auto-S3** on advisories; no auto-thicken hosted VO under hard freeze.
6. **No omit of required opening orientation** to silence scaffold (recreates #1).
7. **No broadening** `infer_heal_intent` `"edl" in text` without VO denylist (reopens #16).
8. **No product `suppress_budget_exhausted`**; no blind EDL→`TRANSIENT_ERROR_CLASSES`.
9. **Ownership fail-closed on**; new persist/stage/`from_stage`/GUI writer → ALLOW row same change ([artifact_ownership.py](../../src/interview_mux/artifact_ownership.py)).
10. **Empty heal pin refuses execute** — no delivery rewind / no music coalesce when Phase A unsealed.
11. **Every closable residual** gets `MUX_FORENSICS=0` cascade fixture asserting pin/predicate flip.
12. **Intentional gates stay honest** — document; do not soft them away (table above).

---

## Workflow residual map (ingest → ship)

```text
G0 → Preclean → Analysis/Framing → Selection/Transitions/Omit
  → Layup/VO/G1/Bind → Phase A/EDL/QC/Preview → Music/Mix/Junction
  → Heal budget/Identical → Finalize/PMQ → G-Publish
```

Cross-cuts every band: ownership fail-closed, hollow `stage_done` refuse, heal pin honesty, soft-pass parity (`verify_full_auto_env.sh`).

See the status doc workflow table for HEAD posture per band.

---

## Regress + tape acceptance

```bash
./tools/check_residual_regress.sh
./tools/tape_acceptance_preflight.sh
```

**Tape acceptance (campaign close):**

1. Preflight: `./tools/tape_acceptance_preflight.sh` (residual regress + ownership audit + `verify_full_auto_env.sh`) green.
2. ≥1 plain Mohan full-auto with **`MUX_FORENSICS` unset** (not a forensics campaign).
3. Ship bar: `master.wav` + verify_master + PMQ `publish_allowed` + local package.
4. No End-A…F-class thrash, no `AuthorityDenied` `unknown_path`, no soft stubs.
5. Expect **#29–#31** advisory/consent noise — do not reopen as product bugs.
