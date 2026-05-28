# Repository map

How **docs**, **code**, **config**, **tools**, and **operator media** fit together.

**Build-out:** [implementation-guide.md](./implementation-guide.md) · [full-application-flow.md](./full-application-flow.md) · [stage-registry.md](./stage-registry.md) · [ticket-specs.md](./ticket-specs.md) · tickets: [README.md](./README.md) · backlog: [steps-forward.md](./steps-forward.md).

---

## Top-level layout

| Path | Role | Build-out / docs |
|------|------|------------------|
| `AGENTS.md` | Agent read order, gates, constraints | BUILD-000 |
| `README.md` | Repo entry, links to setup and docs | BUILD-000 |
| `SETUP.md` | Bootstrap, secrets, first run | BUILD-000 |
| `ASSETS/` | Operator media (gitignored): `input/`, `executions/`, `.gui/` — [assets-and-executions.md](../cross-cutting/assets-and-executions.md) | [capture](../pipeline/capture/README.md) |
| `config/` | `app.defaults.json`, `secrets/secrets.env` | BUILD-011 · [config-keys](../cross-cutting/config-keys.md) |
| `docs/` | Authoritative specs and prompts | Waves 0–6 |
| `src/interview_mux/` | Python package | Waves 1–5, 7 |
| `tools/` | CLI wrappers (`run_analysis`, `run_flow`, checks) | BUILD-028, 051–052 |
| `scripts/` | `bootstrap_venv.sh`, `run.sh` | BUILD-010 |
| `tests/` | pytest (prompt validation, transcript review, shell) | BUILD-054–055 |
| `.cursor/rules/` | IDE policy (logging, Context7) | — |

**Not in v1:** SQLite / `mux_store`, boto3, preset ladder A–E (see `AGENTS.md`).

---

## Python package (`src/interview_mux/`)

| Module | Responsibility | Ticket |
|--------|----------------|--------|
| `cli.py` | Typer CLI: `analysis`, `flow`, `serve`, default pipeline | BUILD-028, 051 |
| `config.py` | Merge defaults + secrets; model IDs | BUILD-011 |
| `run_context.py` | Run workspace paths, `.stage_done`, `ctx.log()` | BUILD-012 |
| `file_store.py` | Locked JSON read/write | BUILD-012 |
| `session_log.py` | `gui_log.jsonl` append/read | BUILD-016 |
| `gui_session.py` | Active run / server session under `ASSETS/.gui` | BUILD-014 |
| `gates.py` | G0/G1/G2 checks, `selected_flow`, profile gate before Flow 1 extended | BUILD-017, 081 |
| `pipeline.py` | Stage orders, `run_analysis`, `run_flow1/2` | BUILD-028, 035–036, 043–044 |
| `analysis_orchestrator.py` | Investigation queue drain after LLM stages | BUILD-018 |
| `analysis_memory.py` | `analysis_state.json`, profile, queue | BUILD-018 |
| `context_volley.py` | LLM message volleys per stage | BUILD-013 |
| `prompt_validation.py` | JSON schema validation for stage outputs | BUILD-001 |
| `elevenlabs_rest.py` | REST SFX (no SDK) | BUILD-034, 042 |
| `nle_state.py` | `segments/nle_edits.json` | BUILD-068 (ranking + EDL) |

### Stages (`src/interview_mux/stages/`)

| Module | Stage id(s) | Ticket |
|--------|-------------|--------|
| `ingest.py` | `ingest` | BUILD-020 |
| `transcribe_aws.py` | `transcribe` | BUILD-021 |
| `transcript_review.py` | `transcript_review_build`, `transcript_review` | BUILD-018 |
| `understanding.py` | `speaker_roles`, `content_context` | BUILD-022 |
| `segmentation.py` | `boundary_detection`, `segment_classification` | BUILD-023–024 |
| `gaps.py` | `missing_framing`, `optimal_questions`, `vo_ingest` | BUILD-025–027 |
| `llm_runner.py` | OpenAI calls (`task_kind`, tier meta) | BUILD-013, 073 |
| `analysis_stage.py` | Shared LLM stage runner + arbiter | BUILD-013, 073 |
| `model_registry.py` | Tier → API ID resolution | BUILD-073 |
| `llm_arbiter.py` | Post-primary verdict | BUILD-073 |
| `llm_subtasks.py` | Shard/collate decompose | BUILD-073 |
| `analysis_flow1_extended.py` | `topic_coverage_audit`, `narrative_arc_plan` | BUILD-029–030 |
| `selection_flow1.py` | ranking, transitions, sfx brief | BUILD-031–033, 068 |
| `selection_flow2.py` | highlights, sfx brief | BUILD-040–041 |
| `sfx_elevenlabs.py` | `elevenlabs_sfx_flow1/2` | BUILD-034, 042 |
| `sound_design.py` | `mix_flow1`, `mix_flow2` | BUILD-065 |
| `assembly_flow1.py` | `edl_flow1`, `mux_flow1` → `mix_flow1` | BUILD-035, 065, 067, 068 |
| `assembly_flow2.py` | `mux_flow2` → `mix_flow2` | BUILD-043, 065 |
| `mastering.py` | `master_flow1`, `master_flow2` | BUILD-036, 050 |
| `audio_preclean.py` | ElevenLabs isolation (optional) | BUILD-019 |
| `publishing_flow3.py` | `podcast_show_description`, `export_show_description` | BUILD-045–046 |
| `sound_design_stages.py` | `sound_design_palettes`, `sound_design_plan_flow1/2`, `elevenlabs_prompt_craft` | BUILD-061–064 |

