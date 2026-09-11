# Swarm wave-2 synthesis (HEAD identify-only)

Merged from parallel research agents after initial catalog delivery. Deduped against INDEX; elevates previously under-weighted risks.

## New / elevated P0–P1 (add to ranked reviews)

### SYN-SHAPE-01 — Research/Shape soft-gate stub vs prompt cutover
- Surface: stage / LLM (unwired)
- Modes: Manual | Full-auto | Partial
- Finding: `mastering_research_*` = existence probes; Shape agenda/candidates/synthesize = heuristics (`cands[0]`, fake scores); L0–L5 / critics / flagship prompts under `docs/prompts/mastering/` largely unwired. Real LLM in this band: `missing_framing`, `gap_framing_compose` only.
- Why weak: docs imply mutation engine; production ships soft-gate + gap LLMs; Pass2 confirm before compose; plan `ordered_segment_ids` often tape order
- Likelihood: L3 | Severity: S2–S3
- Evidence: `mastering_research.py`, `mastering_shape_runtime.py`, `docs/prompts/mastering/README.md`
- Fix-cluster: `research-shape-llm-cutover` (+ `FC-pass2-confirm`, `FC-order-timing`)
- Status: OPEN_RISK

### SYN-SCHEMA-01 — Empty `{}` skips artifact schema validation
- Surface: LLM / completeness
- Call graph: `prompt_validation.validate_stage_artifacts` — empty artifacts return []
- Likelihood: L3 | Severity: S3
- Fix-cluster: `schema-hollow-gate`
- Status: OPEN_RISK

### SYN-SCHEMA-02 — Required arrays allow hollow `[]`
- Surface: LLM
- Stages include: missing_framing evaluations, gap lines, nuggets, layups, VO adjudicate lines, transitions, chapters, topic_mappings, seams, topics, synthetic lines
- Likelihood: L3 | Severity: S2
- Fix-cluster: `schema-hollow-gate`
- Status: OPEN_RISK

### SYN-PACK-01 — Conductor pack injects stage_done / artifact_exists
- Surface: homunculus / LLM
- Prompt says tape-only denylist; `pack_conductor_context` injects operational metadata
- Likelihood: L3 | Severity: S2
- Evidence: `docs/prompts/homunculus/conductor/system.txt` vs packer
- Fix-cluster: `llm-packet-denylist`
- Status: OPEN_RISK

### SYN-MODE-01 — Partial UI “only G0+S3” lie
- Surface: GUI / mode
- Reality: overlay lifts for G-Framing, any `job.status=gate`, pickup, reuse, etc.; driver still auto-accepts framing/VO/SFX
- Evidence: StartTab / ActionOverlay copy vs `partialAcceleratedGuard` + driver
- Likelihood: L3 | Severity: S2
- Fix-cluster: `mode-gate-honesty`
- Status: OPEN_RISK

### SYN-GUI-01 — Dual-advance after gate POST
- Surface: GUI
- Panels POST then `advanceFromCheckpoint` (GapFraming, PickupSpeaker, VoiceRef, GapDelivery)
- Likelihood: L2 | Severity: S3
- Fix-cluster: `gui-dual-advance`
- Status: OPEN_RISK

### SYN-GUI-02 — Unguarded mutating panels under Partial
- Timeline optimizer remaster, Conversation Studio delete, Acoustic overrides, G-Listen skip, per-line VO synth — missing `shouldBlockOperatorActionsForJob`
- Likelihood: L2 | Severity: S3
- Fix-cluster: `partial-overlay`
- Status: OPEN_RISK

### SYN-MIX-01 — mix_epoch_block no-ops when Phase A unsealed + unstable
- Surface: cross-cut
- Forced `--from-stage mix` can run early
- Likelihood: L2 | Severity: S3
- Evidence: `delivery_guardrails.mix_epoch_block`
- Fix-cluster: `music-epoch`
- Status: OPEN_RISK

### SYN-DELIGHT-01 — Full-auto listen_delight auto-waiver
- `ensure_listen_delight_waiver_unattended` soft-seals when audit JSON exists but seed incomplete
- Likelihood: L3 | Severity: S3
- Fix-cluster: `delight-authoritative`
- Status: OPEN_RISK

### SYN-GFR-01 — Framing posture advisory ≠ sticky Yes/No
- Homunculus auto-Yes ignores posture LLM; pending+enabled=true semantic lie
- Likelihood: L3 | Severity: S2
- Fix-cluster: `g-framing-authority`
- Status: OPEN_RISK

### SYN-PREPARE-01 — Partial post-G0 preclean vs G0-locked STT
- Auto-preclean after G0 creates isolated.wav; SAP/spine prefer it; transcript stays raw-normalized
- Likelihood: L2 | Severity: S3
- Fix-cluster: `partial-prepare-order`
- Status: OPEN_RISK

### SYN-SHARED-01 — Shared artifact self-stale (brief / boundaries / SDP)
- Multi-writer paths leave hollow `.stage_done`
- Likelihood: L3 | Severity: S3
- Fix-cluster: `invalidation-blast` / `hollow-done-coverage`
- Status: OPEN_RISK

### SYN-RETRY-01 — Junction feel attempts=3; seam tier ladder ≤3
- Product law “max 2” vs outliers
- Likelihood: L2 | Severity: S2
- Fix-cluster: `llm-hard-stop-routing`
- Status: OPEN_RISK

## Agent sources (research only)
- Inventories, thrash VJ-01..24, delivery D-*, analysis early, mastering/gap, prompts F1–F12, GUI F1–F5 / top-10, model/tool map
