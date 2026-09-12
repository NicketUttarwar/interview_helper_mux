# Predicate families (Mohan full-auto hardening ledger)

Living checklist of **failure families** seen across Mohan forensics campaigns (`d19c15b58ab4` fingerprint).  
Predicates are **names of gate failures**, not root causes. Close a row only when: producer invariant is fixed **and** a fixture pytest exists (prefer also plain full-auto without `MUX_FORENSICS`).

**Umbrella plan:** `.cursor/plans/predicate_family_hardening_a7731b18.plan.md`  
**Related:** [publishability-contract.md](./publishability-contract.md) · [air-order-boundary.md](./air-order-boundary.md) · [execution-status.md](./execution-status.md)

**Corpus (ships):** `5196`, `5399`, `5404`, `5410`, `5570`, `10066`, `11130`, `11160`  
**Corpus (killed / mid):** `11165` (stop: `seated_bind_stale`) · partials e.g. `5402`, `11136`  
**Do not** resume `11165` for discovery — use as fixture source only.

### Forensics error capture (while still using `MUX_FORENSICS=1`)

Until plain full-auto is reliable, keep running forensics. Every failure should land in:

| Artifact | Contents |
|----------|----------|
| `operator/forensics_errors.json` (+ `.md`) | **All** errors / predicates (identical_failures, driver ERROR, recovery, stalls) |
| `operator/forensics_minor_fixes.json` (+ `.md`) | Successful small heals only |
| `operator/identical_failures.json` | Signature counters / halt telemetry |
| `operator/forensics_escalation.json` | Stuck-same-predicate parent escalate |

Post-run: skim `forensics_errors.md` → add new families to this ledger if needed → fixture + patch → then plain full-auto acceptance.

---

## Agent iteration protocol (same prompt each time)

**Work queue order:** `F2` → `F3` → `F4` → `F1` → `F5` → `F6` → `F7`

On each invocation:

1. Read this file. Pick the **first** ID in the queue whose Status is `open` or `partial` (ignore `closed`).
2. Work **only that one family** this turn (no drive-by fixes on later IDs).
3. Investigate evidence runs + likely code; summarize the failure in plain language.
4. **Ask the operator** 1–3 concrete resolution questions (policy / tradeoffs) before patching. Wait for answers.
5. Patch producer invariant + add fixture pytest; run the new/related tests.
6. Update this ledger row: set Status to `closed`, fill **Fixture / test** with paths + pytest node id(s).
7. Reply with exactly: `COMPLETE: <ID> — <one-line summary>` and name the **next** queue ID still open/partial (or `QUEUE EMPTY`).

Do not start forensics, do not resume `exec_11165`, do not open a second family in the same turn.

---

## Status legend

| Status | Meaning |
|--------|---------|
| `open` | Still breaks plain or forensics runs; needs invariant + test |
| `partial` | Patches landed in-campaign (iN) but no durable fixture / still regresses |
| `closed` | Fixture pytest green + family not required forensics heal to pass |

---

## Ledger

