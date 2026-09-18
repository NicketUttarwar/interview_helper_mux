# Decisions — master_finalize

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | Full-auto g_listen? | Full-auto auto-clear after successful remaster; Partial may keep block | → MF-B2 done |
| 2026-09-17 | L1 | aspirational vs NORTH_STAR? | | B3 needs_you |
| 2026-09-17 | L3 | MF-B1 StageInfo PMQ/delight? | Wave 2 yes | stages.py description; pytest pin |
| 2026-09-17 | L3 | MF-B2 Full-auto g_listen auto-clear? | Full-auto auto-clear after successful remaster; Partial may keep block | shared `maybe_auto_clear_g_listen_for_full_auto` in gates; wired via `require_g_listen_clear` |
| 2026-09-17 | L3 | MF-B3 aspirational vs NORTH_STAR ship? | skip | needs_you + FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 | MF-B4 drop llm_execute? | Wave 2 yes | lifecycle `execute` via dependency_data + bootstrap; pytest pin |
| 2026-09-17 | L3 CONTINUE | MF-B3 aspirational advisory vs NORTH_STAR ship? | Advisory = ship OK | aspirational advisory local `master.wav` counts as NORTH_STAR ship success for campaign bar; remote S3 still gated by advisories/G-Publish; already IN_CODE (`run_authoritative_listen_delight_at_ship` F7 1C); notes/target/inventory only |
