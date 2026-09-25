# High-risk stage audit — sound_design_plan

tier: T1 | seed: #53 | runs_hit: 8/9  
status: `complete`  
mode: fix  
updated: 2026-09-25T17:55:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> Write this before anything else. Also open the chat with a short spoken summary of what this stage does, its main rules, and key considerations so a human can orient cold.

### What this stage does

Happy path: after transitions + ranked selection exist, optionally fail-closed-reconcile selection↔narrative, refresh soundscape cue_slots / episode_structure compact, LLM-invent music **assets** + motif for the podcast flow → lint invent → stamp deferred placeholder cues (`palette_bed_placeholder` / open) onto selection bookends → inject a matching bed cue_slot into `soundscape_policy` → clamp durations → commit `understanding/sound_design_plan.json` with `_meta.producer_stage=sound_design_plan` → refresh invent-gate on policy. Real cue placement is deferred to `music_palette_compose`.

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `master/transitions.json` | Contract hard input |
| Reads (soft) | selection, narrative_plan, gap_report, sonic_context, soundscape_policy, episode_structure, briefs, … | Volley packet |
| Writes (SSOT body) | `understanding/sound_design_plan.json` | Shared one_writer with palettes / craft / compose / vo_finalize |
| Writes (ops) | `understanding/music_brief.json` | Operational ALLOW |
| Soft / side | `understanding/episode_structure_compact.txt` | ALLOW refresh |
| Spoofed side | `understanding/soundscape_policy.json` | Written under `stage_key=soundscape_policy_build` from SDP helpers |
| Touch via reconcile | `master/narrative_plan.json` | order_reconcile may align under ranking key; freezes → AuthorityDenied |

### Rules that govern it

- **Admit** — sound_design enabled (Full-auto/production force-on unless `operator/music_omitted.json`); transitions present
- **Refuse** — invent lint fail (empty assets / missing underscore|cold-open|accent / banned texture); empty selection order; Full-auto order_reconcile drift; mix seat + incomplete SDP
- **Incomplete** — palettes-only file without `producer_stage=sound_design_plan` (agenda `delivery_sdp_present`); invent_obligation unpaid in coherence
- **Heal** — placeholder cues + bed cue_slot inject; duration clamp; mix-seat restamp + raw `mark_done`; repair_sound_design_plan / sanitize off-air anchors (shared path)
- **Wait_for_gate** — none owned; seed-order waits on layup / air_script_seams upstream
- **Done / hollow honesty** — restamp producer_stage required; mix-seat skip uses `raw_stamp_session` to bypass incompleteness gate when delivery SDP already paid
- **Hard floors / QC bars** — invent lint min roles/kinds; post-commit `validate_post_sound_plan` cue↔cue_slots (skipped while `compose_deferred`); motif `prompt_dna`
- **Freeze / never_touch / ownership** — SDP one_writer ALLOW list; policy ALLOW is only `soundscape_policy_build` (SDP borrows that key); narrative/episode_structure freezes deny SDP-attributed writes

### Considerations & load-bearing policy

- **Publishability / Full-auto:** music invent must not be silently skipped (`enabled=false` overridden); MusicGen stub not a ship path.
- **Dual timeline:** assets invent here; placement/compose later — `compose_deferred` + invent_obligation gate exist to keep policy slots from inventing beds before SDP pays.
- **Selection membership:** bed/bookend anchors must sit on `ordered_segment_ids`; banned sonic flags (overlap/trauma) steer bed pick.
- **Mix seat:** once mix/junction seated, never re-invent; restamp/skip only.

### LLM / external calls

- Prompt: `docs/prompts/sound_design/plan-flow1.system.txt` via `run_flow_llm_stage`
- ≤2 attempts per stage invoke
- Hollow meaning: invent without assets / without producer restamp; invent under mix freeze

### What it deliberately does *not* do

- Does not mint WAVs (`mmaudio_sfx` / music gen) or craft verbal prompts (`sfx_prompt_craft`)
- Does not seat final cue arrangement (`music_palette_compose`)
- Does not own VO lines / EDL / mix
- Does not invent early palettes when `early_palettes_llm=false` (that stage defers here)

### Operator-visible effects

- Blocks VO synthesize / EDL narrative / mix via seed-order until delivery SDP stamped
- Cue/slot validation storms show as `stage_error` volume in forensics
- GUI: sound-design plan artifact under understanding/

---

## 1. Job statement

