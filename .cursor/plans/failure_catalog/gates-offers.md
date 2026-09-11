# Gates & offers — vulnerable junctions

Identify-only. Modes: Manual / Full-auto / Partially accelerated. Brain 0.1.0.

---

### GATE-G0-01 — mandatory transcript review

- Surface: gate
- Modes: Manual (always human) | Full-auto (auto-accept if soft/auto_accept) | Partial (**never** auto)
- Call graph: `transcript_review_build` → G0 panel → accept API → unlock analysis
- Invariant: Partial never auto-clears G0; wrong words poison all downstream
- Why weak: Full-auto auto-accept can ship bad STT; Manual skip paths if any; Partial prepare-until-G0 defers preclean
- Likelihood: L2 | Severity: S2
- Evidence: `gates.py` / transcript review; `automation_run.PARTIAL_AUTO_PREPARE_UNTIL_G0`; `e2e_soft.py`
- Fix-cluster: `mode-gate-honesty`
- Status: OPEN_RISK (Full-auto STT quality) / LIKELY_MITIGATED (Partial never auto — if enforced all paths)

### GATE-GFRAME-01 — Yes/No sticky authority vs 0.1.0 auto-Yes

- Surface: gate
- Modes: all
- Call graph: G-Framing panel → `gap-framing/enable`; `framing_posture_decide` advisory only; 0.1.0 auto-Yes for hosted 1:1 when unset
- Invariant: explicit operator No/Yes never overwritten by auto_accept
- Why weak: race between auto-resolve and operator click; advisory shown as authority
- Likelihood: L2 | Severity: S2
- Evidence: operator-gates.md; gap framing modules
- Fix-cluster: `g-framing-authority`
- Status: OPEN_RISK

### GATE-GFRAME-02 — Speaker / VoiceRef / Delivery ladder

- Surface: gate
- Modes: when G-Framing Yes
- Call graph: PickupSpeakerPanel → VoiceReferencePanel → GapDeliveryPanel → G1
- Invariant: clone = least-spoken/frame host never guest; voice-ref must exist before Chatterbox
- Why weak: wrong speaker pick; voice-ref gate blocks topic_coverage; Full-auto auto path may proceed with thin refs
- Likelihood: L2 | Severity: S3
- Evidence: `gap_vo_gates.py`, VoiceReferencePanel
- Fix-cluster: `g-framing-ladder`
- Status: OPEN_RISK

### GATE-G1-01 — optional skip vs seated floor

- Surface: gate
- Modes: all
- Call graph: G1 skip-optional / synthesize-all / record → vo seats; `g1_optional` config
- Invariant: skip optional must not leave contract requiring seated WAVs; min_synthetic_vo_lines is post-layup ship bar
- Why weak: skip then later seat floor thrash; Partial automation_pending hides banner while synth pending
- Likelihood: L2 | Severity: S3
- Evidence: `gates.check_g1_vo`, vo_contract floor helpers
- Fix-cluster: `g1-vo-seed-cycle`
- Status: OPEN_RISK

### GATE-GLISTEN-01 — warn vs block + remaster re-arm

- Surface: gate
- Modes: all
- Call graph: after mix when `g_listen_recommended`; continue/skip APIs; junction remaster may set pending again
- Invariant: warn mode advisory; block mode hard-stop; remaster should not infinite re-arm
- Why weak: remaster → G-Listen pending loop; operator Skip vs Continue confusion
- Likelihood: L2 | Severity: S3
- Evidence: `junction_snip_qa._set_g_listen_pending_after_remaster`; g_listen_mode config
- Fix-cluster: `junction-remaster`
- Status: OPEN_RISK

### GATE-GPUB-01 — prepare vs S3 consent

- Surface: gate
- Modes: Manual | Full-auto (soft prepare) | Partial (**never auto S3**)
- Call graph: GPublishPanel → prepare local package; sync script separate; advisories gate S3
- Invariant: PMQ publish_allowed vs advisory_fail; Partial never auto-upload
- Why weak: operator thinks Prepare uploaded; Full-auto soft vs quality waiver confusion
- Likelihood: L2 | Severity: S2
- Evidence: GPublishPanel; sync_assets / podcast publish stages
- Fix-cluster: `g-publish-consent`
- Status: OPEN_RISK

### GATE-UNLOCK-01 — G-DeliveryUnlock epoch

- Surface: gate
- Modes: all after Phase A seal
- Call graph: `POST .../delivery/unlock` with reason; structural invalidation blocked when locked
- Invariant: heal-only proceeds; structural needs unlock
- Why weak: wrong classification → permanent block or silent wipe
- Likelihood: L2 | Severity: S3
- Evidence: delivery epoch lock; server unlock route
- Fix-cluster: `invalidation-blast`
- Status: OPEN_RISK

### GATE-AIR-01 — G-AirOrder warn-only default

- Surface: gate (informational)
- Modes: all
- Call graph: air_order_integrity on selection mutations; PMQ backstop optional
- Invariant: default warn; block flags opt-in
- Why weak: integrity critical loops while warn-only → silent bad air order until PMQ
- Likelihood: L2 | Severity: S2
- Evidence: air-order-boundary.md; `air_order_integrity.py`
- Fix-cluster: `air-order-policy`
- Status: OPEN_RISK

### OFFER-PRECLEAN-01 — never auto-run

- Surface: offer
- Modes: Manual/Full-auto offer early; Partial defers after G0
- Why weak: dismiss then poor STT; accept mid-run checksum churn
- Likelihood: L2 | Severity: S1
- Fix-cluster: `partial-prepare-order`
- Status: OPEN_RISK

### OFFER-NLE-01 — Timeline split cascade re-rank

- Surface: offer
- Modes: Manual primarily
- Why weak: split after ranking without understanding cascade cost; Full-auto may ignore NLE
- Likelihood: L2 | Severity: S2
- Fix-cluster: `nle-cascade`
- Status: OPEN_RISK

### OFFER-OPT-01 — Timeline optimizer endless daemon

- Surface: offer
- Modes: after mix
- Why weak: Take best vs Keep optimizing vs Stop; remaster side effects; CPU burn
- Likelihood: L2 | Severity: S2
- Fix-cluster: `timeline-optimizer`
- Status: OPEN_RISK

### ESC-01 — resilience escalations resolve options

- Surface: API / GUI
- Modes: all
- Call graph: `POST .../escalations/{stage}/resolve` — retry_stage, skip_optional_vo, prepare_local_package_only; force_publish rejected on Manual
- Why weak: wrong resolve option; soft_ship rejected but confusion remains
- Likelihood: L2 | Severity: S2
- Fix-cluster: `escalation-resolve`
- Status: OPEN_RISK
