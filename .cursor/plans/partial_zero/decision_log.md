# Decision log — Partial Zero

Append-only.

## 2026-09-21T17:26:00Z — DP-A2
- verdict: A
- notes: named End-A allowlist for ship-blocking omit/integrity; CUT packaging substring auto-allow; CTA named or meta-gate; keep i30/i37 as named rows (not second constitution)
- unlocks: implement DP-A2 (IMPLEMENT_NEXT)
- family: FREEZE_CONSTITUTION

## 2026-09-21T17:31:45Z — DP-A2 implement complete
- verdict: A (landed)
- notes: HARD_FREEZE_ALLOWLIST + end_a_action_for_ship_blocking_omit; commit routes via hard_freeze_action_permitted; packaging substring CUT; enda/i30/i37/i38 + seat_freeze_meta_gate green under MUX_FORENSICS=0
- unlocks: present DP-A1
- family: FREEZE_CONSTITUTION (A2 surface closed; A3/A4 open)

## 2026-09-21T17:42:41Z — DP-A1 + MIX-JUNCTION-SEAT-AUTHORITY
- verdict: custom (1A foundation + 2A remaster_owner + 3A Partial seated music)
- notes: adopt Mix–Junction Seat Authority; fold A1/BUILD-MIX/A5/ASSEMBLY music-admit under one lifecycle SSOT; speech-first mix under Partial when music deferred
- unlocks: implement DP-MIX-JUNCTION-SEAT-AUTHORITY
- family: MIX_JUNCTION_SEAT

## 2026-09-21T18:05:00Z — Seat authority / End-A footguns 1–9
- verdict: harden (no new DP)
- notes: remaster_session+abandon; speech_first→music_epoch remaster; music_admit_block_reason; packaging soft-only; near-miss refuse; unmapped omit no default; hollow mix demote; hitch uses mix_outputs_seated
- unlocks: present DP-B4
- family: MIX_JUNCTION_SEAT + FREEZE_CONSTITUTION

## 2026-09-21T18:15:00Z — DP-B4 custom → DP-DONE-AUTHORITY (1A+2A+3A)
- verdict: custom (umbrella Done Authority)
- notes: 1=A full umbrella; 2=A wait clears only on honest seed-complete; 3=A finalize = master+PMQ+integrity; folds B4/B5/BUILD-HOLLOW-MIX/SHIP-HOLLOW-FINALIZE
- unlocks: implement DP-DONE-AUTHORITY
- family: HOLLOW_DONE

## 2026-09-21T18:30:00Z — DP-DONE-AUTHORITY implement complete
- verdict: landed
- notes: done_authority.py; mix refuse unseated mark; ESR may_clear_wait=seed_complete only; finalize incompleteness+PMQ stamp after persist; LLM try_mark_done; tests under MUX_FORENSICS=0
- unlocks: present DP-SOUND-SDP-CUE
- family: HOLLOW_DONE (B4/B5/BUILD-HOLLOW-MIX/SHIP-HOLLOW-FINALIZE surfaces closed)

## 2026-09-21T18:45:00Z — Done Authority footguns 1–9
- verdict: harden (no new DP)
- notes: stamp only on success + ship-gate incompleteness; mark_done raise not silent; honest_finalize_seeded cousins; LLM auto_complete StageError; pmq_well_formed; driver LUFS→PMQ; seed ImportError-only; ESR/C4 integrity master_ok
- unlocks: present DP-SOUND-SDP-CUE
- family: HOLLOW_DONE

## 2026-09-21T18:55:00Z — DP-SOUND-SDP-CUE custom A+
- verdict: custom A+ (one writer, invent soft-block, normalize+dedupe)
- notes: build_cue_slots_ssot; fold repair inject into SSOT; invent unpaid keeps planned/inject beds; canonical slot schema; Partial-safe
- unlocks: implement DP-SOUND-SDP-CUE
- family: SDP_CUE_SLOTS

## 2026-09-21T19:00:00Z — DP-SOUND-SDP-CUE implement complete
- verdict: landed
- notes: SSOT + soft-block + admit_inject; soundscape_policy + residual F-03 tests green under MUX_FORENSICS=0
- unlocks: present next open DP
- family: SDP_CUE_SLOTS closed

## 2026-09-21T19:05:00Z — DP-LOCAL-ML-RETRY
- verdict: A
- notes: shared reclaim→fixed 5s→same-class-retry once, then existing ladders; wire six runners
- unlocks: implement DP-LOCAL-ML-RETRY
- family: LOCAL_ML_RECLAIM

