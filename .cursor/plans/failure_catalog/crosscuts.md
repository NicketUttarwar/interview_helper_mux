# Cross-cut vulnerable junctions (HEAD)

Identify-only. Brain 0.1.0. Modes: Manual / Full-auto / Partial.

---

### XC-PREMATURE-01 — premature_cap → heal_navigate music↔narrative pin

- Surface: cross-cut
- Modes: Full-auto | Partial (driver heals); Manual (resume CTA)
- Brain: 0.1.0
- Call graph: `delivery_guardrails.premature_cap_hard_pin` → `thrash_hardening.heal_navigate` / `canonical_resume_pin` / `_music_epoch_producer_pin`
- Invariant: pin earliest incomplete **producer**, never consumer alone
- Why weak: exception paths fall through; music-epoch class can still interact with Phase-A EDL pins when selection missing; leased expensive stage can stick
- Manifestation: oscillating `--from-stage`; `class_failure … premature_complete:music_epoch`; wasted_work `music_deferred`
- Heal/stop: sticky heal ×3 → needs_operator; identical_failures halt (unless MUX_FORENSICS)
- Footgun: Manual “Run mix” while music incomplete
- Likelihood: L2 | Severity: S4
- Evidence: `delivery_guardrails.py:premature_cap_hard_pin`, `thrash_hardening.py:heal_navigate`
- Fix-cluster: `heal-navigate-pins`
- Status: LIKELY_MITIGATED_ON_HEAD (guards present; residual fallthrough OPEN via exceptions)

### XC-PREMATURE-02 — premature_cap exception swallow

- Surface: cross-cut
- Modes: all
- Call graph: multiple `except Exception: pass` around heal_navigate imports in `premature_cap_hard_pin`
- Invariant: pin logic always applies
- Why weak: import/runtime errors silently degrade to weaker walkback
- Likelihood: L2 | Severity: S3
- Evidence: `delivery_guardrails.py:1167+`
- Fix-cluster: `heal-navigate-pins`
- Status: OPEN_RISK

### XC-SEED-01 — may_rewind_to_vo_synthesize monotonic delivery

- Surface: cross-cut
- Modes: all
- Call graph: `may_rewind_to_vo_synthesize` ← agenda/driver unmark paths; uses G1 check, seated_vo_missing, transition pair freeze
- Invariant: after assembly+G1 green, no VO rewind for deferred-only pairs
- Why weak: broad `except: return True` on G1 check failure allows rewind; script↔WAV paths must stay aligned with vo_synthesis_audit
- Likelihood: L2 | Severity: S4
- Evidence: `delivery_guardrails.py:may_rewind_to_vo_synthesize`
- Fix-cluster: `monotonic-vo`
- Status: OPEN_RISK (fail-open on G1 exception)

### XC-SEED-02 — seed cycle detect / g1_vo_open fake stage

- Surface: cross-cut
- Modes: Full-auto | Partial
- Call graph: `delivery_invariants.detect_seed_cycle`, `resolve_g1_vo_open_resume`, recovery playbooks
- Invariant: never resume unknown `g1_vo_open` as from_stage
- Why weak: any remaining string `g1_vo_open` in resume maps → Unknown from_stage suicide
- Likelihood: L2 | Severity: S4
- Evidence: `delivery_invariants.py:detect_seed_cycle`
- Fix-cluster: `g1-vo-seed-cycle`
- Status: LIKELY_MITIGATED_ON_HEAD (helpers exist; audit all call sites still needed)

### XC-MUSIC-01 — music_epoch_complete / mix deferral

- Surface: cross-cut
- Modes: all
- Call graph: `music_epoch_complete` → `filter_delivery_candidates` / `mix_epoch_block` / `safe_mix_resume_stage`
- Invariant: mix not scheduled until music epoch complete (G5 + MUSIC_BEFORE_MIX + SDP WAV parity)
- Why weak: stamp/complete_at with stub WAVs; break seal ↔ remint loops; hollow mmaudio QA historically
- Likelihood: L2 | Severity: S4
- Evidence: `delivery_guardrails.py:music_epoch_complete`
- Fix-cluster: `music-epoch`
- Status: LIKELY_MITIGATED_ON_HEAD

### XC-IDENT-01 — identical×3 halt vs forensics suppress

- Surface: cross-cut
- Modes: Manual | Full-auto | Partial (**halt must work**); Forensics env = footgun
- Call graph: `identical_failures.record_failure` → `is_halted` → driver stop
- Invariant: same fingerprint ×3 → halt needs_operator
- Why weak: `forensics_mode()` forces `is_halted` False; cascade_suppressed; rotating seg IDs may never hit ×3
- Likelihood: L3 (if env set) / L2 (signature rotation) | Severity: S4
- Evidence: `identical_failures.py:is_halted`, `forensics_mode`
- Fix-cluster: `identical-halt-honesty`
- Status: OPEN_RISK

