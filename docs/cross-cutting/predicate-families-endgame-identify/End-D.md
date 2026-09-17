# End-D identify (sidecar)

- **Family:** Mix / junction commitment seating
- **Status suggestion:** partial
- **Plain-language failure:** After junction (or mix-adjacent writers) persist a newer live EDL via `write_live_edl`, `assembly.wav` can lag that EDL (mtime and/or `render_ledger` generation). Mix is then **unseated** (`mix_outputs_seated` false → `mix_unseated` / `mix_seat` / `premature_complete:mix_seat`). Junction must run a **commitment** remaster to reseat assembly; that remaster must **not** be refused as timeline-reopen `low_gain`. If remaster still cannot run, junction must **loud-fail** (`junction_commitment_remaster_refused`) — never stamp hollow `.stage_done/junction_snip_qa` so `master_finalize` can seed-skip and thrash (`seed order: complete junction_snip_qa before master_finalize`). **HEAD seal is incomplete:** producer loud-fail + `ship_path_ready` / `assert_consumer` often catch finalize, but `seed_stage_complete(junction)` has **no** `stage_artifact_incompleteness` commitment branch — autopsy/QA files alone can look seed-complete while commitment mismatches.
- **Example predicates:**
  - `commitment_remaster_refused` / `junction_commitment_remaster_refused` / `junction_commitment_remaster_failed`
  - `low_gain` / remaster refused low_gain (non-critical paths; must not gate `path=commitment`)
  - `mix_unseated` / `mix_outputs_seated` / `assembly_seating_stale`
  - `mix_seat` / `delivery:premature_complete:mix_seat` (≠ HX-4 `premature_complete:music_epoch`)
  - `seed order: complete junction_snip_qa before running master_finalize`
  - hollow / force-done junction; `junction_commitment_mismatch` / `junction_incomplete` (ship-path); `junction_commitment_diverged`
  - Hint surface (exec_11630 #9): junction hollow-done / commitment remaster `low_gain` → mix unseated; also `mix_seat`, incomplete `assembly.wav`, finalize↔junction seed thrash
- **Producer stage(s):** `junction_snip_qa`, `mix`, `master_finalize` (consumer / seed gate)
- **HEAD proof (file:function):**
  - `junction_snip_qa.py:_budgeted_remaster_mix` — `path` containing `commitment` is `critical` → skips `decide_timeline_reopen` / low_gain; feel/repair still gated; shared budget/osc after gate; bare `except` → `(False, 0)` even for commitment
  - `junction_snip_qa.py:run_junction_snip_qa` (write_live_edl then asm mtime < edl → `_budgeted_remaster_mix(..., path="commitment")`; refuse → `commitment_remaster_refused` + loud `junction_commitment_remaster_refused` / “refuse hollow junction_done”)
  - `junction_snip_qa.py:remaster_mix_only` → `write_render_ledger` + promote + `ensure_assembly_mtime_seats_edl`
  - `air_order.py:mix_outputs_seated` / `live_render_generation_matches` / `ensure_assembly_mtime_seats_edl` / `mix_wav_fresh_versus_edl`; junction/finalize also `mix_committed_for_live_gen` / `assert_consumer`
  - `stage_completion.py:_mix_unseated_incompleteness` (HX-2 for **mix only**); **no** junction commitment incompleteness branch in `stage_artifact_incompleteness`
  - `homunculus/agenda.py:_junction_commitment_matches_assembly` / `stage_outputs_present` (junction: committed fast-path, else files-only if not `mix_stale_versus_live`)
  - `delivery_guardrails.py:seed_stage_complete` / `ship_path_ready` (`junction_incomplete`, `junction_commitment_mismatch`)
  - `thrash_hardening.py:FAIL_CLASS_MIX_SEAT` / `premature_fail_key` / `safe_mix_resume_stage`; driver `premature_complete:mix_seat`
  - Seed promote cousin: `llm_flow_hardening.py:_earliest_incomplete_seed_stage` (junction→finalize promote via `stage_outputs_present`, not commitment incompleteness)
- **Likely code:** `junction_snip_qa.py`, `air_order.py`, `stage_completion.py`, `homunculus/agenda.py`, `delivery_guardrails.py`, `thrash_hardening.py`, `llm_flow_hardening.py`, `seam_autopsy.py` (`verify_commitment` / `write_render_ledger`), `timeline_reopen_meta_gate.py` (cosmetic/feel only)
- **Reuse / gap vs F*/H*:**
  - **HX-2 (closed):** core mix seating — reuse; End-D is the **junction commitment remaster → reseat** cousin after live-EDL rewrite (junction/finalize seating ≠ identical to `mix_outputs_seated`)
  - **HX-1 / HX-4 (closed):** music-epoch / premature mix lease while music incomplete — reuse for pre-mix epoch; **gap:** after music complete, mix-family leases still win while assembly unseated; `premature_complete:mix_seat` is a different class than `music_epoch`
  - **HX-3 (closed):** pre_mix autopsy path — adjacent; does not refuse hollow junction done or force commitment remaster
  - **HX-5 (closed):** G-Listen re-arm / `refused_low_gain` no re-arm — adjacent; not seating
  - **i24 partial:** unit low_gain bypass + seating helpers only — not E2E / hollow seed chain
  - Remaining cousins beyond i24: (1) gen cap / oscillation still refuse commitment remaster; (2) gate `except` refuse without low_gain label; (3) files-only `stage_outputs_present(junction)` / missing incompleteness token; (4) post-music `mix_seat` thrash vs commitment ownership; (5) End-E overlap: `seed_order_prereq` when `.stage_done` true but `seed_stage_complete` false
- **Policy questions (1–3, unanswered):**
  1. Confirm: commitment remaster always bypasses low_gain; cosmetic / feel remaster still subject to timeline-reopen gates?
  2. Should mandatory commitment (assembly-seat) remaster also bypass remaster **budget / oscillation**, or remain hard-pin → `junction_commitment_remaster_refused`?
  3. Must `stage_artifact_incompleteness("junction_snip_qa")` require `_junction_commitment_matches_assembly` (not only QA JSON + autopsy files) so hollow `.stage_done` cannot seed-complete finalize?
- **Fixture gap (what MUX_FORENSICS=0 test is missing):**
  - E2E: `write_live_edl` leaves asm older than EDL → `path=commitment` remasters → `mix_outputs_seated` true / junction may complete
  - Refuse path: commitment remaster fails → no hollow `.stage_done/junction_snip_qa`; `_seed_prereq_block(..., "master_finalize")` pins junction (**without mocking** `seed_stage_complete`)
  - Cousin: gen-cap / oscillation blocks commitment seating (policy-dependent assert)
  - Cousin: post-music `mix_seat` / `premature_complete:mix_seat` while unseated pins mix/junction (not music)
  - Existing partial / related: `tests/test_i24_commitment_remaster.py`; `tests/test_hx2_mix_unseated.py`; `tests/test_delivery_thrash_hardening.py::test_force_done_refuses_hollow_music_and_junction` (empty-ctx force only); ship-path tests often **mock** `seed_stage_complete` (`test_major_thrash_*`, `test_ship_path_ready_requires_*`) — do not close End-D
- **One-line summary:** Commitment remaster must reseat assembly after live-EDL rewrite without low_gain refuse; hollow junction seed-complete still possible without a commitment incompleteness token — keep `partial`.