## 2026-09-21T19:40:00Z — DP-LOCAL-ML-RETRY implemented
- verdict: A (landed)
- notes: `heavy_task_policy.reclaim_for_same_class_retry` + `reclaim_settle_sec=5`; wired musicgen/mmaudio/chatterbox/s2s/deepfilter/stt; `test_heavy_task_policy` green under MUX_FORENSICS=0
- unlocks: present next open DP
- family: LOCAL_ML_RECLAIM closed

## 2026-09-21T19:55:00Z — DP-LOCAL-ML-RETRY footguns 1–9 hardened
- verdict: A (follow-on)
- notes: no synthetic abort; settle credits abort backoff; bind_reclaim_run; one Chatterbox fingerprint; S2S nest removed; reclaim only hang/OOM-class; kill only live Popen
- unlocks: present next open DP
- family: LOCAL_ML_RECLAIM

## 2026-09-21T20:05:00Z — DP-A3
- verdict: custom:A′′ (Global Freeze)
- notes: write-layer choke; End-A or skip on all freeze-covered docs; no cue carve-out; seat-truth artifacts; fail-closed; allowlist pass
- unlocks: implement DP-A3 A′′
- family: FREEZE_CONSTITUTION

## 2026-09-21T20:25:00Z — DP-A3 implemented
- verdict: custom:A′′ (landed)
- notes: hot-commit freeze choke (SDP/transitions + raw-escape block); omit/air_script/adjudicate fail-closed; write_plan vo_seats preserve; End-A + hitch/catastrophe/air_script_omit; selection preserve retry as epoch owner; enda tests green under MUX_FORENSICS=0
- unlocks: present next open DP
- family: FREEZE_CONSTITUTION (A3 closed; A4 still open)

## 2026-09-21T20:35:00Z — DP-A4
- verdict: A (thorough)
- notes: hard-only sticky SSOT; soft/fingerprint never; hard:False beats level=hard; config freeze_sticky_extra_stages for future; stamp level fields; matrix tests
- unlocks: implement DP-A4 thorough
- family: FREEZE_CONSTITUTION

## 2026-09-21T20:40:00Z — DP-A4 implemented
- verdict: A thorough (landed)
- notes: freeze_artifact_proves_hard SSOT; freeze_sticky_seed_stages()+config extras; soft never sticky (live+probe+contradictory level); hard sticky all core; seed_policy + platform_fault tests green MUX_FORENSICS=0
- unlocks: present next open DP
- family: FREEZE_CONSTITUTION (A2+A3+A4; A5 still open)

## 2026-09-21T21:15:00Z — DP-A4 footguns 1–7 hardened
- verdict: A thorough (follow-on)
- notes: unlock level hygiene; extras allowlist+critical denylist; FREEZE_STICKY_SEED_STAGES via __getattr__; honest EDL (marker+edl.json); CORE+seams/palettes/sanitize; docstring; hard_freeze_active=freeze_artifact_proves_hard; tests green MUX_FORENSICS=0
- unlocks: present next open DP
- family: FREEZE_CONSTITUTION

## 2026-09-21T21:25:00Z — DP-A5
- verdict: A
- notes: retain HEAD A5-1 — skip commitment only when assembly.wav missing; must_verify_commitment SSOT; no expand
- unlocks: implement DP-A5 A (confirm + pin test)
- family: MIX_JUNCTION_SEAT

## 2026-09-21T21:26:00Z — DP-A5 implemented
- verdict: A (retained)
- notes: HEAD already correct; pin test_must_verify_commitment; gate matrix A5 green under MUX_FORENSICS=0
- unlocks: present next open DP
- family: MIX_JUNCTION_SEAT (A5 closed)

## 2026-09-21T21:35:00Z — DP-VO1
- verdict: A+
- notes: ladder-complete SSOT; Partial never auto_accept on synth entry; framing auto-accept kept; G1 automation_pending ≠ ladder-complete; NESTED/LAYUP/B1 stay separate
- unlocks: implement DP-VO1 A+
- family: VO_LADDER_PARTIAL

## 2026-09-21T21:45:00Z — DP-VO1 implemented
- verdict: A+ (landed)
- notes: vo_ladder_complete + synth_entry_may_auto_accept; vo_synthesize/G1/API honor ladder; Partial no synth-entry stamp; operator-gates.md; tests green MUX_FORENSICS=0
- unlocks: present next open DP (NESTED-SYNTH / LAYUP-ADJ / B1)
- family: VO_LADDER_PARTIAL (VO1 closed; cousins remain)

