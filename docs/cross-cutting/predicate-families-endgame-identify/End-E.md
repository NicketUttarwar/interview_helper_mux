# End-E identify (sidecar)

- **Family:** Heal / stamp pin discipline
- **Status suggestion:** open
- **Plain-language failure:** Late-delivery heals still resume sealed consumers (`edl` / `mix` / `master_finalize`) or stamp the wrong producer: generic `seed_order` / incompleteness defaults pin `edl`; driver chapter-absorb + missing-`voice_speaker_id` heals rewrite selection/gap under `full_master_ranking` / `edl` then re-enter `edl`; seed-order remutate can restamp a live `master_finalize` / mix marker and walk the consumer while loudnorm/`master.wav` may be truncated or still pending.
- **Example predicates:** `seed_order_prereq`; `seed order: complete <producer> before running <consumer>`; wrong-producer heal; `is split by unrelated` / chapter continuity absorb; `missing voice_speaker_id` / stamped `voice_speaker_id`; truncated loudnorm / pending `master.wav` thrash; `promote_refuse_pending_master`
- **Producer stage(s):** heal routing / `heal_navigate`; `stage_completion` pin table; `chapter_close_hitch` restamp; driver narrative remutate (`edl_narrative_qc` chapter/voice heal); `master_finalize` / loudnorm; seed-order playbook (`vo_synthesize` default + named prereq)
- **HEAD proof (file:function):**
  - `stage_completion.py:PRODUCER_PIN_TABLE` — `"seed_order"→"edl"`, `"hollow_done"→"edl"`, `"skip_then_consume"→"edl"`, `"pmq_structural"→"master_finalize"`
  - `stage_completion.py:producer_pin_for_token` — unmatched token `default="edl"`
  - `thrash_hardening.py:heal_navigate` — table pin then `canonical_resume_pin` / `path_to_master_pin` fall-through to `edl`/`mix`/`master_finalize`
  - `heal_routing.py:PLAYBOOK_REGISTRY` — `seed_order_prereq` no-ctx default `vo_synthesize`; several EDL narrative classes default `edl`
  - `recovery_controller.py:playbook_seed_order_prereq` → `delivery_invariants.py:apply_seed_order_heal` / `seed_order_consumer_for` / `live_producer_authority` (restamp sealed live producers → resume consumer)
  - `tools/full_auto_driver.py` (~5491–5555) — chapter absorb `write_json(..., stage_key="full_master_ranking")`; gap `voice_speaker_id` stamp via `write_committed_json(..., stage_key="edl")`; `execute(from_stage="edl")`
  - `tools/full_auto_driver.py:delivery_resume_stage` (~7468) — `remutate_consumers` allowlist vs producer honor
  - `stages/mastering.py:master_wav` — `ctx.mark_done("master_finalize")` immediately after ffmpeg loudnorm (no post-render duration/integrity vs assembly)
  - Cousin (not coverage): `chapter_close_hitch.py:hitch_restamp_lattice_sanitize` (HR-1 Phase A in-place restamp)
- **Likely code:** `heal_routing.py`, `stage_completion.py` (`PRODUCER_PIN_TABLE` / `producer_pin_for_token`), `thrash_hardening.py` (`heal_navigate` / `canonical_resume_pin`), `delivery_invariants.py` (seed-order restamp), `recovery_controller.py` (`playbook_seed_order_prereq`), `tools/full_auto_driver.py` (chapter/voice heal + remutate allowlist + pending-master promote), `stages/mastering.py` (loudnorm mark), `speaker_delivery_plan.py` / `selection_order_repair.fill_chapter_list_membership_gaps`, `chapter_close_hitch.py` (restamp cousin)
- **Reuse / gap vs F*/H*:**
  - **Reuse (cousins, not supersede):** HM-2 (mastering thin ≠ `edl`), HV-2 (missing WAV → `vo_synthesize`), HE-2 (unsanitary blocks soft EDL heal), HS-4 (`fuse_oscillation` ≠ `edl`), HC-4 (recovery runs resume `impl`) — all closed with fixtures below; they prove *named* wrong-pin cases, not End-E’s generic `seed_order`→`edl`, chapter/`voice_speaker` consumer stamps, or loudnorm/pending-master done-lie.
  - **HR-1 gap:** hitch ranking-lattice unmark/restamp after ID remap only — does **not** cover mid-delivery chapter absorb / `stage_key="edl"` voice stamp.
  - Fixtures to consult (not End-E close): `tests/test_hm2_mastering_heal_pin.py`, `tests/test_hv2_vo_coverage_pin.py`, `tests/test_he2_edl_heal_playbook.py`, `tests/test_hs4_fuse_oscillation_pin.py`, `tests/test_hc4_recovery_impl.py`; related thrash `tests/test_major_thrash_fixtures.py::test_fixture_pending_master`, `tests/test_recovery_controller.py` seed-order restamp cases.
- **Policy questions (1–3, unanswered):**
  1. Single resume map owner: extend `PRODUCER_PIN_TABLE` only, or also driver remutate allowlists (`delivery_resume_stage` / narrative chapter-voice heal)?
  2. On chapter absorb / missing `voice_speaker_id`, which producer may stamp (`full_master_ranking` / gap compose / `vo_synthesize` / sanitize) — and is resume-`edl` ever legal while seat freeze holds?
  3. When seed-order names a live expensive stage (`mix` / `master_finalize`), prefer unmark+rerun, restamp+resume consumer, or refuse until post-loudnorm / committed-master integrity passes?
- **Fixture gap (what MUX_FORENSICS=0 test is missing):** One (or small cluster) asserting (a) `seed_order` / `seed_order_prereq` via `heal_navigate` / pin table resumes the **named** incomplete producer, never sealed `edl`/`mix`/`master_finalize` by default; (b) chapter absorb + `voice_speaker` stamp does not use consumer `stage_key="edl"` / resume-`edl` as writer authority; (c) truncated or pending `master.wav` cannot restamp/promote `master_finalize` done / ship walk.
- **One-line summary:** Heal/stamp maps still default to sealed consumers; chapter/`voice_speaker` driver heals and seed-order/loudnorm restamp can leave wrong pins or hollow ship “done.”
