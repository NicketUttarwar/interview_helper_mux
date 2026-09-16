# Exec 11630 major-errors status (HEAD as of 2026-09-15)

**Run:** `exec_11630_d19c15b58ab4_20260915T033341Z` (operator said “16630” — no such folder; this is the forensics campaign).  
**Outcome then:** shipped locally 72/72; 25 product interventions; 26 driver restarts.  
**Sources:** `operator/forensics_errors.json` (2000 entries / 26 unique predicates), `identical_failures.json`, `EXECUTION_REPORT.md`, End-A…F ledger, HEAD fixtures.

**Companion constitution:** [residual-closure-constitution.md](./residual-closure-constitution.md) · inventories [residual-inventories.md](./residual-inventories.md) · seal ledger [predicate-families-endgame.md](./predicate-families-endgame.md) (End-A…F closed; no End-G).

## Status key

| Status | Meaning for a fresh same-source full-auto |
|--------|-------------------------------------------|
| **RESOLVED** | Failure mode should not recur as thrash |
| **RESIDUAL** | Thrash fixed; one-shot / cascade / correct-gate log still possible |
| **INTENTIONAL_GATE** | By design — may log until producer completes or operator consents |
| **STILL_LIKELY** | Same class likely fires again without further work |

Product residual campaign R1–R7 is **closed** on HEAD (`tests/test_r1_*.py` … `tests/test_r7_*.py` green under `MUX_FORENSICS=0`). No `IN_PROGRESS` product residuals remain.

## Dominant thrash (~90% of error volume)

| # | Error | Then | Today |
|---|-------|------|-------|
| 1 | Opening orientation `audible_count=0` → HARD stall ×600+ | Campaign End-A + revive under freeze | **RESOLVED** — `tests/test_r1_orientation_heal_pin.py`; thrash should not return; one-shot miss → HARD escalate to named producer still possible |

## Deduped major failures (31)

| # | Error | Today | Why / fixture |
|---|-------|-------|---------------|
| 1 | Opening orientation thrash | **RESOLVED** | End-A allowlist + revive; `test_enda_*`, `test_opening_orientation`; **R1** `tests/test_r1_orientation_heal_pin.py` |
| 2 | `run_golden_facts` pending_only | **RESOLVED** | `heal_or_refuse_mark` flush; `test_stage_completion_heal` |
| 3 | `missing_framing` batch_fill (LLM must score N) | **INTENTIONAL_GATE** | HG-3 refuse done until score/CAP; `test_hg3_*` |
| 4 | Framing coverage exhausted → needs_operator | **RESOLVED** | CAP seals leftovers; `test_hg3_*coverage_exhausted*` |
| 5 | `analysis:premature_complete:missing_framing` | **RESOLVED** | Cascade of #3/#4 sealed |
| 6 | `gap_evaluations` newer uncommitted pending | **RESOLVED** | Foreign-pending ignore + flush; `test_write_staging` |
| 7 | Transition lands on late opening `seg_005` | **RESOLVED** | Sanitize imports `artifact_repairs.prune_reverse_jump_*` loud; `test_sanitize_transitions_prunes_reverse_jump` |
| 8 | `transitions_unsanitary:stamp_pair_freeze` | **INTENTIONAL_GATE** | Allowlisted under freeze; one-shot until stamp commits |
| 9 | Redundant framing transition | **RESOLVED** | framing_dedupe + heal; **today:** import failure now loud (`framing_dedupe_failed`) |
| 10 | `exclude_rationales` vs ordered ids | **RESOLVED** | Selection sanitize prune fixtures |
| 11 | Blank kids `seg_003a`/`003j` on timeline | **RESOLVED** | Blank drop under freeze / unstamped short = blank; story_keep_ok may legally stay |
| 12 | Spoken scaffolding / forward-cue on orientation | **RESOLVED** | Heal rewrite exists; **R2** `tests/test_r2_scaffold_sanitize.py` |
| 13 | `spoken_copy_guard` block on required VO | **RESOLVED** | `repair_gap_report` → `raise_loud_failure` / pin compose (not ValueError thrash) |
| 14 | Nugget layup authority (compose origins) | **RESOLVED** | Layup authority lint + scrub; `test_nugget_layup` |
| 15 | `vo_unsanitary` / bind_stale / G1 missing | **RESOLVED** | End-B discard stale pending; **R3** `tests/test_r3_vo_family.py` |
| 16 | Gap VO missing WAV layup 005/020 | **RESOLVED** | Classifies `vo_seated_coverage`; fail_class `vo_g1`; **R3** `tests/test_r3_vo_family.py` |
| 17 | `vo_seated_coverage` / premature vo_g1 | **RESOLVED** | Pins synth not soft EDL; **R3** `tests/test_r3_vo_family.py` |
| 18 | `edl_narrative:vo_g1` QC-before-EDL | **INTENTIONAL_GATE** | Strict QC by design; End-C wrong-heal stopped |
| 19 | EDL speech ≠ selection order (narrative QC prose) | **RESOLVED** *(was STILL_LIKELY)* | **today:** prose + `edl_narrative_audit` → `selection_edl_order_drift` |
| 20 | Repeated `seed_order_prereq` | **RESOLVED** | End-E named producer pins |
| 21 | `premature_complete:music_epoch` | **RESOLVED** | HX-1/HX-4 epoch pins; **R4** `tests/test_r4_premature.py` |
| 22 | `premature_complete:phase_a_edl` | **RESOLVED** | Soft-pass refuse; **R4** `tests/test_r4_premature.py` + `test_soft_pass_pre_edl_refuse` |
| 23 | `assembly_preview` missing `edl.json` | **INTENTIONAL_GATE** | Cascade until EDL writes |
| 24 | `mix_seat` / incomplete assembly | **RESOLVED** | End-D reseat; **R5** `tests/test_r5_mix_seat.py` |
| 25 | EDL heal `budget_exhausted` | **RESOLVED** | Ceiling remains; **R6** `tests/test_r6_edl_budget.py` |
| 26 | Hollow `junction_snip_qa` before finalize | **RESOLVED** | End-D commitment match required |
| 27 | PMQ floors + `omit_ledger_air_contract` | **RESOLVED** | End-F live pack + i25; **R7** `tests/test_r7_pmq_honesty.py` |
| 28 | Commitment remaster `low_gain` refuse | **RESOLVED** | i24/End-D bypass |
| 29 | `host_vo_duration` under floor | **INTENTIONAL_GATE** | Aspirational listenability; no auto-thicken |
| 30 | S3 blocked on quality advisories | **INTENTIONAL_GATE** | G-Publish consent |
| 31 | Stale e2e brief on soft-stub refuse | **INTENTIONAL_GATE** | Production parity signal, not ship hole |