## 2026-09-21T21:55:00Z — DP-VO1 footguns 1–5 + A4 EDL spine hardened
- verdict: A+ (follow-on)
- notes: vo_synth_mint_allowed (Partial=ladder); G8 allow_rewrite=False + probe fail-closed; adjudicate never is_done fallback; G1 wait_vo_ladder message; EDL sticky requires version+ids/typed clips; Partial nested skip when ladder open
- unlocks: present next open DP
- family: VO_LADDER_PARTIAL

## 2026-09-21T22:05:00Z — DP-B1+B2+B3+B6 (PIN_PREMATURE family batch)
- verdict: A / A / A / A
- notes: comprehensive retain HEAD — longest/specific compound; exact-token not substring; unknown premature→transitions; single incompleteness_resume_stage; high-coverage matrix
- unlocks: implement PIN family closeout
- family: PIN_PREMATURE

## 2026-09-21T22:15:00Z — DP-B1+B2+B3+B6 implemented
- verdict: A batch (landed)
- notes: SSOT docs on producer_pin_for_token + incompleteness_resume_stage; test_pin_premature_family.py matrix; r4/hx2 green MUX_FORENSICS=0
- unlocks: present next open DP
- family: PIN_PREMATURE closed

## 2026-09-21T22:20:00Z — DP-NESTED-SYNTH
- verdict: A
- notes: KEEP skip-not-stamp; seal fail-open except→mint holes; Partial never nested auto_accept (VO1 already paved ladder)
- unlocks: implement DP-NESTED-SYNTH A
- family: VO_LADDER_PARTIAL / nested mint

## 2026-09-21T22:25:00Z — DP-NESTED-SYNTH implemented
- verdict: A (landed)
- notes: resync gap/transitions fail-closed on probe error; nested_synth_may_mint probe fail-closed; test_nested_synth_skip probe paths green MUX_FORENSICS=0
- unlocks: present next open DP (LAYUP-ADJ or C1)
- family: VO_LADDER_PARTIAL (nested mint sealed)

## 2026-09-21T23:10:00Z — DP-LAYUP-ADJ
- verdict: A
- notes: MUST_PRECEDE+G8 sole order SSOT; clamp heal/resume; no phase move; prevent layup→adjudicate→synth leapfrog thrash
- unlocks: implement DP-LAYUP-ADJ A
- family: VO_LADDER_PARTIAL / layup-adjudicate order

## 2026-09-21T23:25:00Z — DP-LAYUP-ADJ implemented
- verdict: A (landed)
- notes: expanded MUST_PRECEDE VO chain; clamp_resume_through_order on VO clamp stages; heal_navigate/_accept_pin/resume_producer; test_must_precede_order LAYUP matrices green MUX_FORENSICS=0
- unlocks: present next open DP (C1 lean / ESR family)
- family: VO_LADDER_PARTIAL (order cousin sealed; family closable when matrix updated)

## 2026-09-21T23:40:00Z — DP-C1+C2+C3+C4
- verdict: A (ESR_POST_MASTER family batch)
- notes: retain HEAD post-master never-thrash-wait; shared SSOT helpers; C5 ship-bar separate
- unlocks: implement ESR family thorough seal
- family: ESR_POST_MASTER

## 2026-09-21T23:55:00Z — DP-C1+C2+C3+C4 implemented
- verdict: A (landed thorough)
- notes: post_master_never_wait / skip_post_master_mtime_lease / C2 may_clear_wait; test_esr_post_master_family.py matrix green MUX_FORENSICS=0; docs/execution-status.md
- unlocks: present DP-C5 or BUILD-ASSEMBLY-FRESHNESS
- family: ESR_POST_MASTER closed

## 2026-09-22T00:10:00Z — DP-C5
- verdict: A
- notes: pipeline_complete = sole local ship-bar SSOT; G-Publish/S3 consent separate; align ESR/driver/docs/tests
- unlocks: implement DP-C5 A thorough
- family: SHIP_BAR_VOCAB

## 2026-09-22T00:25:00Z — DP-C5 implemented
- verdict: A (landed thorough)
- notes: package_ready envelope; ship_bar_complete/reasons; driver fallback; test_ship_bar_vocab.py green MUX_FORENSICS=0; SHIP_BAR_VOCAB closed
- unlocks: present BUILD-ASSEMBLY-FRESHNESS or PRE-PARTIAL
- family: SHIP_BAR_VOCAB closed

