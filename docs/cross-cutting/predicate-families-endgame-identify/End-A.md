# End-A identify (sidecar)

- **Family:** Seat / omit / freeze constitution
- **Status suggestion:** open
- **Plain-language failure:**
  Under hard seat freeze, HEAD has no single allowlist of legal mutations. Some paths refuse via `gate_seat_mutation` / meta-gate; `sanitize_air_contract` and `sanitize_transitions` stay freeze-blind and can reseat, drop seats, protect/revive orientation, stamp pair-freeze, or auto-commit those deltas—while EDL/heal still thrash on `opening_orientation_audible_count=0`, blank interloper vs order restore, and air-contract ↔ `vo_synthesize` loops. Paperwork that *is* intentionally allowed (omit order-lock rebuild, blank drop under freeze) lives only as comments/tests, not a shared constitution.
- **Example predicates:**
  - `HARD: opening orientation contract still failing after one EDL resume` (hint exec_11630 volume leader)
  - `opening_orientation_audible_count=0` / `opening_orientation_inaudible`
  - `air_contract_needs_sanitize:drop_seated_missing_from_gap` (+ `protect_orientation_from_omit`, clamp cousins)
  - `air_contract_unsanitary` / soft-freeze while unsanitary (HF-4 cousin surface)
  - `transitions_needs_sanitize:stamp_pair_freeze` / redundant-transition strip thrash
  - blank interloper vs freeze undo (EDL narrative / chapter continuity; exec_11630 `seg_041`)
  - `seat_freeze_blocked_*` / `omit_ledger_order_lock_stale` (order-lock rebuild path)
- **Producer stage(s):**
  `air_contract_sanitize`, `omit_ledger` (heal / revive / order-lock rebuild), `transitions`, `edl`, `opening_orientation`, selection commit under freeze (`air_order_boundary`), seat meta-gate (`seat_authority` / `run_meta`)
- **HEAD proof (file:function):**
  - `seat_authority.py:seat_mutation_allowed` / `gate_seat_mutation` — refuse-by-default + opt-in reasons; **not** an End-A enumerated allowlist; many writers never call.
  - `artifact_sanitize/air_script.py:sanitize_air_contract` — mutates seats/omit/gap (`drop_seated_missing_from_gap`, `protect_orientation_from_omit`, floor reseat, clamp) with **no** freeze gate.
  - `artifact_sanitize/air_script.py:air_contract_sanitary_errors` — `_AUTO_COMMIT_ACTIONS` auto-commits those deltas under freeze (exec_11630 thrash comment).
  - `artifact_sanitize/air_script.py:run_air_contract_sanitize` — HF-4 marks/soft-freeze after sanitize; does **not** assert mutation legality.
  - `artifact_sanitize/transitions.py:sanitize_transitions` / `transitions_sanitary_errors` — `stamp_pair_freeze` / `trim_pair_freeze` / dedupe ungated; consumers emit `transitions_needs_sanitize:stamp_pair_freeze`.
  - `omit_ledger.py:heal_omit_ledger_air_contract` + `rebuild_and_write_omit_ledger` — order-lock rebuild **before** gate (comment: “not a seat mutation”); remainder of heal meta-gated.
  - `omit_ledger.py:revive_required_opening_orientation` — revive/clear under freeze blocked unless meta-gate (splits from ungated air-contract protect).
  - `opening_orientation.py:validate_opening_orientation` / `ensure_episode_orientation` — `audible_count=0` when EDL lacks exactly one orientation `vo_pickup`; ensure/bind desync noted (exec_11630).
  - `air_script.py:_orientation_line_waived` — stale omit sync does not waive when `opening_orientation.required` (omit ↔ seat fight).
  - `air_order_boundary.py:commit_selection_mutation` + `_drop_blank_segments_under_freeze` — freeze restores order then blank-drops + `bump_order_lock`; comments document interloper ↔ undo loop (exec_11630 `seg_041`).
