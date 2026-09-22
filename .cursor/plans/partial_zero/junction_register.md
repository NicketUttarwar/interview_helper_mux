# Junction register — Partial Zero

**SSOT:** HEAD code (grep/read). Docs/clinic/plans = hints only.  
**matrix status:** pending until operator verdict + HEAD matrix tests.  
**linked DP:** build packets 2026-09-21 (MIX-JUNCTION · ASSEMBLY-FRESHNESS · HOLLOW-MIX); sound/ship packets also assigned.

Template fields: fact · callers · family · cousin list · matrix status · linked DP.

---

## J-mix-junction-precede

- **fact:** Whether `junction_snip_qa` may run before `mix` is decided by `mix_junction_seat.junction_precedes_mix` (facade `junction_recut_precedes_mix`) — True on live incomplete-cut criticals, stale final assembly, or explicit `remaster_owner`. Missing assembly alone does not precede. MUST_PRECEDE lists only `("edl",)` for junction.
- **callers (HEAD verified):**
  - `mix_junction_seat.py` — authority SSOT (`begin_remaster` / `clear_remaster` / `may_admit_music`)
  - `junction_snip_qa.py:junction_recut_precedes_mix` — thin facade; `remaster_mix_only` stamps owner
  - `homunculus/runtime.py:_seed_prereq_block` — calls SSOT
  - `homunculus/agenda.py`, `llm_flow_hardening.py`, `stage_input_checks.py`
  - `air_order.py:assert_consumer` — `must_verify_commitment`
  - tests: `test_mix_junction_seat.py`, `test_junction_precedes_gate_matrix.py`, `test_i25_*`
- **family:** Seat / precedence (End-D · MIX_JUNCTION_SEAT)
- **cousin list:** J-assembly-freshness · J-hollow-done · J-premature-pin (mix_seat)
- **matrix status:** authority landed; hollow/resume residual
- **linked DP:** [DP-MIX-JUNCTION-SEAT-AUTHORITY](packets/DP-MIX-JUNCTION-SEAT-AUTHORITY.md)

---

## J-assembly-freshness

- **fact:** Mix/junction/finalize consumers must read assembly rendered from the current air-order generation (`live_generation_matches` / `mix_outputs_seated` / `assembly_seating_stale`), not mtime-only or preview WAV.
- **callers (HEAD verified):**
  - `air_order.py:mix_outputs_seated`, `ensure_assembly_mtime_seats_edl`, `assert_consumer`
  - `air_order.py:mix_stale_versus_live` (feeds `junction_recut_precedes_mix`)
  - `thrash_hardening.py:bump_assembly_seating_generation`
  - `air_order_integrity.py` — stamps `assembly_seating_stale` on order change
  - `stages/assembly.py` — bump on EDL rewrite
  - `stage_completion.py` — mix incompleteness → `mix_outputs_seated`; pin table `assembly_seating_stale` → `mix`
  - `homunculus/agenda.py:stage_outputs_present` (mix path)
  - `sound_design.py` / `junction_snip_qa.py` — ensure seating before consume
  - `heal_routing.py` — seating stale / mix seated checks
- **family:** Seat / commitment (End-D · HX-2)
- **cousin list:** J-mix-junction-precede · J-hollow-done · J-premature-pin
- **matrix status:** pending
- **linked DP:** [DP-BUILD-ASSEMBLY-FRESHNESS](packets/DP-BUILD-ASSEMBLY-FRESHNESS.md) (≡ DP-A5 cousin)

---

## J-hollow-done

- **fact:** `.stage_done` without outputs / with incompleteness is not seed-complete. `producer_ready` refuses exists-only escapes. Skip/mark paths must not greenwash hollow markers (`HollowSkipBlockedError`, `heal_or_refuse_mark`).
- **callers (HEAD verified):**
  - `delivery_guardrails.py:seed_stage_complete` / `producer_ready`
  - `homunculus/agenda.py:stage_outputs_present`, hollow-skip refuse (`HollowSkipBlockedError`)
  - `run_context.py:mark_done` → force routes `heal_or_refuse_mark`
  - `stage_completion.py:heal_or_refuse_mark`, `stage_artifact_incompleteness`; PRODUCER_PIN `hollow_done` → `""`
  - widespread stage bodies via `heal_or_refuse_mark` (gaps, air_script, vo_line_adjudicate, …)
  - End-D: junction commitment incompleteness blocks finalize when hollow QA
  - tests: `test_endd_commitment_seating.py`, `test_hv3_*`, `test_hg2_*`, `test_he1_*`
