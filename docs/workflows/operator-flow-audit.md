# Operator flow audit (GUI)

Companion to [operator-journey.md](./operator-journey.md) (happy path) and [gui-surface-map.md](./gui-surface-map.md) (panels ↔ API). This doc captures **full tab/modal branching** and **UX fixes** applied after the 2026 operator flow audit.

---

## Shell (no React Router)

| Tab | Purpose |
|-----|---------|
| **Start** | Pick source WAV, optional `flow_intent`, **New execution** |
| **Executions** | Resume any `exec_*` |
| **Pipeline** | Pipeline step list + `StageDetail` (stage panel, redo, gates) + sub-tabs (Story, Timeline, Profile, Files, Debug) |
| **Logs** | Full `gui_log.jsonl` viewer |

**Chrome:** Status header, **command bar**, **execution status banner**, action modal, API consent, confirm dialog, log strip.

Checkpoint modal uses `findPendingFocusStage()` so the correct gate panel shows on **every tab**, including Logs.

---

## Journey phases

`prepare` → `understand` → `complete` → `create` → `polish` → `ship`

See [operator-journey.md](./operator-journey.md) for CTA strings and milestones.

---

## G0 — Transcript review panel

Rendered in the **operator action modal** when `transcript_review` is `action_required` (also available on stage detail for `transcribe` / `transcript_review`).

| Area | Branching |
|------|-----------|
| Chunk list | Previous / Next / dropdown; auto-advance after **Save chunk** |
| Clip audio | Per-chunk `review_clips/*.wav` player |
| Bulk edit | Textarea + **Save chunk** / **Mark reviewed (no change)** |
| Synced dock | `TranscriptDockViewer` — karaoke word flow, click seek, double-click inline edit |
| Fuzzy panel | `FuzzyReplacePopover` opens on edit; dismiss × or backdrop → **Find similar** pill reopens; strictness slider 80–100%; match rows seek + scroll transcript |
| Complete | **Complete transcript review** or **Accept remaining & complete** → unblocks `speaker_roles` |

Dock saves immediately via `PATCH …/transcript/words`. Chunk saves update `transcript/corrections.json` until complete merges into `full.json`.

---

## Key operator decisions

| Decision | Where | Commits? |
|----------|-------|----------|
| `flow_intent` | Start tab (optional) | Planning only — stored in `run_meta` |
| `selected_flow` | G2 `g2_flow_select` | Yes — `POST /api/runs/{id}/flow`; GUI **Use planned choice** applies intent in one click |
| Stage reuse | `StageReuseSection` on Stage detail + action modal | `GET …/reuse-offers` then `POST …/stages/{id}/reuse` — accept copies outputs (through write staging when enabled); decline runs fresh |
| Write approval | `WriteApprovalPanel` in action modal + Stage detail | `GET/PUT …/pending-writes/{stage}/…` then `POST …/approve` or `…/discard` |
| Source audio hash | Status header + Executions tab | `run_meta.source_audio_hash_short`; **Same audio** pill when hashes match active session |
| API consent | Modal + session grants | Required before `POST …/execute` |
| Handoff ack | After LLM custom-run writes | `POST …/handoff-ack` — uses handoff stage id, not arbitrary sidebar selection |

---

## Resolved UX issues (audit)

| ID | Issue | Resolution |
|----|-------|------------|
| 1 | Wrong/empty modal on Logs tab | Always `selectStage(findPendingFocusStage)` when modal opens |
| 2 | Clear session left server active run | `DELETE /api/session/active` + local clear |
| 3 | Profile lock hint only | CTAs: Open Story Board / Open profile; profile gate **locked** until understanding analysis completes |
| 4 | Status banner unused | Mounted in `AppShell` below command bar |
| 5 | Listen silent no-op | Inline `<audio>` fallback + toast |
| 6 | Mic errors swallowed | Toast on `getUserMedia` failure |
| 7 | Disabled Continue unclear | Per-gate hints in modal |
| 8 | Reuse accept felt stalled | Auto `runNextStage` after accept |
| 9 | flow_intent vs G2 confusing | **Use planned choice** at G2 |
| 10–20 | Medium/low polish | Reuse config flag, value-features API, QC hints, Pipeline resume, 409 handling, docs — see [gui-surface-map.md](./gui-surface-map.md) |

---

## References

- [api-reference.md](./api-reference.md) — HTTP contract
- [stage-execution-reuse.md](./stage-execution-reuse.md) — reuse eligibility
- [operator-gates.md](./operator-gates.md) — G0, G1, G2, quality offers
- [troubleshooting.md](./troubleshooting.md) — symptoms (mic, Listen, job 409)
