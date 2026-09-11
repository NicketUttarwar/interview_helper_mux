# GUI + API user-action vulnerable junctions

Identify-only. Brain 0.1.0.

## API surface (server.py — selected)

| Method | Path | Risk note |
|--------|------|-----------|
| POST | `/api/runs` | Mode/brain/podcast lock; wrong mode footgun |
| GET | `/api/runs/{id}` | Gate honesty / operator_gates payload |
| POST | `/api/runs/{id}/homunculus/skip-stage` | Skip without artifact |
| POST | `/api/runs/{id}/escalations/{stage}/resolve` | Wrong option |
| POST | `/api/runs/{id}/delivery/recover` | Mis-aimed recover |
| POST | `/api/runs/{id}/delivery/unlock` | Structural unlock |
| POST | `/api/runs/{id}/delivery/unstick` | Clears thrash pins — can unstick wrong |
| PUT/PATCH | NLE endpoints | Cascade re-rank |
| Gate POSTs | g1 / gap-framing / g-listen / g-publish | Mode auto-accept differences |

---

### GUI-START-01 — mode/brain/podcast selection

- Surface: GUI
- Modes: all (chosen here)
- Call graph: Start tab → POST /api/runs → run_meta
- Invariant: homunculus_version never changes mid-run; mode drives driver
- Why weak: pick Full-auto intending Partial; wrong brain 0.0.0 vs 0.1.0; dual start while claim held
- Likelihood: L3 | Severity: S3
- Evidence: Start UI; `homunculus/version.py`; driver_singleton
- Fix-cluster: `start-mode-lock`
- Status: OPEN_RISK

### GUI-OVERLAY-01 — partialAcceleratedGuard busy block

- Surface: GUI
- Modes: Partial
- Call graph: `partialAcceleratedGuard.ts` → ActionOverlay / PrecleanOffer / LiveStatusBar
- Invariant: block operator actions while driver active except G0/G-Framing/G-Publish/gate status
- Why weak: exception list incomplete → click during VO thrash; or over-block legitimate checkpoint
- Likelihood: L2 | Severity: S3
- Evidence: `frontend/src/utils/partialAcceleratedGuard.ts`
- Fix-cluster: `partial-overlay`
- Status: OPEN_RISK

### GUI-PIPE-01 — PipelineTab Run from stage

- Surface: GUI
- Modes: Manual (primary); blocked under Partial busy
- Call graph: from-stage → runner → dispatch
- Invariant: from-stage pins producer
- Why weak: operator picks consumer (mix/finalize) while producer incomplete → premature_cap fight
- Likelihood: L3 | Severity: S3
- Evidence: PipelineTab; premature_cap_hard_pin
- Fix-cluster: `heal-navigate-pins`
- Status: OPEN_RISK

### GUI-BANNER-01 — NEEDS YOU / PhaseGuidance honesty

- Surface: GUI
- Modes: all
- Call graph: operator_gates.operator_must_act → PhaseGuidanceBanner
- Invariant: banner only when human required
- Why weak: Partial automation_pending suppresses G1; sticky needs_operator after heal cleared; false complete
- Likelihood: L2 | Severity: S1
- Evidence: PhaseGuidanceBanner; gui_job_reconcile
- Fix-cluster: `gate-banner-honesty`
- Status: OPEN_RISK

### GUI-HOM-01 — HomunculusPanel skip / conductor visibility

- Surface: GUI
- Modes: 0.1.0 runs
- Call graph: skip-stage API; conductor state display
- Why weak: skip stage without understanding seed incompleteness; misleading “why pinned”
- Likelihood: L2 | Severity: S2
- Evidence: HomunculusPanel; delivery_pin_summary
- Fix-cluster: `homunculus-tool-surface`
- Status: OPEN_RISK

### GUI-QC-01 — QcSummary / delight / PMQ display

- Surface: GUI
- Modes: all
- Why weak: advisory_fail shown as hard fail or vice versa; publish_allowed vs local encode confusion
- Likelihood: L2 | Severity: S1
- Fix-cluster: `g-publish-consent`
- Status: OPEN_RISK

### GUI-GATES-01 — gate panels batch footguns

- Surface: GUI
- Modes: all
- Panels: TranscriptReview, GapFraming*, PickupSpeaker, VoiceReference, GapDelivery, VoPickup, GListen, GPublish*, TimelineOptimizer, PrecleanOffer, OmitLedger, Sfx*, etc.
- Why weak: each has accept/skip/refuse; Partial overlay interactions; double-submit
- Likelihood: L2 | Severity: S2
- Evidence: `frontend/src/components/gates/*`
- Fix-cluster: `gui-gate-panels`
- Status: OPEN_RISK

### API-UNSTICK-01 — delivery/unstick

- Surface: API
- Modes: Full-auto | Partial | Manual thrash
- Call graph: `delivery_unstick.run_delivery_unstick`
- Why weak: clears sticky without fixing producer → immediate re-halt; operator hammer
- Likelihood: L2 | Severity: S3
- Evidence: server unstick route; delivery_unstick
- Fix-cluster: `dual-driver`
- Status: OPEN_RISK

### GUI-OVERLAY-02 — checkpoint exception list drift

- Surface: GUI
- Modes: Partial
- Call graph: `isPartialAutoCheckpoint` — lifts overlay for: transcript_review, gap_framing (unless automation_pending), pickup_speaker, job statuses gate/needs_operator/needs_clarification/awaiting_write_approval, stage_reuse, gPublish pending+package_ready
- Why weak: `OPERATOR_BLOCK_REASONS` includes legacy `g1_5_preview_pickup`, `handoff_review`, `write_approval` — product removed some gates; G-Listen / DeliveryUnlock / VoiceRef may not lift overlay consistently; `gap_framing` + `automation_pending` keeps overlay (driver resolving) — operator cannot intervene mid-auto-Yes
- Likelihood: L3 | Severity: S3
- Evidence: `frontend/src/utils/partialAcceleratedGuard.ts`
- Fix-cluster: `partial-overlay`
- Status: OPEN_RISK

### GUI-OVERLAY-03 — DELIVERY_ORDER_5C frontend slice vs backend DELIVERY_ORDER

- Surface: GUI
- Modes: Partial
- Call graph: `DELIVERY_ORDER_5C` in partialAcceleratedGuard vs full `DELIVERY_ORDER` in config
- Why weak: order-violation helper only covers 5C slice — earlier delivery thrash (layup→transitions) not guarded by this helper
- Likelihood: L2 | Severity: S2
- Evidence: `partialAcceleratedGuard.ts:DELIVERY_ORDER_5C`
- Fix-cluster: `partial-overlay`
- Status: OPEN_RISK
