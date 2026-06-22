# Session architecture

Single-machine, single-operator session model for `interview_helper_mux`.

## Three tiers of state

| Tier | Location | Lifetime |
|------|----------|----------|
| Application session | `ASSETS/.gui/application_state.json` + in-process mirror | `./scripts/run.sh` process (preserved across browser refresh; cleared when `MUX_FRESH_SESSION=1`) |
| Execution workspace | `ASSETS/executions/exec_<n>_<hash?>_<timestamp>/` | Durable per pipeline run |
| Client | React (`AppContext`, `runStateStore`) | Browser tab only |

## Application state schema

`application_state.json` (`schema_version: 1`) holds:

- **server** — `started_at`, `pid`, `host`, `port`, `operator_session_id`
- **active** — `run_id`, `selected_stage_id`, `active_tab`, `pipeline_sub_tab`, collapse/filter prefs, activity log prefs
- **source** — `source_locked`, `input_audio_path`
- **lineage** — `immediate_previous_run_id`, `hash_match_with_previous`, `previous_operator_session_id`

Legacy files (`active_execution.json`, `server_session.json`) are kept in sync for older tooling.

## Bootstrap (`./scripts/run.sh`)

- `MUX_FRESH_SESSION=0` (default): preserve GUI session across server restart
- `MUX_FRESH_SESSION=1`: clear `application_state.json` and legacy session files

On `interview_mux serve` start, `on_server_start()` assigns a new `operator_session_id` and writes `ASSETS/.gui/sessions/<id>/bootstrap.log`.

## API surfaces

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/session` | Full session payload: `server`, `active`, `lineage`, `run_summary`, `previous_run_summary`, `working_dir`, `log` |
| `PUT` | `/api/session/active` | Merge UI prefs (all `ActiveBody` fields round-trip) |
| `DELETE` | `/api/session/active` | Clear active session |
| `GET` | `/api/session/lineage` | Per-stage reuse eligibility vs immediate previous run |
| `GET` | `/api/runs/{id}` | Run snapshot incl. `working_dir`, `snapshot_version`, `immediate_previous_run_id` |
| `POST` | `/api/runs/{id}/reuse-from-previous` | Bulk copy eligible stages from immediate previous execution |

## Lineage and reuse

- Each new run stores `immediate_previous_run_id` in `run_meta.json` (execution_number − 1).
- Stage reuse offers scan **only** the immediate previous run when `source_audio_hash` matches.
- `POST /api/runs/{id}/reuse-from-previous` with `{ "accept_all": true }` or `{ "stage_ids": [...] }` copies outputs.

## Browser refresh

1. Fast boot: config + session + lightweight runs list; `sessionReady` stays false until `openRun` completes when restoring a run.
2. `?run=exec_NNN` deep link overrides persisted `active.run_id` on boot.
3. `SessionBanner` in `LiveStatusBar` shows run id, execution #, hash, phase, working directory.

## Frontend providers

`AppProvider` nests `SessionProvider`, `RunProvider`, and `JobProvider`; `useApp()` remains the primary facade. `runStateStore` tracks `snapshot_version` and invalidates on approve, job complete, and refresh.
