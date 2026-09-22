# Phase analysis — build

brain: 0.2.0 | mode: partially_accelerated | code_is_king: true  
stages (`v2/phases.py`): vo_synthesize → sound_design_vo_finalize → edl_narrative_audit → edl → assembly_preview → listen_delight_audit → music_palette_compose → sfx_prompt_craft → mmaudio_sfx → mix → junction_snip_qa  
clinic maps: HINT only — verified against HEAD 2026-09-21

## Level 1 — Stage solo

| Stage | Open routes (HEAD) | Thrash? | Notes |
|-------|--------------------|---------|-------|
| `vo_synthesize` | Chatterbox / S2S synth; G1-skip stub; `require_vo_path_ready`; nested synth skip when seated | Medium (VO ladder cousins live in fill_gaps/sound) | Build entry; hollow seats refuse mark via `_vo_seed_hollow_seats_incompleteness`. Local-ML reclaim order → DP-LOCAL-ML-RETRY. |
| `sound_design_vo_finalize` | Measure vo_pickup WAVs → rewrite SDP cue timings; opening_adjacency repairs (fail-open) | Low–med | Extra seed stage between synth and narrative. **SIMPLIFY/CUT candidate** — work could fold into synth exit or EDL prep. ESR historically waited on `fresh:vo_wavs` here (HINT i8 cousin). |
| `edl_narrative_audit` | LLM remutate loop; blocks `edl` via `narrative_audit_blocks_edl` | Medium | Must-precede for `edl`. Continuity / remutate thrash under freeze (HINT i10). Soft fail can leave audit incomplete → seed pin ping-pong with EDL. |
| `edl` | Build clips + ledger; narrative QC; order lock | Medium | Producer for preview/mix/junction. Incomplete ledger / naked seams feed junction ladder. |
| `assembly_preview` | Speech+VO concat → `assembly_preview.wav`; heard-wav refuse → pin synth | Low–med | Music epoch admits on **preview or** `assembly.wav` (`MUSIC_REQUIRES_ASSEMBLY`). Preview ≠ mix seat — freshness cousin. Dual render vs mix = **SIMPLIFY** surface. |
| `listen_delight_audit` | Pre-mix advisory (`fail_early_at_audit_stage` default false); post-mix rerun; ship authoritative | Medium | Phase-A end. Unattended writes `waived_unattended` telemetry only — does **not** clear floors (`listen_delight_cleared_for_progress` = seed_complete \| quality_waived). Partial can stall music if floors fail and no quality waiver. |
| `music_palette_compose` | LLM cue arrange; hollow when cue_count=0 + theme assets (MPC-B1) | Low–med | Gated by Phase-A seal + assembly present. Cousin **SDP_CUE_SLOTS** (policy written earlier). |
| `sfx_prompt_craft` | Prompt craft for MMAudio | Low | Spend block stage. |
| `mmaudio_sfx` | Local MMAudio generate + QA parity | Medium | Local-ML fault order (DP-LOCAL-ML-RETRY). `ensure_mmaudio_qa_before_mix`. |
| `mix` | Full stem mix → `assembly.wav` + ledger; refuse on live incomplete-cuts; remux cycles | **PRIMARY** | Seat SSOT `mix_outputs_seated` (mtime + commitment + gen). Logs “refuse mark_done” then still calls `mark_done` — ownership/`FORCE_DONE_GUARDED` must catch. Seating `except` skip → hollow risk. |
| `junction_snip_qa` | Detect → repair → `_budgeted_remaster_mix` ≤2 → feel → commitment | **PRIMARY** | MUST_PRECEDE only `edl`. Order flip via `junction_recut_precedes_mix`. Remaster uses `run_nested_staged_stage(..., "mix", ...)`. Oscillation halt + identical-failure ×3. |

## Level 2 — Group

- Internal order / done agreement:
  - Structural spine: `MUST_PRECEDE` in `delivery_guardrails.py` (junction → edl only; mix → mmaudio+edl).
  - Soft epoch: Phase A through `listen_delight_audit` must seal (`phase_a_sealed` / `seal_phase_a_if_stable`) before music consumers.
  - Ready meaning: `producer_ready` ≡ `seed_stage_complete` ≡ done ∧ outputs ∧ no incompleteness — **no** exists-only escape.
  - Mix/junction exception: `junction_recut_precedes_mix` (live cuts **or** missing/stale assembly **or** A1-1 remaster-in-flight: assembly present ∧ mix unmarked).
  - HEAD A1-1: remaster-in-flight folded into SSOT; runtime **no longer** short-circuits on assembly existence alone (`homunculus/runtime.py`). Matrix: `tests/test_junction_precedes_gate_matrix.py`.
  - A5-1: `assert_consumer` skips commitment **only** when assembly missing (not whenever SSOT True).
- Candidate SIMPLIFY / CUT:
  | Unit | Tentative | Why |
  |------|-----------|-----|
  | `sound_design_vo_finalize` as standalone seed | **CUT_CANDIDATE / SIMPLIFY** | Thin measure+SDP rewrite + opening repairs; high ESR/pin surface for low unique value vs folding into synth/EDL. |
  | Dual `assembly_preview` + full `mix` renders | **SIMPLIFY** | Preview admits music; mix reseats everything — wall-clock tax; freshness confuse. |
  | Pre-mix `listen_delight_audit` vs ship authoritative | **SIMPLIFY** | Default fail_early=false already advisory; dual audit + waiver telemetry adds Phase-A seal complexity. |
  | Junction remaster nested mix | **KEEP** (for now) | Nested staging fixed HINT i11e class; cutting remaster forces always-reseed mix externally. |

