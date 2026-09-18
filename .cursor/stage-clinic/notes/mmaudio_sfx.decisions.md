# Decisions — mmaudio_sfx

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | Omit-all ship-legal? | | B2 needs_you |
| 2026-09-17 | L3 | MSFX-B1 drop llm_execute? | Wave 2 yes | lifecycle `execute` via dependency_data + bootstrap; pytest pin |
| 2026-09-17 | L3 | MSFX-B2 creative_delivery vs omit-all? | skip | needs_you + FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 | MSFX-B3 StageInfo MusicGen-first? | Wave 2 yes | stages.py title/description; pytest pin |
| 2026-09-17 | L3 CONTINUE | MSFX-B2 omit-all ship-legal? | NO — not ship-legal | `reserved_themes_all_omitted` → block mix (`assert_theme_bookends_ready_for_mix`) + fail delight (`_sonic_weave`→0); honest fail not hollow ship |
| 2026-09-17 | L3 CONTINUE | MSFX-B2 confirm omit-all fail delight/block mix? | KEEP — already landed | confirmed IN_CODE: `theme_slot_integrity.assert_theme_bookends_ready_for_mix` + `listen_delight._sonic_weave`; pytest `test_msfx_b2_*`; notes only |
