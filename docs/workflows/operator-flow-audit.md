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

**Chrome:** Live status bar, action modal, API consent, confirm dialog, activity teaser (non-Pipeline tabs).

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
| 4 | Status banner unused | `WorkflowStepBar` is canonical command surface (no separate banner) |
| 5 | Listen silent no-op | Inline `<audio>` fallback + toast |
| 6 | Mic errors swallowed | Toast on `getUserMedia` failure |
| 7 | Disabled Continue unclear | Per-gate hints in modal |
| 8 | Reuse accept felt stalled | Auto `runNextStage` after accept |
| 9 | flow_intent vs G2 confusing | **Use planned choice** at G2 |
| 10–20 | Medium/low polish | Reuse config flag, value-features API, QC hints, Pipeline resume, 409 handling, docs — see [gui-surface-map.md](./gui-surface-map.md) |
| 21 | Resume / refresh silent failures | `openRun` error toasts, `sessionReady` gate, stale job reconcile, UI chrome in `active_execution.json` |
| 22 | Half-loaded session stuck | Start/Pipeline **Retry load** + **Clear session** recovery panels |
| 23 | Status "Complete" misleading | Job → **Step finished**; phase → **Record & choose**; stage → **Done** |
| 24 | Stale job during poll | Merge `GET /job` into `run.job` each tick; batch `stage_index/total` in `gui_job.json` |
| 25 | `interrupted` shown as Idle | LiveStatusBar **Run interrupted** branch |
| 26 | Logs only in footer | Pipeline **ActivityLogPanel** (Live / This step / All) + **ActivityTeaser** on other tabs |
| 27 | Duplicate Run/checkpoint CTAs | Single primary CTA in **LiveStatusBar**; command center read-only |
| 28 | Sidebar ≠ running stage | Auto-select `job.stage` unless operator pinned sidebar (30s) |
| 29 | MMAudio post-listen silent no-op | Inline audio ref + toast in **SfxPostListenPanel** / **StageAudioActions** |
| 30 | QC fail only hints redo | **QcSummaryCard** inline redo + activity log link |
| 31 | Audio quality drawer dead-end | **Open checkpoint** action in **AudioQualityDrawer** |
| 32 | Executions list opaque | Job status pill, progress bar, clickable **last_log** → Logs |
| 33 | Duplicate tab badges | Pipeline action badge removed — **LiveStatusBar** owns primary CTA badge |
| 34 | Flat sidebar hid required actions | **Substeps** under each stage in `PipelineStepList`; click opens checkpoint via `activateSubstep` |
| 35 | Done steps looked active | Collapsed gray rows + **Step complete** banner; `StageDetail` done shell |
| 36 | Running step unclear in sidebar | `StepRunningConnector` + spinner on running substep row |
| 37 | Scattered navigation logic | Single `activateSubstep` kernel; `useStageProgress` hook |
| 34 | Session UI not restored | `activity_log_tab` + `activity_log_collapsed` in `active_execution.json` |
| 35 | Timeline QC isolated | **TimelineQcChecklist** links to Pipeline activity log |
| 36 | Desktop timeline surprise | Dismissible desktop-first hint in **TimelineWorkspace** |
| 37 | LLM debug buried | **StageDetail** → Open full debug; **LlmCallsPanel** routing failures + stage filter |
| 38 | Volley table cramped | Expand chevron column + horizontal scroll hint |
| 39 | Write approval invisible mid-run | Live status bar + activity panel copy in **WriteApprovalPanel** |
| 40 | NLE apply progress unclear | **ApplyEditsPanel** + **LiveStatusBar** running state during `nle_apply` |
| 41 | Phase guidance only on Start tab | **StartPhaseGuidance** on Start tab only — no banner on Pipeline |
| 42 | Phase chips hide pending reviews | **Workflow phase** chips use `attention` state + count badge |
| 43 | Dual numbering confusing | Labels **Workflow phase** vs **Pipeline step** + tooltips; blocked mode suppresses step eyebrow |
| 44 | Generic Open Pipeline CTA | Primary button uses `journey.next_action` / **resolveNextActionClick** |
| 45 | Preview-listen gate buried | **PreviewListenPromo** in command center + compact row in LiveStatusBar |
| 46 | Scattered pending actions | **AttentionQueuePanel** ordered list; action badge opens queue when count > 1 |
| 47 | Handoff felt like rubber stamp | **HandoffPanel** skim checklist + inline-first **Review outputs** CTA |
| 48 | Sub-tab work invisible | Badges on **PipelineToolRow** from **subTabAttentionFlags** |
| 49 | Long step list hunting | **Needs you only** filter on **PipelineStepList** |
| 50 | Activity teaser opaque off-Pipeline | **ActivityTeaser** shows resolver **headline** + Go affordance |
| 51 | Executions resume opaque | Enriched list rows show phase, next/blocking hint, **Needs you** pill |
| 52 | Gate progress unclear | **gate-progress-subheader** on G0/G1/profile panels; modal hints for all pending kinds |
| 53 | Optional vs required mixed | **attention-required** / **attention-optional** styling on gates vs pre-clean |
| 54 | Step finished → what's next? | Toast + activity log line + 30s LiveStatusBar **Next:** subline after job complete |
| 55 | Checkpoint labels generic | **checkpointLabels** + **attentionQueue** shared across banners and CTAs |
| 56 | Header duplicate Save CTAs on Pipeline | **LiveStatusBar** status-only on Pipeline tab; sidebar owns Save/Run/reuse |
| 57 | Blocked substep showed spinner | **stageSubsteps** — user-action substeps stay `todo`; spinner only for execution or save-in-flight |
| 58 | Generic "Pipeline blocked" after ingest save | **attentionQueue** maps `journey.blocking.reason` (e.g. `stage_reuse`) to specific titles |
| 59 | Optional pre-clean unclear | Sidebar **Skip this optional step**; skipped rows greyed out |
| 60 | Main panel / sidebar focus mismatch | **approveWriteAndContinue** selects `findPendingFocusStage` after save |