Invent the episode’s music asset roster and motif (deferred placeholder cues only), stamp delivery producer ownership on `sound_design_plan.json`, and leave real placement to `music_palette_compose`.

---

## 2. Error-hint intake

From the high-risk report + optional corpus peek (`identical_failures` / forensics across exec_13159–13198).

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `stage_error` storms (ledger volume) | `still_present_on_HEAD` / amplifies | Mostly wraps cue/slot + AuthorityDenied + seed-order; stage is a thrash amplifier |
| `palette_bed_placeholder` / `theme_underscore` not in soundscape `cue_slots` | `root_here` | Persist invents placeholder bed cue then races policy inject/refresh; `validate_post_sound_plan` strict_slots |
| AuthorityDenied `soundscape_policy.json` (pre_soft / hard freeze) | `authority_friction` → partially `healed` | HEAD spoofs `stage_key=soundscape_policy_build` on refresh/inject (exec_13167 comment) — unpaid land pattern remains |
| AuthorityDenied `narrative_plan.json` via order_reconcile | `downstream_of_X` + `authority_friction` | SDP calls reconcile; freeze vs `narrative_arc_plan` / ranking align key |
| AuthorityDenied `episode_structure.json` | `authority_friction` | Compact refresh is ALLOW; full structure write is not |
| Seed-order: complete layup / air_script_seams first | `seed_order_noise` / `downstream_of_X` | Upstream unpaid; SDP looks hot in ledgers |
| Seed-order: complete SDP before VO/mix/ENA | `downstream_of_X` | Victims waiting on this stage’s done stamp |
| Mix-seat invent / order_reconcile deny | `healed` (skip path) | `_mix_seat_active` + `_SdpMixSeatSkip` on HEAD |

Report why-high-risk: Cue/slot validation storms; freeze vs soundscape/narrative

