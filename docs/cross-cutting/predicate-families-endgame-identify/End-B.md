# End-B identify (sidecar)

- **Family:** Bind / promote authority
- **Status suggestion:** partial
- **Plain-language failure:**
  Seated synthesize lines must stay bind-honest (omit ledger + sha-bound WAV). No consumer — EDL glue, gap repair, or pending promote — may seat or flush bytes that fail bind; heal must pin `vo_synthesize` and never soft-complete EDL. Classic cousins are sealed by F2 / HV-2 / HE-2; the remaining HEAD cousin is **owner** `vo_synthesize` flush / orphan commit promoting stale pending over a sha-bound take after `promote_owner_vo_pickup` already skipped it (exec_11630 surface #3: `seated_bind_stale` + G1 / gap VO missing WAV thrash).
- **Example predicates:**
  `seated_bind_stale`; `vo_unsanitary`; `gap VO lines missing WAV` / `edl: gap VO lines missing WAV`; `vo_seated_coverage`; `VO coverage not rendered`; `G1 VO pickup missing` / `missing_g1_pickup`; `Synthetic VO script/WAV mismatch`; coverage-ladder / `edl_vo_coverage_ladder`
- **Producer stage(s):**
  `vo_synthesize` (owner promote / flush), `edl` (consumer refuse + nested resync/heal), `g1_vo_pickup` (pickup gate), write_staging promote/flush (cross-cutting)
- **HEAD proof (file:function):**
  - `write_staging.py:flush_stage_writes` — owner flush of operator-visible `vo_pickup/synthesized/` has **no** `_should_skip_stale_vo_pickup_promote`; can clobber a sha-bound dest that `promote_owner` already protected.
  - `write_staging.py:_commit_stage_writes` / `run_wrapped_stage` — orphan recovery for `vo_synthesize` auto-commits pending via the same ungated flush (exec_10066 / exec_11630 path).
  - `write_staging.py:_should_skip_stale_vo_pickup_promote` — skip exists but is wired only into `promote_staged_side_effects` / `promote_owner_vo_pickup`; skipped pending left on disk can still be flushed later.
  - `write_staging.py:promote_owner_vo_pickup` — bind-gated promote (partial product); covered by `tests/test_write_staging.py::test_promote_owner_skips_stale_pending_over_audited_wav` (not full End-B closeout).
  - `write_staging.py:promote_glue_then_discard_stale_edl` + `discard_non_owner_pending_vo_pickup` — EDL must not flush `vo_pickup` (F2 closed).
  - `vo_bind_authority.py:heal_seated_bind_mismatch` / `_try_resynth_seated_line` — resynth then omit; does not delete skipped owner pending.
  - `stages/assembly.py:resync_required_synthesize_wavs` + EDL bind-heal block (~1280–1316) + raise at `gap VO lines missing WAV` (~1462) — nested owner promote; consumer refuse, not flush cousin.
  - `stage_input_checks.py:_check_edl` — G1 missing + script/WAV mismatch blocks EDL entry.
  - `stage_completion.py` (`edl` incompleteness / `edl_heal_resume_stage`) + `recovery_controller.py:playbook_rebuild_edl` — refuse dirty EDL / no soft-recover while unsanitary (HE-2).
  - `execution_contract.py:run_edl_vo_coverage_ladder` / `_pin_unrecovered_coverage_to_vo_synthesize` — missing seated WAV pins `vo_synthesize` (HV-2).
  - `heal_routing.py:classify_heal_error` — `seated_bind_stale` / gap-missing-WAV / G1 pickup → synth family, not EDL rebuild.
  - `artifact_sanitize/vo_synthesize.py:vo_sanitary_errors` — emits `seated_bind_stale:*` (gate name, not promote authority).
- **Likely code:**
  `write_staging.py` (`flush_stage_writes`, `_should_skip_stale_vo_pickup_promote`, `promote_owner_vo_pickup`, orphan `_commit_stage_writes`), `vo_bind_authority.py`, `heal_routing.py`, `execution_contract.py`, `stages/assembly.py` (EDL resync/heal), `stage_input_checks.py`, `stage_completion.py`
- **Reuse / gap vs F*/H*:**
  - **Reuse F2** (`tests/test_f2_seated_bind.py`): EDL glue discard, write redirect, heal resynth/omit, EDL done refuse while bind stale — do not reopen.
  - **Reuse HV-2** (`tests/test_hv2_vo_coverage_pin.py`): missing seated WAV / coverage ladder pins `vo_synthesize` — do not reopen.
  - **Reuse HE-2** (`tests/test_he2_edl_heal_playbook.py`): playbook must not soft-complete EDL while VO/bind unsanitary — do not reopen.
  - **HC-3** adjacent only (pending overlay completeness for JSON); **not** WAV bind/promote authority — do not treat as End-B superseded.
  - **Gap:** owner flush/orphan promote after stale-skip; no End-B `MUX_FORENSICS=0` fixture asserting flush cannot clobber audited take; **`missing_g1_pickup` uncovered by F2/HV-2/HE-2/HC-3** (zero tests assert that error_class); bind-stale + newer pending policy unset. Soft: F2 + `test_promote_owner_skips_stale_pending_over_audited_wav` lack `MUX_FORENSICS=0` closeout pin.
- **Policy questions (1–3, unanswered):**
  1. When bind is stale but a newer pending WAV exists, prefer resynth, omit, or promote-after-audit only?
  2. When `_should_skip_stale_vo_pickup_promote` refuses a promote, must that pending be **deleted** so `flush_stage_writes` / orphan commit cannot re-promote it?
  3. Must every owner flush path (`flush_stage_writes`, orphan `_commit_stage_writes`) share the same bind skip as `promote_staged_side_effects`, or is promote-owner-only + discard-on-skip enough?
- **Fixture gap (what MUX_FORENSICS=0 test is missing):**
  1. **`end_b_flush_bypasses_stale_vo_skip`** (HEAD promote cousin) — plant sha-bound committed `vo_pickup/synthesized/{lid}.wav` + stale `.pending_writes/vo_synthesize/vo_pickup/...`; assert `promote_owner_vo_pickup` skips **and** `flush_stage_writes(ctx, "vo_synthesize")` / orphan `_commit_stage_writes` does not overwrite the audited take (preferably also clears skipped pending).
  2. **`tests/test_hv2_missing_g1_pickup.py`** (predicate cousin uncovered) — assert `missing_g1_pickup` / “g1 vo pickup missing” → playbook `ensure_g1` / resume `vo_synthesize`, not soft-recovered EDL; `MUX_FORENSICS=0`.
  Soft/optional: retrofit `MUX_FORENSICS=0` on F2 / promote-owner tests; bind-stale dest + pending matching audit (policy-dependent promote-after-audit).
- **One-line summary:**
  F2/HV-2/HE-2 seal classic bind/heal/pin; End-B stays partial until owner flush/orphan cannot promote bind-failing pending over a sha-bound take (`MUX_FORENSICS=0`).
