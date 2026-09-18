# Decisions — edl_narrative_audit

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | ENA-B2 fix contract hard/consumers? | Wave 2 yes | hard=brief+coverage+narrative+selection; SDP soft; consumers=[edl]; `_SKIP_LLM_UPSTREAM_HARD` + bootstrap YAML; pin test |
| 2026-09-17 | L3 | ENA-B1 keep HE-1? | skipped | FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 | ENA-B3 invalidates vo_synthesize? | skipped | needs_you + FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-18 | L3 | ENA-B3 trim vo_synthesize invalidate? | **8B** yes | invalidates edl only |
| 2026-09-18 | L3 | ENA-B1 HE-1 heard_wav confirm? | **4A KEEP** | audit incomplete until vo_synthesize seed-complete + coverage rendered |