- **Likely code:**
  `seat_authority.py`, `artifact_sanitize/air_script.py`, `artifact_sanitize/transitions.py`, `omit_ledger.py`, `opening_orientation.py`, `air_script.py`, `air_order_boundary.py`, `air_order.py` / seat-freeze meta in `run_meta`, heal consumers that re-enter EDL on orientation inaudible
- **Reuse / gap vs F*/H*:**
  - **F2 (closed):** bind/stamp/heal-never-pins-EDL while unsanitary — cousin of thrash *symptoms*; **does not** define which sanitize writes are legal under hard freeze. Fixture: `tests/test_f2_seated_bind.py`.
  - **F3 (closed):** layup omit-wins / seated skip-omit — pre-synth contract, not freeze-era air-contract/transitions allowlist. Fixture: `tests/test_f3_layup_vo_contract.py`.
  - **HF-4 (closed):** air-contract dirty-done / soft-freeze stamp honesty — **not** mutation allowlist. `tests/test_hf4_air_contract_dirty_done.py`.
  - **HF-3 / HF-1:** freeze+EDL seals Pass-2 for seams seed — seed-order, not sanitize constitution.
  - **HR-2:** selection commit no-op under freeze; omit ledger may still write — partial cousin only.
  - **HE-2:** `opening_orientation_inaudible` must not soft-complete EDL (pins synth/EDL heal) — **downstream pin**, fights End-A when root is omit/seat thrash under freeze.
  - **HG-5:** compose no-op under layup/freeze — wrong-producer, not W3 sanitize allowlist.
  - **HC-\*:** hollow/pending/driver — no seat-freeze mutation constitution.
  - **End-F / i25 partial:** `test_i25_omit_order_lock_rebuild_under_freeze` is the closest allowlist pin for paperwork rebuild; does **not** close End-A.
  - **Do not mark superseded** — End-A remains the missing constitution layer above closed F2/F3/HF-4.
- **Policy questions (1–3, unanswered):**
  1. Under hard seat freeze, which stay legal: omit order-lock rebuild; `drop_seated_missing_from_gap`; orientation omit sync (`protect_orientation_from_omit` / revive / stamp_gap skips); blank exclude via `_drop_blank_segments_under_freeze` (vs freeze undo of blank exclude)?
  2. When `opening_orientation.required=true`, may omit ledger keep `gap_line_skip` on the orientation id, or must revive be allowlisted without meta-gate (HEAD splits meta-gated revive vs ungated air-contract protect)?
  3. Do `stamp_pair_freeze` / `trim_pair_freeze` / framing dedupe count as allowed “redundant transition strip,” or must `sanitize_transitions` refuse all writes once `vo_seats_freeze.hard` is set?
- **Fixture gap (what MUX_FORENSICS=0 test is missing):**
  No integrated hard-freeze constitution fixture. Need `MUX_FORENSICS=0` coverage that (a) allows only the operator-chosen allowlist under `hard_freeze_active`, and (b) refuses illegal reseat / EDL thrash / blank-interloper undo loops. Existing partials: `tests/test_i25_pmq_omit_clarity.py::test_i25_omit_order_lock_rebuild_under_freeze`; `tests/test_artifact_sanitize_air_contract.py` (drop_seated / orientation protect **without** hard freeze); `tests/test_artifact_sanitize_transitions.py` (pair-freeze file, not seat freeze); `tests/test_seat_freeze_meta_gate.py` / `tests/test_hr2_off_bus_selection.py` (meta-gate / selection no-op); `tests/test_opening_orientation.py` / `tests/test_he2_edl_heal_playbook.py` (audible_count / heal pin). **Zero** tests for blank interloper vs freeze undo.
- **One-line summary:** Hard seat freeze lacks a shared mutation allowlist—air-contract and transitions sanitize stay freeze-blind while orientation/omit/blank paths thrash EDL.