### XC-STICKY-01 — sticky heal / true_waste

- Surface: cross-cut
- Modes: Full-auto | Partial
- Call graph: `thrash_hardening.note_sticky_heal_attempt`, `record_wasted_work` → `maybe_sticky_halt_on_true_waste` — **`maybe_sticky_halt_on_true_waste` since deleted** (guardrail subtraction, W0; see `docs/cross-cutting/subtraction-holes.md` §1.4); graph left as recorded
- Invariant: unchanged predicate ×3 → halt
- Why weak: clear-halts wrongly applied; false sticky mid-delivery; GUI reconcile races
- Likelihood: L2 | Severity: S3
- Evidence: `thrash_hardening.py`, `delivery_guardrails.record_wasted_work`
- Fix-cluster: `sticky-heal-halt`
- Status: LIKELY_MITIGATED_ON_HEAD

### XC-SHIP-01 — ship_path_ready vs pending master

- Surface: cross-cut
- Modes: all
- Call graph: `ship_path_ready` requires assembly, mix, junction seed-complete, commitment match, delight; `committed_master_wav` for SHIP_AFTER_MASTER filter
- Invariant: pending `.pending_writes/**/master/master.wav` must not imply ship-ready
- Why weak: other modules still use bare `artifact_exists("master/master.wav")` — can disagree with committed_master_wav
- Likelihood: L2 | Severity: S3
- Evidence: `delivery_guardrails.ship_path_ready`, `delivery_invariants.committed_master_wav`; call sites: `llm_flow_hardening.py:406`, `web/runner.py:1391`, `web/server.py:1994`, `journey_state.py:199`, `post_master_quality.py:260,861`, `asset_transcripts.py:870`
- Fix-cluster: `committed-master-honesty`
- Status: OPEN_RISK

### XC-SHIP-02 — ship_path_ready commitment match vs tests

- Surface: cross-cut
- Modes: all
- Call graph: `ship_path_ready` → `_junction_commitment_matches_assembly`
- Invariant: junction commitment must match live assembly size/sha
- Why weak: HEAD diagnostic — `tests/test_delivery_guardrails.py::test_ship_path_ready_pins_finalize` expects `ready is True` after mocking seed_complete but without commitment match → **fails on HEAD** (product/test skew). Real runs need commitment fields populated or ship-ready stays false → finalize pin thrash
- Likelihood: L3 | Severity: S3
- Evidence: `delivery_guardrails.ship_path_ready` + failing HEAD test (observation only; no patch in this campaign)
- Fix-cluster: `junction-remaster`
- Status: OPEN_RISK

### XC-REMUTATE-01 — active_remutate_stages protect

- Surface: cross-cut
- Modes: Full-auto | Partial (driver); Manual remutate CTAs
- Call graph: `delivery_invariants.active_remutate_stages` ← driver restamp skips; listen_delight_remutate + edl_narrative_remutate JSON
- Invariant: stages cleared by remutate not restamped complete
- Why weak: any heal path that only checks one remutate JSON kind can bypass
- Likelihood: L2 | Severity: S3
- Evidence: `delivery_invariants.active_remutate_stages`, `tools/full_auto_driver.py` remutate_protect
- Fix-cluster: `remutate-chain`
- Status: LIKELY_MITIGATED_ON_HEAD

### XC-REMUTATE-02 — listen_delight remutate must re-enter seams→EDL not mix-only

- Surface: cross-cut
- Modes: all
- Call graph: listen_delight remutate planners → air_script_seams / transitions / VO / EDL
- Invariant: conversation_fit / story_followability floors force structural remutate not mix-only noop
- Why weak: mix-only remutate paths can burn budget without predicate flip
- Likelihood: L2 | Severity: S3
- Evidence: `listen_delight_remutate` module (HEAD)
- Fix-cluster: `remutate-chain`
- Status: OPEN_RISK (verify all resume pins)

### XC-JUNCTION-01 — remaster oscillation / budget

- Surface: cross-cut
- Modes: all
- Call graph: `junction_snip_qa._budgeted_remaster_mix` → `note_junction_oscillation_halt` / G-Listen re-arm
- Invariant: bounded remasters; e2e soft must not green critical residuals
- Why weak: remaster without seating/EDL flip; G-Listen re-arm loops; soft residual flags
- Likelihood: L2 | Severity: S4
- Evidence: `junction_snip_qa.py`, `thrash_hardening.junction_remaster_budget_ok`
- Fix-cluster: `junction-remaster`
- Status: LIKELY_MITIGATED_ON_HEAD

### XC-HOLLOW-01 — incompleteness coverage gap on many analysis stages

