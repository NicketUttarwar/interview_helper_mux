# First-try reliability

Canonical operator/agent model for **cold-start success**: new WAV → minimal human stops → batch Review/Save → `master.wav`.

See also: [operator-gates.md](./operator-gates.md), [full-autopilot-operator-model.md](./full-autopilot-operator-model.md), [delivery-quality-preservation-matrix.md](../cross-cutting/delivery-quality-preservation-matrix.md).

## Flag

`journey_ui.first_try_mode` (default **true**). Set `false` to restore per-stage write pauses and strict full G0/G1 human review without confidence/severity shortcuts.

Helper: `interview_mux.first_try`.

## Locked rules

| Topic | Behavior |
|-------|----------|
| Write approval | **Never silent auto-approve.** Mid-phase Save may be **deferred**; operator still clicks **batch Save**. |
| G0 | Auto-complete when review queue has zero `needs_review` chunks |
| G0.5 | Auto-complete when empty |
| G1 | Only `severity` in `high`/`critical` (or `blocking: true`) require VO WAV |
| Profile | Auto-verify when ready and no critical investigations |
| Pickup speaker | Auto-confirm when one eligible speaker |
| G1.5 prompts | Auto-approve when prompt completeness QA is green |
| Preclean | Never auto-accept; auto-dismiss when source readiness green; **unset offer does not block ingest** — optional pre-clean stays on its own stage until you open it |
| SFX / mix | Placeholder SFX warn; missing blocking VO / empty speech hard-fail |
| Handoff | Disabled under first_try (same as full_autopilot) |
| Stage reuse | Offers may list inline on each stage; **non-blocking** under first_try (run fresh without a separate acknowledgement gate) |

## Still human

- Low-confidence G0 chunks (`needs_review`)
- High/critical `delivery: record` VO lines
- TBIY post-preview pickup when those lines exist
- Explicit batch Save at phase end(s)
- Residual Stage Decision Wizard items ITR cannot auto-resolve

## Phase batch Save

With `journey_ui.defer_write_approval_until: "phase_end"`:

1. Stages write under `.pending_writes/<stage>/`
2. Pipeline does **not** pause every stage for Approve
3. Operator uses **Save all pending** (`gui.write_approval.batch_save` / `POST …/pending-writes/approve-batch`)
4. Phases: `analysis` (through `delivery_brief_build`) and `delivery` (through `master_finalize`)

## Source readiness

`understanding/source_readiness.json` — `green` \| `yellow` \| `red`. Drives preclean offer recommendation (never auto DeepFilter accept).
