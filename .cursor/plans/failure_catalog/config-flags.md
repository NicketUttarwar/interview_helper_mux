# Config / env flags inventory (no secret values)

Keys that change behavior. **Never read `config/secrets/secrets.env` values.**

## Process env

| Key | Behavior change |
|-----|-----------------|
| `MUX_RUN_MODE` | manual / full-auto / partially-accelerated |
| `MUX_FULL_AUTO` / `MUX_BABA_E2E` | Launch automation driver as full-auto |
| `MUX_PARTIAL_AUTO` | Launch as partial |
| `MUX_FRESH` / `MUX_RUN_ID` | New vs continue execution folder |
| `MUX_INPUT_AUDIO` | Input path |
| `MUX_HOMUNCULUS_VERSION` | Brain slider (default latest 0.1.0) |
| `INTERVIEW_MUX_AUTO_ACCEPT_GATES` | Gate auto-accept |
| `INTERVIEW_MUX_E2E_SOFT` | Gate soft progress |
| `INTERVIEW_MUX_E2E_QUALITY_WAIVERS` | Quality waivers |
| `MUX_FORENSICS` | Identical-halt suppress (legacy) |
| `MUX_KEEPALIVE` | Driver process restart on crash |
| `MUX_E2E_SOFT_LISTENABILITY` | Soft listenability (sound_design) |

## run_meta fields (behavioral)

| Field | Role |
|-------|------|
| `run_mode` / `full_auto` / `partial_auto` | Mode detection |
| `homunculus_version` | Locked brain for run |
| `e2e_quality_waivers` | Quality waiver opt-in |
| `e2e_soft_junction_residuals` / `e2e_soft_listen_delight` / `e2e_soft_*` | Softened quality paths — footgun if set without waivers intent |
| `needs_operator` / `needs_operator_reason` | Operator halt |
| `g_publish_cleared` / gate stamps | Publish consent |
| `delivery_epoch` / locked | Structural invalidation lock |

## merged_config hotspots (key names only)

- `v2.auto_commit_artifacts`, `v2.g1_optional`
- `analysis.gap_fill.auto_accept_defaults`, `min_synthetic_vo_lines`
- `sound_design.g_listen_mode` (warn vs block)
- `mastering.timeline_optimizer.*`
- `mastering.aspirational_quality.enabled`
- `listen_delight.mode` (authoritative vs soft)
- Podcast / AWS destination keys (values from secrets — presence only)

### CFG-01 — Soft junction residuals without quality waivers

- Surface: config
- Modes: Full-auto primarily
- Why weak: meta flags `e2e_soft_junction_residuals` can green soft seams if set while product docs say gate-only soft
- Likelihood: L2 · Severity: S2 · Status: OPEN_RISK
- Fix-cluster: `e2e-soft-split-honesty`
- Evidence: `e2e_soft.py` docs vs `junction_snip_qa.py` / `assembly.py` meta checks
