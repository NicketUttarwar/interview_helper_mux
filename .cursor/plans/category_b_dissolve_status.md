# Category B dissolve status

Dissolve of exec_13157 systemic Category B (WS1–WS5 + footguns + integrator).
Plan file not modified.

## Definition of done

| WS | DoD | Cascade (`MUX_FORENSICS=0`) |
|---|---|---|
| **WS5** | Sticky halt exits; `resume_producer` never pins sealed consumers when narrative/VO/mix incomplete; interrupt resume prefers ship when `master.wav` exists; dual-driver refuse | `tests/test_category_b_ws5_conductor.py`, `tests/test_p15_attempt_memo.py` |
| **WS1** | Wrong-envelope ≤1 remutate → halt; plan contract; CSP-05 clinic honesty; no soft-heal lie | `tests/test_category_b_ws1_shape.py`, `tests/test_a03_mastering_llm_cutover.py` |
| **WS2** | `resolve_seats` owns demote; coverage≡on_air; floor unmet stamped; layup resume pin | `tests/test_category_b_ws2_highgap.py` |
| **WS3** | Pre-LLM `seam_occupancy`; effective blocking after `contradicted_by_disk`; freeze-safe occupancy | `tests/test_ws3_edl_narrative_disk_gate.py`, `tests/test_i12_narrative_repair_hard_freeze.py` |
| **WS4** | Remap×stage matrix; AST co-writer; `FREEZE_WRITE_POLICY`; checklist in residual | `tests/test_category_b_ws4_ownership.py` |
| **Footguns** | Soft-pass refuse; sealed-consumer pin; ban heal-refuse demote origins; incomplete-after-conductor class | `tests/test_category_b_footguns.py` |
| **Integrator** | Occupancy ALLOW; full suite green; residual wired; write-sites clean | this doc |

## WS5 — Conductor / seed-order / interrupt (5A–G)

- **5A:** EDL resumes resolve through blocking narrative-audit producer (`resume_producer`).
- **5B:** `incomplete_after_conductor` hard fail class; sticky halt exits once (no Phase-A EDL budget burn).
- **5C:** Committed `master.wav` lets `master_finalize` skip mix seed-order rewind.
- **5D:** Refused pre-EDL soft-pass routes to real layup QC producer (no premature sticky credit).
- **5E:** Infra interrupt class; smart-resume finalize/ship when master present.
- **5F:** Sticky halt constrains delivery walk to pin only.
- **5G:** `resume_after_intervene` clears failed/refused memo + sticky for patched stages.
- Dual-driver: live claim refuse second PID on same `run_id`.

## WS1 — Mastering Shape hollow thrash

- Per-artifact schemas (agenda/candidates/rubric); nested envelope unwrap.
- Typed wrong-envelope → one remutate → fingerprinted halt; plan synthesize/confirm use `plan` contract.
- Stage-clinic CSP-05 honesty; Finished-lie capped by one-fail remutate.

## WS2 — High-gap VO seat SSOT

- `HighGapSeat` / `resolve_seats` four-intent authority; compose/lifecycle/driver/playbook folded in.
- Coverage = non-empty non-skipped on-air; floor unmet stamp after demote; heal resume via `high_gap_heal_resume_stage`.

## WS3 — EDL narrative disk-grounded gate

- Pre-LLM `master/seam_occupancy.json` after framing-transition dedupe; ALLOW + freeze-safe write.
- Gates use effective blocking (not contradicted by disk); structured issue codes; transitions-only repair can clear fail.

## WS4 — Ownership / remap / freeze

- SHARED_REMAP × SEGMENT_ID_REMAP_STAGES × epoch matrix; `segment_id_remap` required mutation class.
- AST remap stages + co-writer producers; `FREEZE_WRITE_POLICY` / `freeze_write_allowed`.
- `tools/ownership_new_stage_checklist.py` in residual regress; missing_framing stage_key on flow_adaptation write.
- Matrix docs regenerated.

## Integrator verification (this dissolve)

```text
MUX_FORENSICS=0 pytest
  test_category_b_ws{1,2,4,5}* + test_ws3_edl_narrative_disk_gate
  + test_category_b_footguns + test_p15_attempt_memo
  + test_i12_narrative_repair_hard_freeze + test_a03_mastering_llm_cutover
→ 691 passed

audit_artifact_ownership.py --write-sites-only → unknown_write_sites=0
ownership_new_stage_checklist.py → OK
./scripts/verify_artifact_contract.sh → exit 0
```

Wired into `tools/check_residual_regress.sh`: Category B WS cascades + footguns.

## Anti-footgun locks

- Soft-pass without last-resort → empty mark set.
- `resume_producer(ctx, "edl")` → `edl_narrative_audit` when narrative blocks.
- Compose/lifecycle must not demote with `e2e_heal_lint_dirty` / `post_commit_uncovered_high` string origins.
- `FAIL_CLASS_INCOMPLETE_AFTER_CONDUCTOR` registered; `resume_after_intervene` present; seam_occupancy ALLOW row.
