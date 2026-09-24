# Delivery phases (conductor policy)

Homunculus walks delivery in phases. Manifest [`DELIVERY_ORDER`](../../src/interview_mux/v2/config.py) is authoritative. Phasing is **agenda policy** in [`delivery_guardrails.py`](../../src/interview_mux/delivery_guardrails.py).

Live ask/enqueue/seal enforcement is **`MUST_PRECEDE` + `seed_stage_complete` / `producer_ready`** (not `MUX_CONTRACT_REQUIRES=1`, which stays advisory).

## Phase A — air order stable (rewind-safe)

Contiguous prefix of `DELIVERY_ORDER` through `listen_delight_audit`:

`topic_coverage_audit` → `narrative_arc_plan` → `chapter_close_hitch` → `connector_fuse_pass_pre_ranking` → `full_master_ranking` → **`selection_order_sanitize`** → `air_script_compose` → `nugget_corpus_mine` → `information_package_plan` → `nugget_layup_compose` → **`gap_report_sanitize`** → `refinement_agenda` → `gap_framing_recompose` → `selection_framing_apply` → `air_script_seams` → **`air_contract_sanitize`** → `transitions` → **`sound_design_plan`** → `vo_line_adjudicate` → `vo_synthesize` → **`sound_design_vo_finalize`** → `edl_narrative_audit` → `edl` → `assembly_preview` → `listen_delight_audit`

Order notes:

- Sanitize stages sit on the air-order spine (`selection_order_sanitize` / `gap_report_sanitize` / `air_contract_sanitize`).
- **`sound_design_vo_finalize` runs after `vo_synthesize`** (C-02: measure seated WAVs). It is Phase A, not music planning.
- Adjudicate → synthesize → finalize → narrative audit → edl.

**Seal:** when G5 (`delivery_stable_for_music`) passes, write `operator/delivery_checkpoint.json` (no new stage id). Seal and music stability require **seed-complete** layup, adjudicate, edl, and assembly (or assembly WAV + preview seed-complete) — not hollow `artifact_exists`.

## Phase B — music planning (T0)

`music_palette_compose` + `sfx_prompt_craft` only. No MusicGen.

## Phase C — MusicGen (T2)

`mmaudio_sfx` — last possible moment before mix. Requires G5 + Phase A seal + Phase B. Lazy slots: generate cue/mix-referenced theme assets only (`avoided_musicgen` in `operator/wasted_work.json`).

Internal sub-step: `sfx_prompt_refine` runs inside `mmaudio_sfx`, not as an agenda stage.

## Phase D / E

Mix → junction → master, then ship (`SHIP_AFTER_MASTER`).

**B3 mix epoch:** after Phase A is sealed, `junction_snip_qa` / `master_finalize` wait until `music_epoch_complete` (MUSIC_BEFORE_MIX seed-complete + SDP WAV parity). **Always-HAU** (`optional_beds_until_remaster`): first `mix` may seat speech-only assembly before MusicGen via `mix_junction_seat.next_delivery_seat` / `allow_speech_first_mix`; beds remaster after the music epoch. Soft theme/SFX gates use `beds_deferred_for_mix` (stamp + music incomplete), not live speech-first alone. Isolated unit dispatch without a checkpoint is not gated.

**Phase A lock:** when `delivery_epoch.phase_a_sealed_at` is set, `delivery_epoch.locked` defaults true. Structural invalidation requires **G-DeliveryUnlock** (`POST …/delivery/unlock`). See [operator-gates.md](../workflows/operator-gates.md).

## Listen delight soft-waive (full-auto)

Full-auto may write `operator/escalations/listen_delight_audit.json` `status: waived_unattended` after an audit artifact exists (telemetry). **Music/ship clearance** still requires seed-complete delight or explicit `quality_waived` / `e2e_quality_waivers` — bare `waived_unattended` / `e2e_soft` do not green progress. See [operator-gates.md](../workflows/operator-gates.md).

## Guardrails

| ID | Rule |
|----|------|
| G1 | `seed_stage_complete` = done ∧ outputs ∧ no incompleteness |
| G2 | Music stages require assembly WAV |
| G5 | Music block waits for Phase A seal + seed-complete producers |
| G8 | `vo_synthesize` waits for layup/transitions; never job-Finished while G1 open |
| MUST_PRECEDE | Consumer enqueue deferred until producers are `producer_ready` |
