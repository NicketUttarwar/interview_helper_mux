# GUI click-flow matrix (middle panel + Activity)

Synced with `pipelineSubTabAvailability.test.ts` and E2E rows in [flow1-gui-e2e/02-GUI-JOURNEY.md](../../CURSOR_EXECUTE/flow1-gui-e2e/02-GUI-JOURNEY.md).

## Pipeline tool row

| Sub-tab | Prerequisite | Locked UX |
|---------|--------------|-----------|
| stage | run loaded | — |
| story | `story_board_ready` | grey + tooltip + **toast on click** |
| timeline | `timeline_ready` | grey + tooltip + **toast on click** |
| profile | `profile_ready_for_review` | grey + tooltip + **toast on click** |
| files, llm_calls, volley_memory | — | — |

Navigation API: `navigatePipelineSubTab` in `AppContext` (guarded); locked clicks call `showToast(reason)`.

**Flow hardening:** [gui-flow-hardening.md](./gui-flow-hardening.md) — full feedback contract for all panels and job terminals.

## Activity stream policy

| Event | Tab behavior |
|-------|----------------|
| User picks Live / This step / All | Pin until job starts |
| Job starts | Clear pin → **Live** |
| StageActivityStrip “View in activity” | **This step** |
| Error from expected-empty panel fetch | No `appendClientLog` |
| Activity **All** | No pinned errors block; consecutive dedup |

## Flow permutations

| Flow | Story lock | Timeline lock | Notes |
|------|------------|---------------|-------|
| flow_1 | until content understanding | until segment classification | Full podcast path |
| flow_2 | same flags | same flags | VO pickup / shorter build |
| flow_3 | same flags | same flags | Alternate sound design path |

Navigation API: `navigatePipelineSubTab` in `AppContext` (guarded); internal utils call `setPipelineSubTab` from context hook.
