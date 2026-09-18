# Decisions — air_script_seams

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | Retier contract to process/deterministic? | _(target B1)_ | draft backlog |
| 2026-09-17 | L3 | ASS-B1 retier process? | Wave 2 yes | `_PROCESS_STAGES` + dependency lifecycle execute; bootstrap YAML; pytest pin; gap_framing_plan write confirmed IN_CODE |
| 2026-09-17 | L3 | ASS-B2 enable=false mark/skip honesty? | skipped | FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 | ASS-B3 soft-freeze no-op vs required reseat? | skipped | needs_you + FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 | ASS-B2 CONTINUE: enable=false skip-done (CSP-01) | Wave 2 yes (operator override FARR skip) | same `persist_air_script_disabled_skip` + heal; ASS-B3 still needs_you |
| 2026-09-17 | L3 | ASS-B3 soft-freeze no-op vs required reseat? (1B) | KEEP cautious soft-freeze | no product patch; ASC-B3 does not force reseat; Pass B freeze no-op remains IN_CODE |
| 2026-09-18 | L3 | ASS-B3 soft-freeze confirm? | **7A KEEP** | no forced reseat; freeze still blocks order cascades when active |
| 2026-09-18 | L3 | Operator north star: Full-auto decides; strictest rails; error-free master alone | **reaffirm 7A** — soft-freeze no-op ≠ human gate | Freeze is an auto guardrail (protect seats). Forced reseat (7B) thrashs VO/EDL and fights error-free unattended. Meta-gate / End-A allowlist / catastrophe unlocks remain the deterministic rewrite path when needed. |
