# Decisions — podcast_publish

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | Full-auto S3 advisory consent? | | B2 needs_you |
| 2026-09-17 | L1 | Skip vs ready:true? | | B1 unambiguous draft |
| 2026-09-17 | L1 | Revive require_g_publish_clear? | | B4 needs_you |
| 2026-09-17 | L3 | PPUB-B1 skip package_ready honesty? | Wave 2 yes | skip writes ready:false skipped; incompleteness + stage_outputs_present treat skip as present |
| 2026-09-17 | L3 | PPUB-B2 Full-auto advisory consent? | skip | needs_you + FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 | PPUB-B3 hard mp3+cover+VTT? | Wave 2 yes | dependency_data hard + bootstrap YAML |
| 2026-09-17 | L3 | PPUB-B4 require_g_publish_clear? | skip | needs_you + FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 | PPUB-B5 drop over-soft inputs? | Wave 2 yes | soft=edl+selection+narrative+meta+cover_meta only |
| 2026-09-17 | L3 | PPUB-B6 skip + advisory sync tests? | Wave 2 yes | pytest host honesty; sync mocked (no AWS) |
| 2026-09-17 | L3 CONTINUE | PPUB-B2 Full-auto advisory consent? | DONE-local / refuse-remote | local package ready; no S3 without consent; `note_remote_publish_refused`; Full-auto clears pending hang; Partial keeps must-act; never auto-consent |
| 2026-09-17 | L3 CONTINUE | PPUB-B4 require_g_publish_clear? | KEEP DEAD | confirmed unused outside `gates.py` def; notes + AST pin test; do not wire |