- Surface: cross-cut
- Modes: all
- Call graph: `stage_artifact_incompleteness` only specializes subset (vo, layup, mmaudio, edl, sanitize, SDP, …)
- Invariant: every producer stage refuses hollow mark_done
- Why weak: majority of ANALYSIS_ORDER stages have **no** dedicated incompleteness branch — rely on generic checks / none
- Likelihood: L3 | Severity: S2
- Evidence: stage_completion.py stage_id branches vs ANALYSIS_ORDER (inventory script)
- Fix-cluster: `hollow-done-coverage`
- Status: OPEN_RISK

### XC-STAGING-01 — pending_writes shadow consumers

- Surface: cross-cut
- Modes: all
- Call graph: `write_staging` flush / discard_pending_shadows; consumers `read_json` committed paths
- Invariant: consumers never treat unflushed pending as complete unless intentional
- Why weak: seed-order thrash when WAVs only under pending; discard wipes unflushed; commit_barrier_halt
- Likelihood: L2 | Severity: S3
- Evidence: `write_staging.py`, `stage_acceptance.py`
- Fix-cluster: `pending-flush-honesty`
- Status: OPEN_RISK

### XC-VO-01 — vo_contract seats / clamp / script↔WAV

- Surface: cross-cut
- Modes: all
- Call graph: `vo_contract.ensure_hosted_framing_vo_seats` / `clamp_hosted_seats_to_rendered_wavs`; `vo_synthesis_audit` bind hash
- Invariant: one writer authority; clamp after seat mutate; never stamp audit on old bytes
- Why weak: any omit/heal path missing terminal clamp; silent rebind refused but alternate writers may drift
- Likelihood: L2 | Severity: S4
- Evidence: `vo_contract.py`, `vo_synthesis_audit.py`
- Fix-cluster: `vo-seat-authority`
- Status: LIKELY_MITIGATED_ON_HEAD

### XC-INV-01 — heal-only vs structural invalidation

- Surface: cross-cut
- Modes: all (+ G-DeliveryUnlock when locked)
- Call graph: `execution_invalidation_profiles` / `artifact_lifecycle` / `air_order_integrity` / agenda `invalidate_downstream`
- Invariant: heal-only must not archive live EDL/assembly needed by finalize; structural needs unlock when epoch locked
- Why weak: wrong profile → clear_from archives heal target; BD shared boundaries self-stale
- Likelihood: L2 | Severity: S4
- Evidence: `artifact_lifecycle.py`, `execution_invalidation_profiles.py`
- Fix-cluster: `invalidation-blast`
- Status: OPEN_RISK

### XC-DUAL-01 — dual-driver / unstick

- Surface: cross-cut
- Modes: Full-auto | Partial
- Call graph: `driver_singleton` claim; `delivery_unstick`; serve `on_serve_restart_harden`
- Invariant: one healer per run
- Why weak: stale claim after crash; second ensure_e2e without force
- Likelihood: L2 | Severity: S3
- Evidence: driver_singleton / delivery_unstick modules
- Fix-cluster: `dual-driver`
- Status: LIKELY_MITIGATED_ON_HEAD

### XC-LLM-01 — llm_simple max 2 then hard stop

- Surface: LLM
- Modes: all
- Call graph: `llm_simple.run_llm_stage_simple` ← analysis_stage / delivery runners / homunculus
- Invariant: schema validate → ≤2 attempts → StageError hard stop (no arbiter UI)
- Why weak: operator/Manual must from-stage after fix; Full-auto heal must map StageError to producer pin or identical halt
- Likelihood: L2 | Severity: S3
- Evidence: `llm_simple.py`, docs operator-gates LLM failures
- Fix-cluster: `llm-hard-stop-routing`
- Status: OPEN_RISK

### XC-AUTH-01 — authority_undo / hash oscillation

- Surface: cross-cut
- Modes: Full-auto | Partial
- Call graph: sanitize/authority thrash detectors on SDP / transitions / gap_report
- Invariant: oscillating hash/action must halt not infinite rewrite
- Why weak: detectors may not cover all JSON mutators
- Likelihood: L2 | Severity: S3
- Evidence: sanitize_authority / thrash modules (HEAD)
- Fix-cluster: `authority-undo`
- Status: OPEN_RISK

---

## Wave-2 elevations

### XC-MIX-EPOCH-NOOP — mix_epoch_block returns None when Phase A unsealed + unstable
- Likelihood: L2 | Severity: S3 | Status: OPEN_RISK | Fix-cluster: `music-epoch`
- Evidence: `delivery_guardrails.mix_epoch_block` (swarm VJ-07)

### XC-DELIGHT-WAIVER — ensure_listen_delight_waiver_unattended
- Likelihood: L3 | Severity: S3 | Status: OPEN_RISK | Fix-cluster: `delight-authoritative`
- Evidence: `delivery_guardrails.ensure_listen_delight_waiver_unattended` (swarm VJ-15)

### XC-LEASE-STICKY — expensive_stage_lease short-circuits premature_cap
- Likelihood: L2 | Severity: S2 | Status: OPEN_RISK | Fix-cluster: `heal-navigate-pins`
- Evidence: swarm VJ-01
