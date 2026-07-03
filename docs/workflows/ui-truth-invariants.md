# UI truth invariants

Canonical rules so workflow chips, sidebar, middle-panel outputs, and operator-action resolver agree.

## Stage status vs artifacts

| Stage status | Artifact rows | Operator meaning |
|--------------|---------------|------------------|
| `pending` | missing or partial | Run or wait |
| `running` (job) | may be generating | Watch activity log |
| `awaiting_write_approval` | **staged** in `.pending_writes/<stage>/` | Review → Save to working directory |
| `done` | committed at final paths (or `n_a` / `skipped` for optional stages) | Step complete |
| `action_required` | varies (gate, reuse, consent) | Follow blocking reason |
| `locked` | n/a | Upstream incomplete |

## Artifact lifecycle phases

`artifacts_lifecycle[path]` and `outputs_view[].phase`:

- `missing` — not on disk
- `staged` — in `.pending_writes/` (not in working tree final path)
- `committed` — final path under `exec_*`
- `partial` — file exists but fails completeness check
- `n_a` / `skipped` — optional stage skipped (e.g. `audio_preclean`)

**Never** show `provider.json` / `lineage.json` as pending when `audio_preclean` is `done` + `optional_skipped`.

## Invariant codes (backend `ui_truth.validate_run_snapshot`)

| Code | Rule |
|------|------|
| T1 | `done` stage must not have `artifacts_status[path]=pending` unless lifecycle is `n_a`/`skipped` |
| T8 | `outputs_view` must not show `pending` for done stages (except staged write-approval) |
| T9 | `awaiting_write_approval` must have staged artifacts |
| T10 | `gui_job.status: complete` must not retain `awaiting_write_approval` or `pending_write_stage` |
| T11 | P0 spine stage with volley `stage_conclusion` (or `stage_summaries`) must have producer artifact `complete` or `staged` |

Run `python tools/ui_truth_smoke.py` against executions to audit.

## Write approval semantics

- Staged files: `GET …/pending-writes/{stage}/content?path=…` (`pending=1` in UI copy)
- Approve: `POST …/pending-writes/{stage}/approve` → flush to working directory + `mark_done`
- UI label: **Save to working directory** (not “complete” while staged)

## Journey phase sync

`journey.phase`, `LiveStatusBar` workflow chips, and `StepListContextHeader` derive from the same `build_journey_snapshot` fields on each `GET /api/runs/{id}`.

## Removed surfaces

- **Audio quality drawer** — removed; pre-clean only via `PrecleanOfferCard` + checkpoint modal
- `GET /api/runs/{id}/audio-quality` — removed (404)
- `journey_ui.unified_preclean_drawer` — removed from config

## Operator feedback invariants

| Invariant | Rule |
|-----------|------|
| F1 | Primary CTAs must not silently no-op when `jobRunning` or `actionBusy` — use `guardBusy` |
| F2 | Checkpoint completion must use `advanceFromCheckpoint`, not direct `runNextStage` after gates |
| F3 | Job `complete` must toast operator with `journey.next_action` or stage hint |
| F4 | `actionBusy` must reflect in sidebar substeps for write approval, profile verify, handoff |

See [gui-flow-hardening.md](./gui-flow-hardening.md).
