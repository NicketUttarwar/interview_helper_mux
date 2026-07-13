# base_smoke run fixture

Minimal run directory for pytest smokes (`test_pipeline.py`, `test_gates.py`).

| Path | Purpose |
|------|---------|
| `run_meta.json` | `REMOVED_selected_flow: flow1` |
| `understanding/analysis_state.json` | `operator_verified: true` for Flow 1 extended smokes |
| `understanding/gap_report.json` | G1 VO line for `check_g1_vo` tests |
| `transcript/review_queue.json` | Non-empty queue until `transcript_review` stage is marked done |

Copied into pytest `tmp_path` via `run_fixtures.ctx_from_fixture` — never mutated in-repo.
