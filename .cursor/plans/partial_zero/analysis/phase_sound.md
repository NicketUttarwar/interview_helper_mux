# Phase analysis — sound

brain: 0.2.0 | mode: partially_accelerated | code_is_king: true  
phases.py: `sound` → `["sound_design_plan", "vo_line_adjudicate"]`  
hints only: clinic maps `sound_design_plan.possibility.md`; Mohan HINT i3 / i4 (exec_13167)

## Level 1 — Stage solo

| Stage | Open routes (HEAD) | Thrash? | Notes |
|-------|--------------------|---------|-------|
| `sound_design_plan` | enabled=false → force-heal skip; clean LLM + motif + music_brief; order_reconcile fail-open; `refresh_cue_slots` fail-open log; invent unpaid / empty assets → incompleteness / `sdp_unsanitary` | **Yes — SDP_CUE_SLOTS** | Writes `understanding/sound_design_plan.json` + `music_brief`. Cue placement deferred to `music_palette_compose`; SDP keeps placeholder cues. Pre-LLM `refresh_cue_slots` commits policy under `stage_key=soundscape_policy_build`. |
| `vo_line_adjudicate` | no gap_report → skip; G1 optional skip stub; batch LLM with `auto_complete=False` then seal + `heal_or_refuse_mark`; spoken lint / allocation refuse | Residual (i4 surface patched) | Primary `understanding/vo_line_adjudication.json`. Mid-batch hollow mark_done fixed on HEAD (`auto_complete=False`). Cousin **VO_LADDER_PARTIAL** still owns Partial fill_gaps→build, not this phase alone. |

### HEAD routes worth keeping visible

- **SDP invent gate:** `_apply_invent_obligation_gate` sets `cue_slots=[]` while invent unpaid (`soundscape_policy.py`) — intentional strip, but couples refresh thrash to unpaid invent.
- **Dens + planned beds:** `score_cue_slots` dens-caps then `_merge_planned_bed_slots` (i3 surface). Tests: `test_score_cue_slots_preserves_planned_sdp_beds_beyond_dens_cap`, `test_sdp_bed_cue_slot_injections_survive_sound_design_plan_flush`.
- **Repair inject:** `artifact_repairs` isolates refresh failure so theme_underscore inject still runs; still dual-writes policy slots vs SDP beds.
- **Adjudicate:** seal-then-mark only; FORCE_DONE_GUARDED + hollow refuse remain.

## Level 2 — Group

- **Internal order / done agreement:** MUST_PRECEDE `transitions` → `sound_design_plan` → `vo_line_adjudicate` → (`vo_synthesize` / music consumers). Agenda `stage_outputs_present`: SDP requires delivery producer fingerprint (`_sdp_producer_stage == sound_design_plan`); adjudicate requires adjudication.json (not mid-batch).
- **Candidate SIMPLIFY / CUT:**
  - SIMPLIFY: one cue_slot writer (score ∪ planned ∪ inject) — see DP-SOUND-SDP-CUE.
  - CUT candidate: early `sound_design_palettes` LLM already deferred (`early_palettes_llm=false`) — keep; do not re-add dual invent sites.
  - Do **not** CUT soundscape refresh entirely — music/SFX consumers need slots; fix honesty instead.

## Level 3 — Handoffs

| Edge | Ready meaning | Cousin risk |
|------|---------------|-------------|
| P9 `edit`/`plan_rank` → `sound` (`transitions`) | `producer_ready(transitions)` | freeze promote of SDP (FREEZE_CONSTITUTION) |
| M14 SDP → adjudicate | SDP seed-complete | dens wipe / invent wipe → hollow SDP consume |
| P10 `sound` → `build` (adjudicate → `vo_synthesize`) | adjudication seed-complete | VO_LADDER_PARTIAL; hollow adjudicate (HOLLOW_DONE) |
| M29 SDP → `sfx_prompt_craft` | SDP seed-complete | cue_slots / cross-band thrash |
| fill_gaps `soundscape_policy_build` → SDP refresh | policy exists | refresh ownership / invent gate |

## Level 4 — Junctions

| Junction id | Fact | Callers | Linked DP |
|-------------|------|---------|-----------|
| J-sdp-cue-slots | Planned theme beds must survive dens rescoring + refresh write | `score_cue_slots`, `refresh_cue_slots`, SDP build_input, `artifact_repairs` inject, music/SFX consumers | **DP-SOUND-SDP-CUE** |
| J-hollow-done | No mid-batch / outputs-missing mark_done | adjudicate batches, `heal_or_refuse_mark`, `assert_may_mark_done` | (VO/ship DPs; sound residual i4) |
| J-freeze-constitution | SDP / policy writes under hard freeze | `persist_frozen_seat_doc`, refresh `stage_key` | DP-A3 family (not opened here) |
| J-vo-ladder-partial | Adjudicate is plan step of VO ladder | `vo_path_ready` consumers in build | DP-VO1 (draft elsewhere) |

## Decision Packets drafted

- **DP-SOUND-SDP-CUE** — cue_slots thrash / dens vs planned beds / invent wipe / dual writers — `awaiting_operator`
- (Noted, not opened): adjudicate mid-batch hollow — HEAD patched; reopen only if Partial soak regresses.

## Partial impact

Without SDP cue_slot root honesty, Partial stalls in **sound** on identical-failure / heal-validate↔stage-fail (HINT exec_13167 dominant family). Adjudicate alone is not the Partial blocker once seal-after-batch holds; **build** still needs VO ladder closure separately.

## Verdict (phase)

**PARTIAL_BLOCKED** on **SDP_CUE_SLOTS** until DP-SOUND-SDP-CUE verdict + matrix close. Adjudicate: **PARTIAL_SURFACE_OK** on HEAD for mid-batch mark_done; residual risk is cousin VO ladder.