| ID | Family | Invariant (one sentence) | Example predicates | Evidence runs | Producer stage(s) | Likely code | Fixture / test | Status |
|----|--------|--------------------------|--------------------|---------------|-------------------|-------------|----------------|--------|
| **F1** | Selection lattice | After ranking commit, every hard-keep is in order; CTA/orphan policy is sealed; specialist/invoke cache cannot sticky-halt without write-through | `hard_keep_missing_from_order`, `selection_lattice_seal_refused`, `limit_exhausted:…max_invokes`, `selection_sanitize_stamp_stale`, `packet_hash` | Ships: `10066`, `11130`, `11160`. Mid: `11165` i2/i3 | `full_master_ranking`, `selection_order_sanitize` | `selection_constraints.py` / `playability.py` (strip CTA/orphan from order), `artifact_sanitize/selection.py` (restamp stale if sanitize would pass), `llm_specialists.py` (`write_committed_json` specialist write-through) | `tests/fixtures/f1_selection_lattice/` · `tests/test_f1_selection_lattice.py` (`test_seal_drops_cta_and_orphan_without_raising`, `test_stale_stamp_restamps_when_fresh_sanitize_would_pass`, `test_specialist_write_through_survives_pending_discard`) · i2: `tests/test_run_failure_hard_fixes.py::test_hard_keep_drops_orphan_ids_absent_from_manifest`, `test_hard_keep_cta_parent_via_selection_exclude_without_cta_artifact` | `closed` |
| **F2** | Air / seat / bind / stamp | Seated synthesize lines have omit ledger + sha-bound WAV that match; any gap/EDL repair restamps; heal never pins EDL while bind unsanitary | `air_contract_unsanitary`, `stamp_gap_omit_flags`, `stamp_stale`, `seat_freeze_blocked_…`, **`seated_bind_stale`** | Ships: `5404`, `10066`, `11130`, `11160`. Kill: `11165` | `air_contract_sanitize`, `vo_synthesize`, `edl`, heal routing | `vo_bind_authority.py`, `write_staging.py` (EDL never flushes `vo_pickup/`), `stage_completion.py`, `heal_routing.py` | `tests/fixtures/f2_seated_bind/` · `tests/test_f2_seated_bind.py` (`test_edl_glue_does_not_promote_stale_vo_pickup`, `test_heal_resynth_clears_seated_bind_stale`, `test_heal_omits_when_resynth_fails`, `test_edl_stage_done_refused_while_bind_stale`) | `closed` |
| **F3** | Layup / VO contract | Locked-order scraps that cannot support excerpt are omitted; seated synth lines never carry skip/omit; contract checked before synth | `transcript_excerpt` (CTA scrap), `VO contract drift`, seated skip/omit | Nearly all ships; `11165` i5 | `nugget_layup_compose`, `vo_line_adjudicate`, `vo_synthesize` | `vo_contract.py` (omit-wins unseat before floor reseat), `media_ip_cta.py` (`omit_locked_degraded_cta_scraps` + i5 host-exec) | `tests/fixtures/f3_layup_vo_contract/` · `tests/test_f3_layup_vo_contract.py` (`test_repair_unseats_seated_skip_omit_keeps_flags`, `test_producer_omits_locked_degraded_cta_scrap_without_llm_need`, `test_sync_after_layup_proceeds_when_skip_omit_leftovers_omitted`, `test_hosted_floor_does_not_reseat_omit_wins`) · i5: `tests/test_media_ip_cta.py::test_execute_cta_omit_drops_degraded_transcript_excerpt_need` | `closed` |
| **F4** | Bridge / EDL glue | Reorder joins have pair-specific glue (typed topics); bridge heal resumes VO-first when WAV/bind incomplete — never soft-pass thrash on EDL | `Reorder seam missing…`, `bridge_completeness`, `chapter_close_hitch`, snake_case `topic_tags` | Ships: `11130`. Partials: `5402`. Mid: `11165` i6 | `edl`, reorder bridges, `topic_coverage_audit`, heal | `seam_glue.py` (fail-closed empty hinge; hitch/skip omit spoken), `heal_routing.py` / `recovery_controller.py` (WAV → `vo_synthesize`), `stages/assembly.py` (no soft-complete) | `tests/fixtures/f4_bridge_glue/` · `tests/test_f4_bridge_glue.py` (`test_empty_ungrounded_seam_fails_closed`, `test_hitch_cover_omits_spoken_transition_when_ungrounded`, `test_missing_bridge_wav_heals_to_vo_synthesize_not_edl`) · i6: `tests/test_vo_flow_and_cuts.py::test_listener_topic_rejects_snake_case_pipeline_tags` | `closed` |
| **F5** | Junction / mix QC | Critical incomplete-cut residuals cannot reach mix; resume producer (junction/snip), not blind remaster | `incomplete_cut_unresolved`, `on_a_roll`, publishability `pre_mix` | **`11160`**; junction noise also `5404`, `10066` | `junction_snip_qa`, `pre_mix` | `junction_snip_qa.py` (`refuse_mix_if_live_incomplete_cuts`; noop recut fuse-then-omit; incomplete-cut always hard-block), `publishability_boundary.py` (pre_mix still checks live hangs while junction is active), `stages/assembly.py` (mix preflight) | `tests/fixtures/f5_junction_mix_qc/` · `tests/test_f5_junction_mix_qc.py` (`test_remaster_refuses_live_incomplete_cuts_and_keeps_mix_done_marker`, `test_pre_mix_blocks_live_hang_even_when_junction_is_active`, `test_noop_thought_complete_fuses_into_neighbor`, `test_noop_thought_complete_omits_when_no_neighbor`) | `closed` |
| **F6** | Ship schema / PMQ | `quality_status` / PMQ `status` vocab is closed; allowed ships write `pass` (never `advisory_fail` on disk); finalize does not loud-fail that envelope; aspirational-off rubric misses are omitted | schema: `'advisory_fail' is not one of ['pass','fail']` while `publish_allowed: true` | **`11160` only** among recent ships (older ships `pmq=pass`) | `master_finalize`, PMQ, scorecard | `quality_status.py` (`ship_wire_status` / `coerce_ship_envelope_status`), `post_master_quality.py` (evaluate/persist/block) | `tests/fixtures/f6_pmq_ship_schema/` · `tests/test_f6_pmq_ship_schema.py` (`test_allowed_ship_writes_pass_not_advisory_fail`, `test_run_pmq_block_true_does_not_loud_fail_on_allowed_rubric`, `test_non_aspirational_omits_rubric_miss_from_pmq`) · related: `tests/test_post_master_quality.py` | `closed` |
| **F7** | Cover / listen advisories | Cover/listen misses are advisory above catastrophic floors; invalid cover prompts harvest a backup and still generate; Apple 1400px min-size still hard-stops local package | listen quirks, cover prompt craft noise | `5404`, `5570`, cover noise in several ships | `listen_delight_audit`, cover stages | `listen_delight.py` (1C ship soft-proceed), `post_master_quality.py` (aspirational listen rubric unless catastrophic), `stages/podcast_publish.py` (2B harvest then generate; 3C `require_cover_min_size`) | `tests/fixtures/f7_cover_listen_advisories/` · `tests/test_f7_cover_listen_advisories.py` (`test_invalid_llm_prompt_harvests_valid_backup`, `test_rejected_prompt_still_tries_generate`, `test_apple_min_size_still_hard_stops`) · `tests/test_listen_delight.py` (`test_authoritative_ship_soft_proceeds_when_catastrophic_ok`, `test_catastrophic_floors_still_hard_stop_at_ship`) | `closed` |

### Campaign interventions mapped (`exec_11165`)

| iN | Family | Notes |
|----|--------|-------|
| i1 | (gap schema) | Tier-D / sanitize — support F3/F4 inputs |
| i2 | F1 | hard_keep ∩ manifest, CTA−keep, specialist cache, packet_hash |
| i3/i3b | F1/F2 | seat freeze + stamp_stale preserve/restamp |
| i4 | (thrash) | true_waste sticky — ESR/forensics |
| i5 | F3 | degraded CTA scrap omit; soft rewrite cap bypass |
| i6 | F4 | topic_tags + ban_canned seam |
| i7 | F2 | restamp air omit after gap repair |
| i8 | F2 | pending-shadow bind probe — incomplete; closed via resynth→omit + EDL never flushes `vo_pickup/` |

---

## Closeout rule

Flip `Status` → `closed` only when all are true:

1. Producer-side invariant in product code (not forensics waiver).
2. Fixture pytest under `tests/` asserting predicate flip / dirty `stage_done` refused.
3. Ledger row updated with fixture path + test node id.

Acceptance of the **tape** (separate from per-family close): **2×** plain Mohan full-auto (`MUX_FORENSICS` unset) ship bar green.