Classification values: `root_here` | `downstream_of_X` | `seed_order_noise` | `authority_friction` | `still_present_on_HEAD` | `healed`

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_sound_design_plan` | `src/interview_mux/stages/sound_design_stages.py` (~L218) |
| Mix-seat skip / delivery ready | same file `_mix_seat_active`, `_sdp_delivery_ready_for_mix_skip`, `_finalize_existing_sdp_under_mix_seat` |
| Invent lint / placeholder bed | `_lint_sdp_invent`, `_safe_placeholder_bed_segment`, `_ensure_placeholder_palette` (inject peeled) |
| Cue_slots SSOT (compose-owned inject) | `soundscape_policy.py` + `music_palette_compose._inject_bed_cue_slots_for_composed_cues` |
| Post-commit cue↔slot validate | `sdp_cross_validate.py` `validate_post_sound_plan` (skips strict_slots while deferred) |
| Shared sanitize / one_writer commit | `artifact_sanitize/sound_design_plan.py`, `one_writer.py` |
| Repair kitchen | `artifact_repairs.repair_sound_design_plan` (skips slot align when `compose_deferred`) |
| Drift check (read-only) | `_selection_narrative_drift` → `material_order_conflicts` |
| Ownership | SDP one_writer; policy ALLOW `soundscape_policy_build` + `music_palette_compose` |
| Contract | `docs/cross-cutting/stage-contracts/sound_design_plan.yaml` |
| Tests (non local-ML) | `test_sdp_s1_s5_simplify.py`, `test_sound_design_stages.py`, `test_i15_mix_seat_sdp_reconcile.py`, … |

---

## 4. Business-logic walk

1. **Gate enabled** — `_sound_design_enabled`; Full-auto forces on unless explicit music omit.
2. **Mix seat short-circuit** — if mix/junction seated and delivery SDP already paid → restamp producer + seed sonic_identity if missing + `heal_or_refuse_mark` (no raw stamp); incompleteness skips selection/sdp sanitize thrash when mix-seat paid.
3. **`build_input`** — read-only selection↔narrative drift check (Full-auto refuse invent; no narrative mutate); episode_structure compact refresh; volley + music_brief write; **no** cue_slot refresh.
4. **LLM** — `run_flow_llm_stage` plan-flow1 → assets / flow_plans / motif.
5. **`persist`** — invent lint; deferred placeholder cues (`compose_deferred=True`); hydrate/bind bookends; palette seed; clear invent_obligation; clamp durations; validate; write SDP; restamp producer. **No** policy inject/refresh.
6. **Compose later** — `music_palette_compose` injects bed cue_slots under honest `writer_stage=music_palette_compose`.
7. **Downstream** — craft/MMAudio consume assets; strict cue↔slot only after deferred clears.

---

## 5. Over-engineering scorecard

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **5** | (baseline pre-fix) invent + reconcile + cue_slot inject + placeholder kitchen + mix-seat raw done |
| Dual / competing SSOTs | **yes** | (baseline) SDP cues vs policy cue_slots; spoofed policy land |
| Soft-heal / thrash re-admit loops | **yes** | (baseline) inject→refresh→validate storms |
| Co-producer / unpaid land | **yes** | (baseline) borrowed `soundscape_policy_build` stage_key |
| Brittle predicates vs simple rules | **yes** | (baseline) cue not in cue_slots |
| Disproportionate shard/memo/resume | **partial** | (baseline) satellite surface |
| “Fix everything downstream” behavior | **yes** | (baseline) inject+reconcile kitchen |

**Over-engineered?** `yes` — baseline FAIL.

**Scorecard verdict:** `FAIL`

- What would flip FAIL → PASS: responsibilities ≤2 (invent + commit SDP only); no policy/narrative side writes from this stage; strict cue↔slot validation only after compose owns cues (or single SSOT for beds).

### 5b — Re-score after changes (MODE=fix / MODE=rescore only)

| Check | Answer | Delta | Evidence now |
|-------|--------|-------|--------------|
| Responsibilities count | **2** | 3→2 (S6) | (1) invent assets/motif + restamp, (2) mix-seat skip/heal when already paid |
| Dual / competing SSOTs | **no** | partial→no | Empty deferred cues; compose owns first placement + slot inject |
| Soft-heal / thrash re-admit loops | **no** | — | Repair skips density/hinge/slot seed while `compose_deferred` |
| Co-producer / unpaid land | **no** | — | SDP does not write policy |
| Brittle predicates vs simple rules | **no** | partial→no | No invent-time cue↔slot predicates |
| Disproportionate shard/memo/resume | **no** | — | heal_or_refuse mix-seat only |
| “Fix everything downstream” behavior | **no** | — | Invent does not mint cues/slots |

**Over-engineered?** `no` — responsibilities ≤2; no hard fail-if rows.

**Scorecard verdict:** `PASS`

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P0 | needs_you | done | decided **(C)**: inject moved to `music_palette_compose`; ownership ALLOW compose on `soundscape_policy.json`; `writer_stage` param | Co-producer unpaid land; thrash | SDP call stack has no policy write |
| S2 | P0 | unambiguous | done | peeled inject + post-invent refresh from SDP persist/build_input | Dual SSOT; thrash; fix-downstream | `test_sdp_s1_s5_simplify` S2 |
| S3 | P0 | unambiguous | done | read-only drift refuse; no narrative mutate | Responsibilities; unpaid land | `test_sdp_s1_s5_simplify` S3 |
| S4 | P1 | needs_you | superseded | keep-deferred placeholders in invent → **S6** empties cues instead (still `compose_deferred=True`) | Brittle predicates | see S6 |
| S5 | P1 | unambiguous | done | mix-seat → `heal_or_refuse_mark` only; skip sanitize thrash when mix-seat paid | Hollow honesty; raw stamp | `test_i15` + S5 unit |
| S6 | P1 | needs_you | done | decided peel: invent commits empty `cues` + `compose_deferred`; repair skips density/hinge seed while deferred; compose mints first cues | Responsibilities ≥3 | `test_s6_invent_defers_cues_to_compose`; scorecard PASS |

Operator decisions: S1=(C), S4→superseded by S6 empty deferred cues (2026-09-25).

---

## 7. Root-cause verdict

Pre-fix: invent buried under cue/slot + narrative reconcile kitchen with spoofed policy land.  
Post S1–S6: invent is assets/motif only (empty deferred cues); compose owns placement + bed slots; no policy/narrative side writes from SDP. Scorecard **PASS**.

---

## 8. Recommended next action

`leave`

---

## 9. Scope fence

Upstream poison owner (if any): `nugget_layup_compose` / air_script_seams (seed-order); ranking/selection drift.  
Downstream victims (names only): `sfx_prompt_craft`, `mmaudio_sfx`, `music_palette_compose`, `vo_synthesize`, `edl_narrative_audit`, `mix`.  
Did **not** redesign other stages beyond compose inject + ownership ALLOW + repair deferred skip + stage_completion mix-seat paid honesty.