### Web GUI (`src/interview_mux/web/`)

| Module | Responsibility | Ticket |
|--------|----------------|--------|
| `server.py` | FastAPI `/api/*` | BUILD-014 |
| `runner.py` | Background execute → `gui_job.json` | BUILD-015 |
| `stages.py` | Stage metadata for UI | BUILD-014 |
| `static/` | `index.html`, `app.js`, `styles.css` | BUILD-014 |

**GUI ↔ docs:** [gui-surface-map.md](../workflows/gui-surface-map.md) · [api-reference.md](../workflows/api-reference.md)

---

## Tools and scripts

| Entry | Invokes | Ticket |
|-------|---------|--------|
| `scripts/bootstrap_venv.sh` | venv + `pip install -r requirements.lock` + editable package | BUILD-010 |
| `scripts/run.sh` | Web GUI (`python -m interview_mux serve`) | BUILD-014 |
| `tools/check_prerequisites.sh` | ffmpeg, ffprobe, aws, import smoke, `pip-audit` on `requirements.lock` | BUILD-010 |
| `tools/run_analysis.py` | Shared analysis | BUILD-028 |
| `tools/run_flow.py` | Flow 1, 2, or 3 after G2 | BUILD-051 |
| `tools/verify_master.py` | LUFS + true-peak QA on `master.wav` | BUILD-052, BUILD-070 |
| `src/interview_mux/master_qc.py` | Measurement + threshold checks (shared by CLI and GUI) | BUILD-070 |
| `src/interview_mux/mastering_bus.py` | pyloudnorm assembly-bus LUFS before limiter | BUILD-071 |

---

## Documentation tree (by concern)

| Folder | Purpose |
|--------|---------|
| `docs/pipeline/` | Per-stage I/O, one README per stage |
| `docs/prompts/` | LLM system prompts + examples |
| `docs/cross-cutting/` | Artifacts, schemas, toolchain, quality roadmaps |
| `docs/workflows/` | Gates, GUI, smoke test, troubleshooting |
| `docs/roadmap/` | Future-proofing guardrails |
| `docs/pipeline/value-analysis/` | Optional R&D spikes (not default product path) |
| `docs/build-out/` | Full build-out suite: [implementation-guide](./implementation-guide.md), [stage-registry](./stage-registry.md), [ticket-specs](./ticket-specs.md), tickets, repo map, steps forward |

**Hub:** [INDEX.md](../INDEX.md) · **Pipeline overview:** [pipeline.md](../pipeline.md)

---

## Config and schemas

| Path | Purpose |
|------|---------|
| `config/app.defaults.json` | Paths, model routing, web port |
| `config/secrets/secrets.env` | API keys (gitignored) |
| `docs/cross-cutting/json-schemas/` | Validation contracts |
| `docs/prompts/**/*.system.txt` | Authoritative LLM copy |

---

## Known doc ↔ code gaps (track in [steps-forward.md](./steps-forward.md))

| Topic | Docs say | Code today |
|-------|----------|------------|
| ASSETS-first input | GUI asset list + executions under `ASSETS/executions/`; resume via `GET /api/session` + `PUT /api/session/active` | **Shipped** — GUI + `RunContext` exec_* ids; CLI `--run-id exec_*` opens existing execution; headless fallback still uses `input_audio_path` / `INPUT_AUDIO_PATH` |
| Full podcast mix | VO + SFX in `master.wav` | **Shipped (BUILD-065–066)** — `mix_flow1`/`mix_flow2` canonical in `pipeline.py` + GUI; `mux_flow*` legacy single-stage alias |
| Smart LLM routing | `model_registry`, `llm_arbiter`, `llm_subtasks` | done (BUILD-073) |
| Pre-clean offers | Multiple checkpoints | **done** — BUILD-019 stage + BUILD-072 GUI checkpoints |

When you close a gap, update this table and the ticket status in [README.md](./README.md).