## Intentional gates (document only — never greenwash)

These surfaces may still appear on a healthy full-auto. Softening them recreates thrash or ships illegal masters. Full anti-footgun list: [residual-closure-constitution.md](./residual-closure-constitution.md).

| ID | Gate | Footgun if “fixed” |
|----|------|-------------------|
| #3 | HG-3 `missing_framing` batch_fill refuse until LLM scores / CAP | Fake completeness / silent `stage_done` |
| #8 | `stamp_pair_freeze` needs_sanitize flash | Freeze thrash / illegal mutate under hard freeze |
| #18 | Narrative QC-before-EDL (`edl_narrative:vo_g1`) | Soft-pass glue lies; recovered-EDL while unsanitary |
| #23 | `assembly_preview` needs `edl.json` | Hollow preview theater |
| #29 | `host_vo_duration` advisory under floor | Auto-thicken vs freeze + narrative economy |
| #30 | S3 blocked while `quality_advisories` non-empty | Bypass G-Publish consent |
| #31 | e2e brief when soft/stub refuse fires | Hide production-parity refuse |
| — | **Preclean** never auto-run | Operator gate violation ([operator-gates.md](../workflows/operator-gates.md)) |
| — | Operator **G-Framing No** sticky | Unattended overwrite of human choice (HC-5/6) |
| — | **Catastrophic listen floors** hard-stop | Soft-proceed below catastrophe |
| — | **Tier-0 publishability** (zero keeps, phantom VO, order drift, orientation audible) | Ship illegal master |
| — | **Pending `master.wav` ≠ shipped** | False ship bar / premature G-Publish |

## Anti-footgun constitution (summary)

Every residual patch must satisfy all of:

1. No End-G / no reopen End-A…F — cousins in `tests/test_end_cousin_fixtures.py` or `tests/test_r*_*.py`.
2. Producer heal only — never soft-complete sealed `edl` / `mix` / `master_finalize` on hollow producers.
3. No LAST_RESORT soft, MusicGen stub, soft listenability, or e2e quality waivers in full-auto production parity.
4. No floor lowering (PMQ clarity, `host_vo_duration`); omit ledger stays structural.
5. No auto-S3 on advisories; no auto-thicken hosted VO under hard freeze.
6. No omit of required opening orientation to silence scaffold.
7. No broadening `infer_heal_intent` `"edl" in text` without VO denylist (#16).
8. No product `suppress_budget_exhausted`; no blind EDL→`TRANSIENT_ERROR_CLASSES`.
9. Ownership fail-closed; new persist/stage/`from_stage`/GUI writer → ALLOW row same change.
10. Empty heal pin refuses execute — no delivery rewind / music coalesce when Phase A unsealed.
11. Closable residuals get `MUX_FORENSICS=0` cascade fixtures.
12. Intentional gates stay honest — document; do not soft them away.

## Workflow residual map (ingest → ship)

| Band | What can still bite | HEAD posture |
|------|---------------------|--------------|
| **G0 / ingest** | Hollow `transcript_review_build`; heal pin build/gate | HP-* fixtures; residual soak after GUI changes |
| **Preclean** | Auto-run or hollow unmark clearing `preclean/skip.json` | Intentional never-auto; HP-3 |
| **Analysis / framing** | HG-3 batch refuse; G-Framing No sticky; golden-facts pending; hitch lattice | #3 intentional; CAP/#4 resolved; hitch sticky covered in `test_r_workflow_residual` |
| **Selection / transitions / omit** | Reverse-jump, pair-freeze flash, exclude prune, ghost omit path | Loud sanitize + End-A; ghost `master/omit_ledger.json` forever `unknown_path` |
| **Layup / VO / G1 / bind** | Stale promote, missing WAV, premature vo_g1, orientation inaudible | End-B + **R1–R3 RESOLVED** |
| **Phase A / EDL / QC / preview** | QC-before-EDL, order drift, hollow seed, soft_pass `[]` | #18/#23 intentional; speech-order cousin landed; **R4 RESOLVED** |
| **Music / mix / junction** | Music epoch sticky, mix_seat, hollow junction, G-Listen re-arm | HX-* fixtures; **R5 RESOLVED** |
| **Heal budget / identical / agenda** | `budget_exhausted` no-op loop; sticky false progress | **R6 RESOLVED** |
| **Finalize / PMQ / G-Publish** | Clarity honesty, host_vo advisory, S3 consent, e2e brief | End-F + i25; #29–31 intentional; **R7 RESOLVED** |

## Remaining R\* work status (HEAD-accurate)

End-A…F + i24/i25 + soft-pass + hollow-seed + ownership cousins + **R1–R7** landed under `MUX_FORENSICS=0`. Product residual campaign **closed**.

| Family | Exec # | Status on HEAD | Fixture |
|--------|--------|----------------|---------|
| R1 orientation driver pin | #1 | **RESOLVED** | `tests/test_r1_orientation_heal_pin.py` |
| R2 scaffold id + rewrite-not-omit | #12 | **RESOLVED** | `tests/test_r2_scaffold_sanitize.py` |
| R3 VO / G1 / bind / fail_class | #15–17 | **RESOLVED** | `tests/test_r3_vo_family.py` |
| R4 soft-pass / music sticky / empty pin | #21–22 | **RESOLVED** | `tests/test_r4_premature.py` |
| R5 mix_seat cousins | #24 | **RESOLVED** | `tests/test_r5_mix_seat.py` |
| R6 first-heal fingerprint | #25 | **RESOLVED** | `tests/test_r6_edl_budget.py` |
| R7 PMQ honesty | #27 | **RESOLVED** | `tests/test_r7_pmq_honesty.py` |

Regress harness: `tools/check_residual_regress.sh` · tape preflight: `tools/tape_acceptance_preflight.sh`.

## Ownership fail-closed (post-11630 HEAD blocker)

| Path | Status |
|------|--------|
| `master/air_order.json` | **FIXED** — ALLOW for `edl` / `mix` / `junction_snip_qa`; i24 green |
| `understanding/omit_ledger.json` | **FIXED** — ALLOW for sanitize/layup owners |
| `master/omit_ledger.json` | Ghost path (not written); forever `unknown_path` — do not ALLOW |

Write-site audit (`audit_artifact_ownership.py --write-sites-only`): **0 unknown** — see [residual-inventories.md](./residual-inventories.md).

## Fixture suite (MUX_FORENSICS=0)

End-A…F + i24/i25 + HG-3 + opening_orientation + ownership + cousins + soft-pass + hollow-seed + **R1–R7** + workflow residual: **green**.  
Cousin / residual modules:

- `tests/test_end_cousin_fixtures.py` — End-* ownership cousins + exec_11630 classify + ghost omit / nested VO / junction / speakers·manifest
- `tests/test_r1_orientation_heal_pin.py` … `tests/test_r7_pmq_honesty.py`
- `tests/test_r_workflow_residual.py` · `tests/test_r_schema_parity.py` · `tests/test_r_gui_attended.py`

## Bottom line for next Mohan full-auto

Expect **no 11630-scale orientation / VO / PMQ thrash**. Expect occasional **intentional** surfaces: sparse framing batch refuse (#3), pair-freeze stamp (#8), QC-before-EDL (#18), host-VO advisory → S3 consent (#29–30), and e2e brief noise (#31). Residual one-shots (#1/#12/#15–17/#21/#24/#27) heal to the named producer — R\* fixtures closed.

Tape acceptance: `./tools/tape_acceptance_preflight.sh` then one plain full-auto with `MUX_FORENSICS` unset (see constitution).