## Level 3 — Handoffs

| Edge | Ready meaning | Cousin risk |
|------|---------------|-------------|
| sound → build (`vo_line_adjudicate` → `vo_synthesize`) | adjudicate seed-complete + `vo_path_ready` | VO_LADDER_PARTIAL · J-vo-ladder-partial |
| `vo_synthesize` → `sound_design_vo_finalize` | synth outputs + seated VO WAVs | HOLLOW_DONE (hollow seats) |
| `*_finalize` → `edl_narrative_audit` → `edl` | finalize seed-complete; narrative blocks EDL | FREEZE / remutate; narrative thrash |
| `edl` → `assembly_preview` | edl seed-complete | heard-wav → synth rewind |
| `assembly_preview` → `listen_delight_audit` | preview WAV | Preview≠mix seat confuse |
| Phase A → music (`listen_delight` → palette/SFX) | `phase_a_sealed` + delight cleared **or** quality waiver; assembly **or** preview | J-phase-a-seal · delight waiver honesty |
| music → `mix` | mmaudio seed-complete + edl | Local-ML · theme bookends |
| `edl`/`mix` → `junction_snip_qa` | edl seed-complete; **mix optional** when SSOT precedes | **MIX_JUNCTION_SEAT** · J-mix-junction-precede |
| `mix` seat honesty | `mix_outputs_seated` before done | J-hollow-done · J-assembly-freshness |
| build → ship | seated mix + committed junction (or omit path) | J-post-master-wait · hollow junction End-D |

Internal handoff ids (ledger): M23 preview→delight · M32 edl→mix · M33 edl→junction · M34 edl→finalize.

## Level 4 — Junctions

| Junction id | Fact (HEAD) | Callers | Linked DP |
|-------------|-------------|---------|-----------|
| J-mix-junction-precede | `junction_recut_precedes_mix`: live cuts \| missing/stale assembly \| A1-1 (assembly ∧ ¬done(mix)). MUST_PRECEDE junction=`(edl,)`. | SSOT `junction_snip_qa.py`; runtime `_seed_prereq_block`; agenda `constrain_conductor_to_seed_front`; `llm_flow_hardening`; `_check_junction_snip_qa`; `assert_consumer` (A5-1); MUST_PRECEDE; tests gate matrix + i25 | **DP-BUILD-MIX-JUNCTION** (≡ DP-A1 remount) |
| J-assembly-freshness | Consumers need gen+mtime+commitment seat (`mix_outputs_seated` / `mix_stale_versus_live` / seating stale bump) — not preview WAV alone | `air_order.py`; thrash bump; assembly rewrite; stage_completion pin; agenda mix path; heal_routing; sound_design / junction ensure seat | **DP-BUILD-ASSEMBLY-FRESHNESS** (≡ DP-A5 cousin) |
| J-hollow-done | `.stage_done` without seated outputs refused; mix calls mark_done after “refuse” log; seating except skip | mark_done / ownership / FORCE_DONE_GUARDED; mix body; junction commitment incompleteness | **DP-BUILD-HOLLOW-MIX** (feeds DP-B4) |
| J-phase-a-seal | Seal before music; refuse without sanitary layup | delivery_guardrails; agenda; thrash; unstick | (defer to sound/plan_rank DPs; noted) |
| J-premature-pin | `mix_seat` / assembly_stale pins | premature_class_pin; heal_navigate; mix_seat_resume_stage | cousin of MIX_JUNCTION — soak under DP-BUILD-MIX-JUNCTION |
| J-vo-ladder-partial | Synth entry | gap_vo_gates; vo_synthesize | fill_gaps DP (not opened here) |

## Decision Packets drafted

- **DP-BUILD-MIX-JUNCTION** — remaining mix⇄junction / A1-1 overbreadth / pin cousins (aligns DP-A1)
- **DP-BUILD-HOLLOW-MIX** — mix “refuse then mark_done” + seating-exception hollow path (aligns DP-B4 mix surface)
- **DP-BUILD-ASSEMBLY-FRESHNESS** — preview vs assembly admit + commitment when assembly present (aligns DP-A5 / HX-2)

Also open cross-cutting: **DP-LOCAL-ML-RETRY** (mmaudio / chatterbox in this phase).

## Partial impact

Build is **critical-path thrash** for Partial zero. HEAD already landed A1-1 SSOT fold, A5-1 commitment-skip narrowing, nested remaster staging, and `mix_outputs_seated` gates — HINT i11* classes are **partially mitigated**, not closed. Remaining Partial blockers:

1. **A1-1 overbreadth:** any unmarked mix + landed assembly → junction precedes even with clean detect — traps hollow-stamp-fail remasters in junction-first forever until mix marks done.
2. **Hollow mix path honesty:** log says refuse; `mark_done` still invoked; seating helper exceptions skip the gate.
3. **Assembly freshness / music admit:** preview satisfies `MUSIC_REQUIRES_ASSEMBLY` while mix seat is gen+commitment — Partial can spend SFX on preview then thrash reseating at mix/junction.
4. **Phase-A delight floors** without quality waiver can stall music under Partial even with `waived_unattended` telemetry.
5. **CUT/SIMPLIFY:** `sound_design_vo_finalize` and dual preview/mix remain complexity tax without closing seat cousins.

**Tentative phase verdict:** **PARTIAL_BLOCKED** until DP-BUILD-MIX-JUNCTION + DP-BUILD-HOLLOW-MIX + DP-BUILD-ASSEMBLY-FRESHNESS decided (and Local-ML retry for mmaudio). Not ship-blocked solely by build if ship waits, but Partial ironclad cannot claim build clear.
