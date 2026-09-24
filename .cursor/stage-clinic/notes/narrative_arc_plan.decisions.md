# Decisions — narrative_arc_plan

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | L1: contract hard vs brief; QC ownership hitch? | _(awaiting)_ | draft target backlog |
| 2026-09-17 | L3 | NAP-B1 align contract hard with checker (coverage+brief)? | Wave 2 yes | hard = coverage_audit + content_brief; soft no longer lists brief |
| 2026-09-17 | L2/L3 | NAP-B2 QC writer SSOT hitch vs narrative? | Wave 2 skip — needs_you | open |
| 2026-09-18 | L3 | NAP-B2 / CCH-B2 ownership? | **6C** leave dual; document | no ownership rewrite |
| 2026-09-22 | L3 | NAP-B2 overturned — live plan mint SSOT? | **yes** NAP owns live plan; hitch QC + `hitch_chapter_authority` only; anti-spoof | never forge stage_key=narrative_arc_plan from hitch |
| 2026-09-22 | L3 | Adaptive ladder R0–R7 (synthesize on LLM fail)? | **yes** | never empty chapters; never soft-pre-flush allowlist |
