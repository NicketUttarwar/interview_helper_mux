# Decisions — mix

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | Full-auto g_listen policy? | align with MF: Full-auto auto-clear; Partial may keep block | → MIX-B3 done |
| 2026-09-17 | L1 | VO soft / SFX hard OK? | keep VO soft / SFX hard | → MIX-B4 done (no code change) |
| 2026-09-17 | L3 | 0.2.0 should_stamp classified? | yes unambiguous DoD#3 | removed non-0.1 early return |
| 2026-09-17 | L3 | MIX-B1 align hard edl+SDP? | Wave 2 yes | hard=tape+selection+edl+SDP via dependency_data + bootstrap; drop soft+correctness edl |
| 2026-09-17 | L3 | MIX-B2 keep junction-first? | Wave 2 assert | i25 golden pin; PRESTAGE stays lenient |
| 2026-09-17 | L3 | MIX-B3 Full-auto g_listen? | align with MF-B2: Full-auto auto-clear/warn after successful remaster/mix; Partial may keep block | shared helper from mix listen_critic arm + finalize gate |
| 2026-09-17 | L3 | MIX-B4 VO soft vs SFX hard? | keep VO soft / SFX hard (no change) | operator binding; not required for B3 |
| 2026-09-17 | L3 | MIX-B5 drop llm_execute? | Wave 2 yes | lifecycle `execute` via dependency_data + bootstrap; pytest pin |
