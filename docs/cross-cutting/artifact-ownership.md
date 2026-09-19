# Artifact ownership constitution

Single allow/deny matrix for every persist, mark_done, unmark, pending promote, and heal resume.

**SSOT:** [`src/interview_mux/artifact_ownership.py`](../../src/interview_mux/artifact_ownership.py)

**matrix_version:** stamped into `run_meta.artifact_ownership_matrix_version` at run create / driver claim. Mid-run code reload with a different hash refuses further mutates.

## Four questions (every remaining bug)

1. What fact changed? (path + field)
2. Who is the owner? (exactly one stage, or ordered co-producers)
3. Who else wrote or resumed it?
4. Patch: owner writes; others refuse or pin the owner (`heal_pin_for`)

## Locked policy

- **Hosted VO floor under hard freeze:** keep already-on-air host lines; never invent seats / CTA holes; unmet floor → pin `nugget_layup_compose` (no `catastrophe_hosted_vo_floor`).
- **Fail-closed** on DENY + unknown paths (`INTERVIEW_MUX_ARTIFACT_OWNERSHIP_FAIL_CLOSED=0` only for archaeology).
- **Empty heal pin never executes** (no delivery rewind / no `music_palette_compose` coalesce when Phase A unsealed).
- **Nested VO under EDL is ALLOW**; flushing `vo_pickup` from non-owner pending is DENY.
- **DENY → refuse-and-pin owner**; identical `authority_denied` ×N sticky-halts.

## ALLOW / DENY

Generated views:

```bash
python -c "from interview_mux.artifact_ownership import render_allow_deny_markdown as r; print(r())"
python tools/audit_artifact_ownership.py [--execution-id exec_N]
python tools/generate_ownership_write_checks.py   # refreshes tools/check_* from matrix
```

Checked-in snapshot: [artifact-ownership-matrix.md](artifact-ownership-matrix.md).

Rerun-safe: owner re-execute ALLOW; consumer re-execute never becomes owner.

## Epochs

`pre_soft_freeze` → `soft_freeze` → `hard_freeze` → `edl_sealed` → `mix_seated` → `junction_committed`

`FREEZE_WRITE_POLICY` names the mutations that may cross seat-freeze boundaries.
Narrative metadata alignment and transition shrink/repair remain legal through
hard freeze; narrative host-copy repair stops at soft freeze, and gap compose
copy stops at hard freeze. Unknown stage/mutation pairs fail closed through
`freeze_write_allowed`.

## Dual-writer queue (Phase 5)

Worked in this constitution land:

| Family | Action |
|---|---|
| End-A ∩ C floor | Removed hard-freeze catastrophe reseat; pin layup |
| End-E pins | `heal_pin_for` + driver empty-pin refuse |
| Analysis scaffold | `_one_writer_raw` SDP registered as ops allowlist |
| Selection alias | `stage_key=selection` ALLOW on `master/selection.json` |

Remaining hunts (register `allowed_mutations` or refuse + fixture): End-B assembly resync nested promote, End-C remutate mint transitions dual-writer, End-D junction exclude, analysis speakers/manifest — cousin coverage in `tests/test_end_cousin_fixtures.py`.

## Mutation verbs

Same matrix for `persist`, `mark_done`, `unmark`, `invalidate`, `promote_pending`, `execute`. Nested VO staging under EDL is ALLOW; foreign pending VO / gap / transitions / selection / plan flush is DENY (`verb=promote_pending`). Glue promote walks owner pending only.

## GUI role

Server routes pass `role="gui"` into `RunContext.write_json`. Gate paths (G0 transcript, G1 gap_report, NLE, SFX prompts, recompute scaffolds, publish) have explicit GUI ALLOW rows. `master/edl.json` is DENY for GUI (JSON + text PUT).

## Audit

`python tools/audit_artifact_ownership.py` fails on unknown write-site literals (AST). `python tools/ownership_new_stage_checklist.py` additionally requires registered literal stages at shared remap call sites and verifies that shared-path co-writer literals are catalog producers. `tools/generate_ownership_write_checks.py` refreshes `check_ownership_matrix.sh`.

Shared remap persists must pass `mutation_class="segment_id_remap"`; producer
authority alone is insufficient. The `SHARED_REMAP_RELS ×
SEGMENT_ID_REMAP_STAGES × epoch` matrix is regression-tested.

## Write bypasses

Prefer `ctx.write_json` / `write_committed_json` (gated). `fs_write_json` / `Path.write_*` / shutil for fingerprints and WAV renderers must not invent new owner facts — register as `write_mode=operational` or bind under owner stage. Production `_one_writer_raw` only on `ONE_WRITER_RAW_ALLOWLIST`.

## Cutover

`matrix_version` mismatch → fresh exec only for plain / soak runs; do not resume in-flight execs across ALLOW seed changes. Under `MUX_FORENSICS=1`, driver claim / persist restamps the live hash so a forensics campaign can continue the same `run_id` after an intentional ownership patch. Fail-closed is default; `INTERVIEW_MUX_ARTIFACT_OWNERSHIP_FAIL_CLOSED=0` is attended emergency escape only. Plain Mohan soak (`MUX_FORENSICS` unset) is tape hardness proof after wave gates.

## Related

- [air-order-boundary.md](air-order-boundary.md)
- [predicate-families-endgame.md](predicate-families-endgame.md)
- [publishability-contract.md](publishability-contract.md)