- **family:** Done honesty (BP-B4/B5 · End-D hollow junction · finalize/PMQ)
- **cousin list:** J-premature-pin · J-post-master-wait · J-phase-a-seal · J-vo-ladder-partial
- **matrix status:** pending
- **linked DP:** [DP-BUILD-HOLLOW-MIX](packets/DP-BUILD-HOLLOW-MIX.md) (mix surface); [DP-SHIP-HOLLOW-FINALIZE](packets/DP-SHIP-HOLLOW-FINALIZE.md) (finalize/PMQ); DP-B4/B5 (family)

---

## J-premature-pin

- **fact:** Fail tokens `premature_complete:<class>` must pin the owning producer via `premature_class_pin` / `producer_pin_for_token` — not substring-steal to `transitions` or wrong stage (`mix` inside `remix…`).
- **callers (HEAD verified):**
  - `stage_completion.py:premature_class_pin` — named classes (`mix_seat`, `music_epoch`, `vo_g1`, `phase_a_edl`, …); B3-1 unknown → transitions not fake stage
  - `stage_completion.py:producer_pin_for_token` — compounds before HEAL_TOKEN substring
  - `artifact_ownership.py` — heal token owners; premature_complete routing
  - `thrash_hardening.py:heal_navigate` — premature_class before seed-order fall-through
  - `gap_vo_gates.py` — notes premature remap hazards
  - tests: `test_r4_premature.py`, `test_r5_mix_seat.py`
- **family:** Pin / heal routing (BP-B1/B2/B3)
- **cousin list:** J-hollow-done · J-assembly-freshness · J-mix-junction-precede · J-phase-a-seal
- **matrix status:** pending
- **linked DP:** —

---

## J-freeze-constitution

- **fact:** Under hard seat freeze, legal mutations are End-A `HARD_FREEZE_ALLOWLIST_ACTIONS` only (incl. named ship-blocking omit/integrity + named CTA). Classifier `_ship_blocking_omit_ids` names deltas; `commit_selection_mutation` lands them only via `hard_freeze_action_permitted` (DP-A2=A). Packaging substring auto-allow CUT — CTA exact End-A or meta-gate. Gap/SDP/transition promotes must not silently skip freeze (BP-A3 / DP-A3).
- **callers (HEAD verified):**
  - `seat_authority.py:HARD_FREEZE_ALLOWLIST_ACTIONS`, `end_a_action_for_ship_blocking_omit`, `hard_freeze_action_permitted`, `seat_mutation_allowed`
  - `air_order_boundary.py:_ship_blocking_omit_ids` (classifier), selection commit End-A permit path
  - `air_script.py` — soft/hard freeze gates on mutation
  - `vo_bind_authority.py` / `vo_contract.py` — catastrophe / soft freeze
  - `timeline_optimizer/apply.py` — gap promote gated; transitions/SDP promote historically ungated (BP-A3 hint — verify on patch)
  - tests: `test_enda_hard_freeze_constitution.py` (ship-omit rows + packaging substring refuse), `test_i29_junction_ladder_can_land_omit.py` (i30/i37 land), `test_seat_freeze_meta_gate.py`
- **family:** Freeze (End-A · BP-A2/A3)
- **cousin list:** J-mix-junction-precede (omit under freeze) · J-phase-a-seal · J-sdp-cue-slots
- **matrix status:** A2 closed; A3 pending
- **linked DP:** [DP-A2](packets/DP-A2.md) ✅ · [DP-A3](packets/DP-A3.md)

---

## J-sdp-cue-slots

- **fact:** Soundscape `cue_slots` (theme / dens / planned beds) must survive rescoring — `refresh_cue_slots` / `score_cue_slots` must not wipe coverage-seed beds beyond dens `max_beds` (theme slot integrity).
- **callers (HEAD verified):**
  - `soundscape_policy.py:score_cue_slots`, `refresh_cue_slots` (writes policy `cue_slots`)
  - `stages/sound_design_stages.py` — refresh on SDP path
  - `artifact_repairs.py` — repair path refresh
  - consumers: `sound_design_plan` / music & SFX stages reading SDP + policy
  - tests: `test_soundscape_policy.py` (preserves planned beds), `test_theme_slot_integrity.py`