## 2026-09-22T00:40:00Z — footgun harden pass (5)
- notes: (1) VO downstream clamp when VO hole open (2) Skip≠pipeline_complete (3) unseated mix before ship advance (4) nested framing probe fail-closed all modes (5) C4 hold lease on pending/fresh wavs; test_footgun_harden_pass.py green MUX_FORENSICS=0
- unlocks: PROGRESS_NOW
- family: cross-cut residual seal

## 2026-09-22T01:00:00Z — DP-BUILD-ASSEMBLY-FRESHNESS
- verdict: **custom HAU** (Heard-Assembly Unification)
- notes: HAU; Partial+Full-auto; optional_beds_until_remaster; fold dual-admit cousins only; C+A federal (one heard-assembly SSOT + music after seated / explicit preview_music gate); Partial never auto preview-music; keep A5 commitment
- unlocks: implement HAU
- family: MIX_JUNCTION_SEAT / assembly freshness

## 2026-09-22T01:45:00Z — DP-BUILD-ASSEMBLY-FRESHNESS implemented (HAU)
- verdict: custom HAU landed
- notes: federal may_admit_music (seated|preview_music); heard_assembly SSOT; speech-first beds all modes; delivery_stable_for_music + agenda refuse dual OR; operator POST …/milestones/preview-music; test_hau_assembly_freshness.py + seat/HX-1 updates green MUX_FORENSICS=0
- unlocks: PROGRESS_NOW → PRE-PARTIAL go/no-go
- family: MIX_JUNCTION_SEAT assembly-freshness cousin closed

## 2026-09-22T01:55:00Z — HAU footgun harden (6)
- notes: (1) close clears preview_music_at (2) bare mix_epoch_block no speech-first (3) speech-first needs preview|unseated (4) music_epoch remaster → mix re-land not junction (5) preview-era remaster when seat predated beds (6) gui-only preview_music open; test_hau_footgun_harden.py green MUX_FORENSICS=0
- unlocks: PROGRESS_NOW
- family: HAU residual seal

## 2026-09-22T02:10:00Z — DP-PRE-PARTIAL
- verdict: **A** — Launch + companion; soak-gate residuals
- notes: Launch Partial Mohan 0.2.0; companion watch; no forensics; soak-gates BUDGET_THRASH + premix→incomplete_cut + dual-render surprises — stop and open DP if they dominate (do not silent-ignore)
- unlocks: launch Partial proof (operator starts run; companion attaches to exec_*)
- family: campaign gate

## 2026-09-21T22:46:00Z — DP-GAP-PICKUP-CONFIRM
- verdict: **A**
- notes: stamp `stage_key="missing_framing"` on pickup/adaptation writers owned by missing_framing; declare `flow_adaptation` on missing_framing StageInfo; HEAD test under active gap_framing_compose
- unlocks: implement DP-GAP-PICKUP-CONFIRM (IMPLEMENT_NEXT)
- family: OWNERSHIP_STAGE_KEY

## 2026-09-21T22:50:00Z — DP-GAP-PICKUP-CONFIRM implemented (A)
- verdict: A landed
- notes: confirm_pickup_speaker + apply_flow_adaptation_patch + gap_fill_eligibility skip/clear stamp stage_key; missing_framing StageInfo declares flow_adaptation; tests/test_gap_pickup_confirm_stage_key.py green MUX_FORENSICS=0
- unlocks: resume Partial exec_13168 (clear needs_operator / continue from gap_framing_compose)
- family: OWNERSHIP_STAGE_KEY (pickup surface closed; refresh_conformance mirrored write remains follow-on if soak hits)

## 2026-09-21T23:04:00Z — DP-BUD1
- verdict: **A**
- notes: fingerprint/product-delta reclaim of identity attempt + attempt_memo; refuse must not emit stage-success Finished; HEAD tests under MUX_FORENSICS=0
- unlocks: implement DP-BUD1 (IMPLEMENT_NEXT)
- family: BUDGET_THRASH

## 2026-09-21T23:14:00Z — DP-BUD1 implemented (A)
- verdict: A landed
- notes: reclaim_budget_on_product_flip (Partial + memo-stale); evaluate_dispatch once-per-ctx reclaim; refuse tracks `_dispatch_refuses`; runner writes `incomplete` not Finished when outputs missing; gap_framing_compose stops walk on incomplete refuse; tests/test_bud1_product_reclaim.py green MUX_FORENSICS=0
- unlocks: resume Partial exec_13168 from gap_framing_compose
- family: BUDGET_THRASH (resume-after-fix + hollow Finished closed; soak residual if thrash on same fp)
