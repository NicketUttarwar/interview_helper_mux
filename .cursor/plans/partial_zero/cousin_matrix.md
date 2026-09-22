# Cousin matrix — Partial Zero

**Law:** Code is SSOT. Exec_* / intervene logs / forensics_errors are **HINT only** — verify or drop on HEAD.  
**Seed sources:** [`mechanism_honesty_breakpoints.md`](../mechanism_honesty_breakpoints.md) BP-A/B/C · HINT Mohan intervenes i1–i11h in [`full_auto_forensics_state.md`](../full_auto_forensics_state.md) · HINT histograms in [`mohan_hint_digest.md`](mohan_hint_digest.md).  
**Closure:** family `closed` only when root fixed per operator verdict **and** listed surfaces have HEAD matrix tests (`MUX_FORENSICS=0`). Surface-only `test_iNN` does not close a family.

| Family | Status | Linked DPs | Dominant HINT (exec) |
|--------|--------|------------|----------------------|
| [HOLLOW_DONE](#hollow_done) | closed (Done Authority landed) | **DP-DONE-AUTHORITY** · B4/B5/BUILD-HOLLOW-MIX/SHIP-HOLLOW-FINALIZE ✅ | HINT exec_13167 (i4, i11, i11h) |
| [MIX_JUNCTION_SEAT](#mix_junction_seat) | closed (HAU + seat authority) | **DP-MIX-JUNCTION-SEAT-AUTHORITY** · DP-A1 ✅ · DP-A5 ✅ · **DP-BUILD-ASSEMBLY-FRESHNESS HAU ✅** | HINT exec_13159 / 13167 (i11–i11g) |
| [PIN_PREMATURE](#pin_premature) | closed (B1–B3+B6 ✅) | DP-B1 ✅, DP-B2 ✅, DP-B3 ✅, DP-B6 ✅ | HINT exec_13159 / 13165 (i1, i2, i11c/g) |
| [FREEZE_CONSTITUTION](#freeze_constitution) | open (A2+A3+A4 closed) | DP-A2 ✅, DP-A3 ✅ A′′, DP-A4 ✅ | HINT exec_13161 / 13165 / 13167 (i9) |
| [SDP_CUE_SLOTS](#sdp_cue_slots) | closed (A+ SSOT landed) | **DP-SOUND-SDP-CUE** ✅ | HINT exec_13167 (i3) |
| [LOCAL_ML_RECLAIM](#local_ml_reclaim) | closed (A landed) | **DP-LOCAL-ML-RETRY** ✅ | HINT §0.3b / thrash class |
| [VO_LADDER_PARTIAL](#vo_ladder_partial) | closed (VO1 ✅ A+; NESTED ✅; LAYUP-ADJ ✅) | DP-VO1 ✅, DP-NESTED-SYNTH ✅, DP-LAYUP-ADJ ✅ | HINT exec_13163 / 13167 (i1, i4–i7) |
| [ESR_POST_MASTER](#esr_post_master) | closed (C1–C4 ✅ A batch) | DP-C1 ✅, DP-C2 ✅, DP-C3 ✅, DP-C4 ✅ | HINT code BP-C*; weak in error json |
| [SHIP_BAR_VOCAB](#ship_bar_vocab) | closed (C5 ✅ A) | DP-C5 ✅ | HINT exec_13159 (podcast_publish spam) |
| [BUDGET_THRASH](#budget_thrash) | **closed** (soak residual) | **DP-BUD1** ✅ A | live Partial exec_13168 |
| [OWNERSHIP_STAGE_KEY](#ownership_stage_key) | closed (pickup surface) | **DP-GAP-PICKUP-CONFIRM** ✅ | live Partial exec_13168 |

---

## OWNERSHIP_STAGE_KEY

- **status:** closed (2026-09-21 pickup surface — DP-GAP-PICKUP-CONFIRM A)
- **root (plain English):** Helpers persist co-owned artifacts without naming the ALLOW owner as `stage_key`, so the **active** stage is checked and denied — stage fails before real work.
- **Partial impact:** `gap_framing_compose` dies on pickup auto-confirm → no `gap_report` → delivery `phase_a_edl` premature thrash / needs_operator (budget symptom).

### Cousin surfaces
| Surface / predicate | Seen on (HINT) | Closed by |
|---------------------|----------------|-----------|
| `confirm_pickup_speaker` write under active `gap_framing_compose` | live exec_13168 gui_log traceback | **DP-GAP-PICKUP-CONFIRM A** |
| `missing_framing` owns path but StageInfo undeclared → staged drop | live exec_13168 gui_log | **DP-GAP-PICKUP-CONFIRM A** |
| Bare `flow_adaptation` writes (`refresh_conformance`, …) | HEAD census | follow-on if soak hits |

### Closed-when
- Root: pickup/adaptation writers stamp owning `stage_key`; StageInfo declares path; HEAD test under active gap compose — **landed**.
- Matrix tests (`MUX_FORENSICS=0`): `tests/test_gap_pickup_confirm_stage_key.py`.

### Linked DPs
**[DP-GAP-PICKUP-CONFIRM](packets/DP-GAP-PICKUP-CONFIRM.md)** ✅ A implemented

---

## HOLLOW_DONE

- **status:** closed (2026-09-21 Done Authority 1A+2A+3A)
- **root (plain English):** Callers treat a stage as complete after `mark_done` / `is_done` even when ownership refused the stamp or outputs are missing — hollow `.stage_done` or silent no-op.
- **Partial impact:** Partial walk advances past unfinished work; later premature_complete / ship-wait lies; forensics must re-enter mid-stage (blocks Partial zero).

### Cousin surfaces
| Surface / predicate | Seen on (HINT) | Closed by |
|---------------------|----------------|-----------|
| `mark_done` swallows `AuthorityDenied` → callers assume stamped (BP-B4) | HINT i4 adjudicate mid-batch; i11 mix; i11h finalize | DP-DONE-AUTHORITY `try_mark_done` |
| ESR clears wait on bare `is_done` / exception escape (BP-B5) | HINT code; ship-pin path | DP-DONE-AUTHORITY `may_clear_wait` |
| LLM `auto_complete=True` marks done before seal | HINT i4, i5 | `try_mark_done` in llm_simple / llm_flow_hardening |
| Finalize hollow after loudnorm with PMQ missing | HINT i11h | stamp after PMQ persist; incompleteness requires PMQ |
| Mix refuse log then still `mark_done` | HINT i11 | `require_seated_before_mix_mark` + `try_mark_done` |

### Closed-when
- Root fix landed: `done_authority.py` — seed-complete wait clear; mix seated gate; finalize = master+PMQ+integrity; LLM bool stamp API.
- Matrix tests (HEAD): `tests/test_done_authority.py` + execution_status hollow/honest wait (`MUX_FORENSICS=0`).

### Linked DPs
**[DP-DONE-AUTHORITY](packets/DP-DONE-AUTHORITY.md)** (implements B4 custom + B5 + BUILD-HOLLOW-MIX + SHIP-HOLLOW-FINALIZE)
---

## MIX_JUNCTION_SEAT

- **status:** closed (2026-09-22 HAU + seat authority; residual premix→incomplete_cut / hollow surfaces stay named elsewhere)
- **root (plain English):** Mix vs junction vs assembly freshness disagree across runtime, agenda, hardening, air_order, publishability, and resume pins — remaster can run the wrong stage or leave commitment/ledger stale. Preview WAV dual-admit burned music before a durable seat.
- **Partial impact:** Without authority, mix⇄junction thrash; with HAU, federal seated-only music admit + speech-first beds + optional remaster after music epoch.

### Cousin surfaces
| Surface / predicate | Seen on (HINT) | Closed by |
|---------------------|----------------|-----------|
| Runtime assembly short-circuit vs SSOT `junction_recut_precedes_mix` (BP-A1) | HINT code; remaster class | **DP-MIX-JUNCTION-SEAT-AUTHORITY** — `mix_junction_seat.junction_precedes_mix`; explicit `remaster_owner` |
| `assert_consumer` skips commitment whenever SSOT True (BP-A5) | HINT code | **DP-A5 ✅** `must_verify_commitment` (assembly exists) |
| Hollow mix mark_done after assembly mtime vs EDL | HINT i11 | Done Authority / seat gate |
| Stale resume pins junction instead of mix | HINT i11b, i11c | seat `resume_pin` |
| Render ledger fingerprints pending path | HINT i11d | HEAD ledger fingerprint |
| `remaster_mix_only` writes into junction pending | HINT i11e | nested staging HEAD; `begin_remaster`/`clear_remaster` |
| Premix commitment diverge classified as incomplete_cut | HINT i11f | residual (not HAU) |
| Resume stuck on seated mix (`premature_complete:mix_seat`) | HINT i11g | seat resume advance |
| Preview admits music (dual OR) | ASSEMBLY-FRESHNESS | **HAU** `heard_assembly` + federal `may_admit_music` (seated\|`preview_music`) |

### Closed-when
- Root fix: **Mix–Junction Seat Authority** + **HAU** — one heard-assembly SSOT; music after seated or operator preview_music; speech-first `optional_beds_until_remaster` all modes; A5 commitment when assembly present.
- Matrix tests (HEAD): `test_mix_junction_seat.py`, `test_hau_assembly_freshness.py`, `test_junction_precedes_gate_matrix.py` (`MUX_FORENSICS=0`).

### Linked DPs
**[DP-MIX-JUNCTION-SEAT-AUTHORITY](packets/DP-MIX-JUNCTION-SEAT-AUTHORITY.md)** · **[DP-BUILD-ASSEMBLY-FRESHNESS](packets/DP-BUILD-ASSEMBLY-FRESHNESS.md)** HAU ✅ · DP-A5 folded

---

## PIN_PREMATURE

- **status:** closed (2026-09-21 B1+B2+B3+B6 = A)
- **root (plain English):** Heal/resume pins from compound tokens, short stage-id substrings, or unknown `premature_complete` classes land on the wrong producer (often mix ahead of VO / ranking).
- **Partial impact:** Wrong pin → identical-failure thrash or leapfrog past open G1/selection work.

### Cousin surfaces
| Surface / predicate | Seen on (HINT) | Closed by |
|---------------------|----------------|-----------|
| Compound token: `mix_unseated` before `premature_complete:vo_g1` (BP-B1) | HINT exec_13165 i1 cousin | **DP-B1 ✅** |
| Substring `"mix" in prose` (BP-B2) | HINT code | **DP-B2 ✅** |
| Unknown `premature_complete:<class>` returned as fake stage (BP-B3) | HINT code | **DP-B3 ✅** |
| Premature_cap ranking↔TCA / selection-missing | HINT i2 | residual (not B1–B6) |
| `path_to_master_pin` / delivery_resume mix_seat loop | HINT i11c, i11g | residual MIX/resume |
| Dead first `incompleteness_resume_stage` def (BP-B6) | HINT code (maintenance) | **DP-B6 ✅** |

### Closed-when
- Root fix: specific structured tokens win; no bare short stage-id substring; unknown class → safe default; single resume API. **Landed.**
- Matrix tests: `tests/test_pin_premature_family.py` + `test_r4_premature.py`.

### Linked DPs
DP-B1 ✅, DP-B2 ✅, DP-B3 ✅, DP-B6 ✅

---

## FREEZE_CONSTITUTION

- **status:** open (DP-A2 surface closed 2026-09-21; A3/A4 still open)
- **root (plain English):** Under freeze, seat mutations must go through one End-A allowlist (or meta-gate / one-shot). Writers that never call End-A can still drift seats (A3); soft fingerprint sticky (A4).
- **Partial impact:** Residual A3/A4: silent seat drift or sticky soft fingerprint mid-delivery.

### Cousin surfaces
| Surface / predicate | Seen on (HINT) | Closed by |
|---------------------|----------------|-----------|
| Dual freeze lists: End-A vs ship-blocking omit (BP-A2) | HINT code; i30/i37 class | **DP-A2=A** — named End-A rows; `_ship_blocking_omit_ids` classifies only; packaging substring CUT |
| Gap/SDP/transitions writes skip seat freeze (BP-A3) | HINT code; SDP remaster | — |
| Soft fingerprint sticky on probe exception (BP-A4) | HINT code (rare) | — |
| Narrative plan align denied under hard_freeze | HINT i9; exec_13161 preds | — |
| Layup / transcript persist under freeze | HINT exec_13163 / 13165 | — |

### Closed-when
- Root fix: one freeze constitution (**DP-A2=A done**) + every seat-affecting persist End-A or skip-write (A3); sticky only on hard evidence (A4).
- Matrix tests (HEAD): `test_enda_*` ship-omit + packaging substring refuse; i30/i37 omit lands under freeze; SDP/gap write refuse-or-allowlist (A3); soft fingerprint not sticky (A4).

### Linked DPs
**[DP-A2](packets/DP-A2.md)** (implemented A), DP-A3, DP-A4

---

## SDP_CUE_SLOTS

- **status:** closed (2026-09-21 custom A+ SSOT)
- **root (plain English):** Post-commit cue_slot refresh / dens-cap scoring disagrees with planned SDP beds — heal validate passes then stage fails (or thrash rewrite).
- **Partial impact:** Sound phase identical-failure storm (HINT exec_13167 dominant) blocks Partial through `sound_design_plan`.

### Cousin surfaces
| Surface / predicate | Seen on (HINT) | Closed by |
|---------------------|----------------|-----------|
| `refresh_cue_slots` thrash theme_underscore | HINT i3; exec_13167 ~655 primary | `build_cue_slots_ssot` |
| Planned under_segment beds dropped past dens max_beds | HINT i3 | planned merge + normalize |
| Refresh failure aborts inject | HINT i3 | `admit_inject_cue_slots` isolate |
| invent unpaid gate zeroes cue_slots after planned merge | HEAD was wipe | soft-block keeps planned/inject |

### Closed-when
- Root fix landed: single cue_slot SSOT with normalize+dedupe; invent soft-block; repair inject folded into SSOT.
- Matrix tests (HEAD): `test_soundscape_policy.py` planned beds + invent soft-block + inject admit (`MUX_FORENSICS=0`).

### Linked DPs
**[DP-SOUND-SDP-CUE](packets/DP-SOUND-SDP-CUE.md)** ✅

---

## LOCAL_ML_RECLAIM

- **status:** closed (2026-09-21 A — shared reclaim helper)
- **root (plain English):** Local ML fail paths escalate (lighter model / CPU / mlx / raise) without kill → fixed 5s settle → same-class retry once.
- **Partial impact:** Metal/OOM thrash burns fidelity ladders; DeepFilter/STT fail closed with no reclaim; wall-clock lies about “tried hard.”

### Cousin surfaces
| Surface / predicate | Seen on (HINT) | Closed by |
|---------------------|----------------|-----------|
| MusicGen ladder / CPU before same-class reclaim | HINT thrash / §0.3b | `reclaim_for_same_class_retry` before ladder step |
| MMAudio next fidelity rung on hang/kill | HINT | reclaim then `next_fidelity_rung` |
| Chatterbox → mlx without settle | HINT | reclaim between attempts + pre-escalate |
| S2S transient loop no sleep | HINT | reclaim before continue |
| DeepFilter / STT single-shot raise | HINT | reclaim → one same-class retry |

### Closed-when
- Root fix landed: `heavy_task_policy.reclaim_for_same_class_retry` (fingerprint once; `reclaim_settle_sec=5`); wired in musicgen, mmaudio, chatterbox, s2s, deepfilter, stt.
- Matrix tests (HEAD): `tests/test_heavy_task_policy.py` settle default + once-per-fingerprint (`MUX_FORENSICS=0`).

### Linked DPs
**[DP-LOCAL-ML-RETRY](packets/DP-LOCAL-ML-RETRY.md)** ✅

---

## VO_LADDER_PARTIAL

- **status:** closed (2026-09-21 VO1 A+ · NESTED A+residuals · LAYUP-ADJ A)
- **root (plain English):** VO path readiness / nested mint / G1 / synthesize / spoken lint disagree on “ladder complete” — Partial sees wavs=0, hosted_vo floor, or mid-ladder premature while later stages run.
- **Partial impact:** Highest HINT volume on exec_13163; Partial fill_gaps→build cannot stay unattended without VO honesty.

### Cousin surfaces
| Surface / predicate | Seen on (HINT) | Closed by |
|---------------------|----------------|-----------|
| hosted_vo_floor_unmet + hollow scrub | HINT i1; all five execs | DP-VO1 ✅ ladder + Done Authority cousin |
| Adjudicate/intro mark_done before seal | HINT i4, i5 | Done Authority + VO1 |
| Spoken gendered pronoun / meta lint refuse synth | HINT i6 | DP-VO1 ladders / lint refuse |
| vo_g1 premature while synth incomplete | HINT i7; exec_13165 | PIN_PREMATURE + VO1 |
| Seed-order: synthesize before adjudicate complete | HINT exec_13163 identical storm | **DP-VO1 ✅** `vo_ladder_complete` · **DP-LAYUP-ADJ ✅** MUST_PRECEDE+clamp |
| Nested synth skip / vo_path_ready (code cousins) | HINT clinic / HEAD tests | **DP-NESTED-SYNTH ✅** |
| Layup/transitions leapfrog heal pins | HINT plan_rank thrash | **DP-LAYUP-ADJ ✅** `clamp_resume_through_order` |

### Closed-when
- Root fix: `vo_ladder_complete` + nested skip-not-stamp + MUST_PRECEDE VO chain + heal clamp; no advance past incomplete VO criticals.
- Matrix tests (HEAD): `test_vo_path_ready.py`, `test_nested_synth_skip.py`, `test_must_precede_order.py` LAYUP matrices (`MUX_FORENSICS=0`).

### Linked DPs
DP-VO1 ✅, DP-NESTED-SYNTH ✅, DP-LAYUP-ADJ ✅; pin cousins DP-B1 ✅; hollow cousins DP-B4 ✅

---

## ESR_POST_MASTER

- **status:** closed (2026-09-21 C1–C4 A batch — post-master never-thrash-wait SSOT)
- **root (plain English):** After master exists, ESR / driver / lease mtimes still wait on wrong pins or ghost wav freshness — or keep-join forever without honest done.
- **Partial impact:** Operator-visible stall after audible master; Partial ship walk never finishes without intervene (HINT i8 shape; BP-C1–C4).

### Cousin surfaces
| Surface / predicate | Seen on (HINT) | Closed by |
|---------------------|----------------|-----------|
| Wrong pin still waits on fresh `master.wav` (BP-C1) | HINT code; exec_13165 shape | **`post_master_never_wait`** |
| Driver keep-join requires `is_done` forever (BP-C2) | HINT code | **`stalled_expensive_can_advance`** (Done Authority) |
| Driver raw `wait_vs_halt` when master missing (BP-C3) | HINT code | **`should_wait_incomplete_after_conductor`** only |
| VO/MusicGen mtime leases after stall (BP-C4) | HINT i8 cousin (vo_wavs on done finalize) | **`skip_post_master_mtime_lease`** |
| Pin keeps: sound_design vs vo_ substring | HINT i8 | `_pin_keeps` (retain) |

### Closed-when
- Root fix: shared ESR_POST_MASTER helpers in `execution_status.py`; C4 lease gate delegates; C2 uses `may_clear_wait`.
- Matrix tests (HEAD): `tests/test_esr_post_master_family.py` + `test_execution_status.py` C1/C2/C4 (`MUX_FORENSICS=0`).

### Linked DPs
DP-C1 ✅, DP-C2 ✅, DP-C3 ✅, DP-C4 ✅ — **C5 ship-bar separate**

---

## SHIP_BAR_VOCAB

- **status:** closed (2026-09-22 C5 A — `pipeline_complete` sole Partial DONE)
- **root (plain English):** Five independent “done” meanings (ESR, runner, driver `pipeline_complete`, agenda remaining, G-Publish) disagree at the same wall-clock time.
- **Partial impact:** Local package may be ship-ready while ESR/driver still thrash (HINT exec_13159 podcast_publish volume) or S3 advisory hangs look like pipeline failure.

### Cousin surfaces
| Surface / predicate | Seen on (HINT) | Closed by |
|---------------------|----------------|-----------|
| Five-predicate table (BP-C5) | HINT code | **`SHIP_BAR_VOCABULARY` + docs** |
| Driver `pipeline_complete` vs agenda `ship_after_master_remaining` | HINT code; exec_13167 local ship vs S3 advisory | remaining = work list; DONE = `pipeline_complete` |
| Hollow `is_done` clears ESR (cousin HOLLOW_DONE / B5) | HINT code | package_ready envelope + Done Authority |
| G-Publish consent ≠ local ship bar | HINT exec_13167 ship note | **`g_publish_consent_is_not_ship_bar`** |

### Closed-when
- Root fix: `pipeline_complete` / `ship_bar_complete` require master + cover + mp3 + package_ready; hollow markers refused; driver fallback matches; ESR short-circuits.
- Matrix tests (HEAD): `tests/test_ship_bar_vocab.py` + `test_pipeline_complete_is_ship_bar` (`MUX_FORENSICS=0`).

### Linked DPs
DP-C5 ✅ (consumes B5, C1–C4)

---

## BUDGET_THRASH

- **status:** closed (resume-after-fix + hollow Finished; soak residual if thrash on same fp)
- **root (plain English):** Invoke/budget epoch, identical-failure registry, and walk-continue disagree — refuse of incomplete critical advances; orphan ESR leases; max_invokes without product fingerprint reset; door refuse then hollow Finished.
- **Partial impact:** Spin without product progress (HINT i7); identical_failures dominate early exec histograms; Partial dies on budget before root families surface; hollow “Finished: Interviewer script” after refuse.

### Cousin surfaces
| Surface / predicate | Seen on (HINT) | Closed by |
|---------------------|----------------|-----------|
| max_invokes advance past incomplete vo_line | HINT i7 | DP-BUD1 A (walk stop on SHIP_BAR_CRITICAL incomplete) |
| Orphan pending_only + ESR lease wait | HINT i7 | ESR batch (prior) |
| Budget counts ignore product-patch epoch | HINT i7 · **live exec_13168** | DP-BUD1 A (`reclaim_budget_on_product_flip`) |
| LimitExhausted on nugget_intro without reuse sealed | HINT i7 | prior intro reuse |
| identical_failure storms (cross-family symptom) | HINT exec_13159/61/63 sources | forensics sync / symptom |
| seed_order_prereq loops (often VO/mix symptom) | HINT exec_13163 | preserve-open rows |
| Door refuse then hollow “Finished: \<stage\>” (no artifact) | **live exec_13168** gap_framing_compose | DP-BUD1 A (runner `incomplete`) |

### Closed-when
- Root fix: budget_epoch on product fingerprint (Partial + memo-stale); walk break on refuse of incomplete must-land stages (SHIP_BAR + gap_framing_compose); refuse≠Finished job status.
- Matrix tests (HEAD): `tests/test_bud1_product_reclaim.py` + `tests/test_p15_budget_door.py` under `MUX_FORENSICS=0`.

### Linked DPs
**[DP-BUD1](packets/DP-BUD1.md)** ✅ A — fingerprint reclaim + refuse≠Finished

---

## Notes for analysts

- Prefer **family-root** options over another surface patch when one fix would re-open ≥2 cousins (§3.1 protocol).
- New cousins discovered on HEAD → add row here + new DP; do not silently expand implement scope.
- HINT exec refs never prove HEAD; re-verify predicates in code before STEP-OFF.
