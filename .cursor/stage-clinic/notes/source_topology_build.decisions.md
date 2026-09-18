# Decisions — source_topology_build

| ts | layer | question | answer | implication |
|----|-------|----------|--------|-------------|
| 2026-09-17 | L3 | STB-B1–B5 implement? | Wave 2 yes | hard speakers+transcript; no volley/llm_execute; drop optimal_questions; remove mid-seed pickup auto call |
| 2026-09-17 | L2 | STB-B6 homunculus-only pickup under defaults? | needs_you | do not flip auto_accept_defaults |
| 2026-09-18 | L3 | STB-B6 under Full-auto defaults? | **3A** framing/homunculus enough | KEEP `auto_accept_defaults=false`; no topology/env flip |