### UX simplification wave (61–80)

| # | Issue | Fix |
|---|-------|-----|
| 61 | Duplicate CTAs across command center, status bar, sidebar, modal | **`resolveOperatorAction`** single source of truth for mode/headline/primary |
| 62 | Unclear what to do on each step | **`StepActionHeader`** at top of **`StageDetail`** with mode badge + one primary |
| 63 | Checkpoints scattered inline + modal | **Modal-first** — auto-open on `needs_you`; inline panels hidden when modal owns checkpoint |
| 64 | Modal showed guidance + gates + footer Continue | **`OperatorActionModal`** — one active panel; resolver title; footer deduped |
| 65 | Sidebar substeps looked like buttons with action labels | **`SubstepRow`** navigation-only; checkpoint clicks open modal |
| 66 | Hard to find blocked stage in long list | **`sidebar-step--focus`** + default **Needs you only** filter |
| 67 | LiveStatusBar had no primary on Pipeline | Restored primary CTA; workflow chips read-only on Pipeline tab |
| 68 | Ingest stuck after run (write approval invisible) | **`journey.active_operator_action`** + auto modal on `awaiting_write_approval` |
| 69 | E2E clicked wrong CTA | **`gate_handlers.try_primary_cta`** prefers `step-action-primary` → modal → sidebar |
| 70 | Operator model undocumented | [ux-operator-model.md](./ux-operator-model.md) + updated [gui-surface-map.md](./gui-surface-map.md) |
| 71 | Duplicate Pipeline primaries | LiveStatusBar primary hidden on Pipeline; **StepActionHeader** owns CTA |
| 72 | Pin selection invisible | Sidebar 📌 when selected ≠ focus for 30s |
| 73 | Navigation toast spam | `runNextStage` opens modal without duplicate hint toasts |
| 74 | Handoff did not auto-advance | `acknowledgeHandoff` calls `runNextStage` after refresh |
| 75 | Broken `useOperatorAction` import | Fixed path to `../utils/resolveOperatorAction` |
| 76 | E2E stuck-ingest regression | `BLOCKER-007-stuck-ingest-ux.md` + driver priority table |
| 77 | Stale operator-journey / gates docs | Updated for modal-first + StepActionHeader |
| 78 | UX smoke scripts missing | `operator-stage-checklists.md` Prepare + gates section |
| 79 | Resolver test gap | Expanded `resolveOperatorAction.test.ts` gate matrix |
| 80 | Dead command center mount | Removed `PipelineCommandCenter` from `PipelineTab` |

---

## References

- [api-reference.md](./api-reference.md) — HTTP contract
- [stage-execution-reuse.md](./stage-execution-reuse.md) — reuse eligibility
- [operator-gates.md](./operator-gates.md) — G0, G1, G2, quality offers
- [troubleshooting.md](./troubleshooting.md) — symptoms (mic, Listen, job 409)
