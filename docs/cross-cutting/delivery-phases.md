# Delivery phases (conductor policy)

Homunculus **0.1.0** walks delivery in phases. Manifest [`DELIVERY_ORDER`](../../src/interview_mux/v2/config.py) is unchanged (69 stages). Phasing is **agenda policy** in [`delivery_guardrails.py`](../../src/interview_mux/delivery_guardrails.py).

## Phase A — air order stable (rewind-safe)

Contiguous prefix of `DELIVERY_ORDER` through `listen_delight_audit`:

`topic_coverage_audit` → `narrative_arc_plan` → `chapter_close_hitch` → `connector_fuse_pass_pre_ranking` → `full_master_ranking` → `air_script_compose` → `nugget_corpus_mine` → `information_package_plan` → `nugget_layup_compose` → `refinement_agenda` → `gap_framing_recompose` → `selection_framing_apply` → `air_script_seams` → `transitions` → **`sound_design_plan`** → **`sound_design_vo_finalize`** → `vo_line_adjudicate` → `vo_synthesize` → `edl_narrative_audit` → `edl` → `assembly_preview` → `listen_delight_audit`

`sound_design_plan` / `sound_design_vo_finalize` are **Phase A** (before `vo_synthesize`), not music planning.

**Seal:** when G5 (`delivery_stable_for_music`) passes, write `operator/delivery_checkpoint.json` (no new stage id).

## Phase B — music planning (T0)

`music_palette_compose` + `sfx_prompt_craft` only. No MusicGen.

## Phase C — MusicGen (T2)

`mmaudio_sfx` — last possible moment before mix. Requires G5 + Phase A seal + Phase B. Lazy slots: generate cue/mix-referenced theme assets only (`avoided_musicgen` in `operator/wasted_work.json`).

Internal sub-step: `sfx_prompt_refine` runs inside `mmaudio_sfx`, not as an agenda stage.

## Phase D / E

Mix → junction → master, then ship (`SHIP_AFTER_MASTER`).

**B3 mix epoch:** after Phase A is sealed, `mix` / `junction_snip_qa` / `master_finalize` wait until `run_meta.delivery_epoch.music_complete_at` (or seated `mmaudio_sfx` / `sound_design/mmaudio_qa.json`). Isolated unit dispatch without a checkpoint is not gated.

## Listen delight soft-waive (full-auto)

Full-auto may proceed to Phase B/C with `operator/escalations/listen_delight_audit.json` `status: waived_unattended` after an audit artifact exists. Production parity: see [operator-gates.md](../workflows/operator-gates.md).

## Guardrails

| ID | Rule |
|----|------|
| G1 | `seed_stage_complete` = done ∧ outputs ∧ no incompleteness |
| G2 | Music stages require assembly WAV |
| G5 | Music block waits for Phase A seal |
| G8 | `vo_synthesize` waits for layup/transitions; never job-Finished while G1 open |
