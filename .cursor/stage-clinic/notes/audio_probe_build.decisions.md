# Decisions — audio_probe_build

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | APB-B2 fail_open empty golden_facts: keep vs refuse? | **4B KEEP fail_open empties** (confirm) | `audio_probes.fail_open=true` → empty artifacts + heal; thin tape keep progressing |
