# Decisions — missing_framing

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | Keep batch_fill incomplete (B2)? | Wave 2 yes | pin HG-3 refuse docstring; existing `test_hg3_*` |
| 2026-09-17 | L3 | Document AUTO_ACCEPT vs auto_accept_defaults=false (B4)? | Wave 2 yes | defaults_inventory + gap_vo_gates docstring; config-keys 0.2.0 |
| 2026-09-17 | L2/L3 | Full-auto Start arms homunculus_auto (B1)? | Wave 2 skip — needs_you | open |
| 2026-09-17 | L2/L3 | auto_skip_when_ineligible default (B3)? | Wave 2 skip — needs_you + FULL_AUTO_REGRESSION_RISK | keep false / loud fail |
| 2026-09-17 | L3 | Full-auto arms homunculus_auto (B1)? | operator CONTINUE: yes arm path | Full-auto + recommended `auto_resolve` enters `maybe_auto_accept` without features/env |
| 2026-09-17 | L3 | auto_skip_when_ineligible default (B3)? | operator CONTINUE: KEEP document (risky to flip) | default stays **false** (loud fail); documented in defaults_inventory |
| 2026-09-18 | optional revisit | Q4B auto_accept_defaults | flip default **true** | app.defaults + gap_fill_cfg fallback; monologue/topology still skip; ambiguous clone host still blocks |
