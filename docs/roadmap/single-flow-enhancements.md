# Single-flow enhancements roadmap

After consolidating Flow 1 / Flow 2 / Flow 3 into a single **delivery** path (full podcast master), these follow-ups improve operator UX and doc parity.

## Shipped in migration

- Single `DELIVERY_ORDER` pipeline after shared analysis
- G2 flow selection removed — delivery starts when analysis + G1 + profile gates clear
- Artifact root `master/` replaces `master/`
- Stage IDs shortened (`edl`, `mix`, `mmaudio_sfx`, `master_finalize`, `sound_design_plan`)
- CLI `tools/run_delivery.py` replaces multi-flow runner

## Near-term

1. **Doc sweep** — Update `stage-registry.md`, `artifact-layout.md`, `operator-gates.md`, and GUI surface map to remove Flow 2/3 references.
2. **Schema codegen** — Regenerate Zod/JSON schemas under `master/` paths; drop `flow_2_*` and `flow_3_*` generated files.
3. **Stage contracts** — Rename YAML contracts (`sound_design_plan.yaml` → `sound_design_plan.yaml`, etc.).
4. **E2E harness** — Retarget `CURSOR_EXECUTE/flow1-gui-e2e` to delivery naming.

## Future product

- **Show notes** — Optional post-delivery text export via `show_notes_qc` (not a separate flow).
- **Highlights montage** — Reintroduce as a delivery *mode* or export preset, not a parallel pipeline.
- **Progression matrix** — Simplify readiness spine to delivery-only checkpoints.

## Non-goals

- Restoring G2 flow picker
- Parallel `REMOVED_FLOW2_ORDER` / `REMOVED_FLOW3_ORDER` execution paths
- `REMOVED_selected_flow` in `run_meta.json`