- **family:** Soundscape / dens honesty
- **cousin list:** J-freeze-constitution (SDP promote) · fill_gaps→sound handoff · J-hollow-done (thin policy)
- **matrix status:** pending
- **linked DP:** [DP-SOUND-SDP-CUE](packets/DP-SOUND-SDP-CUE.md)

---

## J-vo-ladder-partial

- **fact:** Partial + 0.2.0 VO readiness is a single ladder (`vo_path_ready`) — framing / voice-ref / G1 / synthesize-all must agree; compose skip and synth refuse share the same reason codes.
- **callers (HEAD verified):**
  - `gap_vo_gates.py:vo_path_ready`, `require_vo_path_ready`
  - `stages/vo_synthesize.py` — requires ready before synth
  - `stages/gaps.py` / compose path — `require_vo_path_ready` for framing
  - `operator_gate_view.py` — gate cards read ready
  - `chatterbox_runner.py`, `s2s_runner.py` — synth runners check ready
  - `delivery_recovery.py` — recovery path for_synthesize=True
  - `web/server.py` — synthesize-all API refuse when not ready
  - tests: `test_vo_path_ready.py`, `test_hg4_voice_ref_heal_pin.py`, `test_hv5_g1_needs_operator.py`
- **family:** Operator / VO ladder (Track B · HG-*)
- **cousin list:** J-hollow-done · J-premature-pin (`vo_g1`) · fill_gaps→plan_rank boundary
- **matrix status:** pending
- **linked DP:** —

---

## J-post-master-wait

- **fact:** After conductor, incomplete stages may `wait` vs hard-halt (`wait_vs_halt` / `should_wait_incomplete_after_conductor`). Drivers/pipeline/agenda/ESR disagree on when fresh `master.wav` / PMQ / `.stage_done` clear the wait (BP-C* five-meanings-of-done).
- **callers (HEAD verified):**
  - `execution_status.py:wait_vs_halt`, `should_wait_incomplete_after_conductor`
  - `pipeline.py` — post-conductor wait row
  - `homunculus/agenda.py` — ship PMQ / committed master checks + wait
  - `web/runner.py` — same wait helper
  - `thrash_hardening.py` / `delivery_guardrails.py` — wait_vs_halt on ship faults
  - `post_master_quality.py:run_post_master_quality`, `require_publishable`
  - `delivery_invariants.py:committed_master_wav`
  - `tools/full_auto_driver.py` (hint: keep-join / master-missing split — verify in companion)
  - tests: `test_i11_*`, `test_execution_status.py`, `test_g_listen_full_auto_clear.py`
- **family:** Ship wait / done vocabulary (BP-C1–C5 · End-F PMQ)
- **cousin list:** J-hollow-done · J-assembly-freshness · build→ship handoff
- **matrix status:** pending
- **linked DP:** DP-C1–C5 (family); hollow feed [DP-SHIP-HOLLOW-FINALIZE](packets/DP-SHIP-HOLLOW-FINALIZE.md)

---

## J-phase-a-seal

- **fact:** Phase A (through `listen_delight_audit`) must seal before music epoch consumers. `phase_a_sealed` = checkpoint **or** `delivery_epoch.phase_a_sealed_at`. `seal_phase_a_if_stable` refuses without sanitary `nugget_layup_compose` seed-complete (C-05); soft marker-lag only for allowlisted reasons.
- **callers (HEAD verified):**
  - `delivery_guardrails.py:phase_a_sealed`, `seal_phase_a_if_stable`, `delivery_stable_for_music`, filter defer of PHASE_B/C until sealed
  - `homunculus/agenda.py` — seal on reconcile
  - `thrash_hardening.py` — seal attempts, deadline (`ensure_phase_a_seal_deadline`), music gates
  - `delivery_unstick.py` — seal + report sealed
  - `chapter_close_hitch.py` — sealed ∨ assembly present shortcuts
  - tests: `test_delivery_guardrails.py` (`test_phase_a_seal_*`)
- **family:** Delivery epoch / music admit (Phase A seal)
- **cousin list:** J-hollow-done (thin layup) · J-sdp-cue-slots · J-premature-pin (`phase_a_edl`) · M24–M28 music edges
- **matrix status:** pending
- **linked DP:** —

---

## Counts

| Metric | Count |
|--------|------:|
| Seed junctions registered | **9** |
| matrix status = pending | 9 |
| linked DP assigned | **6** (build: mix-junction · assembly-freshness · hollow-mix; + sound/ship feeds) |
