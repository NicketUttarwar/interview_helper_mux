# Decisions — selection_order_sanitize

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | L1: _(none critical)_ | _(awaiting)_ | draft target backlog |
| 2026-09-17 | L3 | SOS-B1 contract schema null vs selection schema? | Wave 2 yes | `_OUTPUT_SCHEMA_OVERRIDES` → `master_selection_artifact.schema.json`; bootstrap YAML; pytest pin |
| 2026-09-22 | L3 | Hard-keep vs depth/family; freeze restamp; integrity refuse? | Prefer keep; refuse→pin ranking; no false freeze ok stamp; integrity metrics + sanitary ranking pin (no sanitize refuse on reverse-jump) | Waves 1–4 SOS harden shipped; End-A sanitize clamp / W4 re-rank / foreign pending races remain honest residuals |
