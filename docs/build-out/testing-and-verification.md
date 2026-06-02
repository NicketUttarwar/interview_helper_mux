# Testing and verification

How to verify each build-out wave before marking tickets **done**. Complements [smoke-test.md](../workflows/smoke-test.md) (operator greenfield checklist).

---

## Layers

| Layer | What it proves | When |
|-------|----------------|------|
| **Prerequisites** | Toolchain + imports | Every machine setup |
| **Unit / contract** | Prompt schemas, transcript review helpers | CI / pre-commit |
| **Stage integration** | One stage writes expected artifacts | Per BUILD ticket |
| **Flow integration** | Full flow1, flow2, or flow3 | Per wave |
| **Operator smoke** | GUI + CLI happy path | Release / definition of done |
| **Autonomous E2E** | `./scripts/e2e.sh` — all flows + heal + final report | Release / nightly |
| **Quality QA** | LUFS, listen tests, SFX coherence | Wave 5–6 |

---

## Prerequisites (all waves)

```bash
./scripts/bootstrap_venv.sh
source .venv/bin/activate
./tools/check_prerequisites.sh
```

**Pass:** Python 3.12.x, ffmpeg/ffprobe, aws CLI, imports smoke, `pip-audit` on `requirements.lock` with no unaccepted HIGH/CRITICAL findings.

---

## Automated tests (BUILD-054–055, #18)

```bash
pytest tests/
```

| Test file | Covers |
|-----------|--------|
| `test_prompt_validation.py` | JSON schema validation; `fixtures/prompts/stage_artifacts.json` per stage key |
| `test_transcript_review.py` | Review queue / correction merge |
| `test_gates.py` | Profile gate, G1 VO, flow selection, transcript review pending |
| `test_pipeline.py` | Flow 1/2/3 + analysis order smoke (stubbed stages, `fixtures/runs/base_smoke`) |
| `test_build073_llm_routing.py` | Arbiter + shard/collate routing |
| `test_g1_5_prompt_review.py` | ElevenLabs prompt review API (GET/PUT/approve) |
| `test_preclean_offer.py` | BUILD-072 pre-clean offer API + run_meta |
| `test_master_qc.py` | LUFS / true-peak thresholds, sample-rate checks |
| `test_verify_master_cli.py` | CLI exit codes + flow path inference |
| **Gap closure (GC-F1–GC-D1)** | |
| `test_gap_foundation.py` | `acoustic_profile`, `audio_timeline` crossfade, `operator_quality.preclean_acknowledged` |
| `test_sound_design_crossfade.py` | Assembly preview speech crossfades |
| `test_mix_acoustic_profile.py` | SAP-driven duck / stinger policy in mix |
| `test_transcript_review_schema.py` | `validate_transcript_review_queue` fail-fast |
| `test_runner_preclean_gate.py` | `record_qc_summary` merge, runner preclean gate, strict NLE |
| `test_elevenlabs_chunk_policy.py` | ElevenLabs upload byte limit contract |
| `test_elevenlabs_music.py` | Music v2 compose payload, duration clamp, prompt-influence prose |
| `test_audio_preclean.py` | Pre-clean enable/skip, vo_pickup scope, chunked isolation path |
| `test_gap_closure_smoke.py` | Smoke fixture validators + qc_summaries on fixture run dir |
| `test_source_acoustic_profile.py` | SAP stage output shape |
| `test_ingest_preclean.py` | Ingest path when preclean isolated exists |
| **Phase 6 (GC-Q1–Q13)** | |
| `test_selection_flow2_sap.py` | Flow 2 SAP in `sfx_brief` build_input |
| `test_recompute_acoustic_profile.py` | Recompute invalidates downstream on pace change |
| `test_stinger_pause_alignment.py` | Pause-aligned stinger placement |
| `test_mix_intelligibility_qc.py` | Post-mix intelligibility QC + `qc_summaries` |
| `test_llm_specialists.py` | Specialists pilot (`full_master_ranking`) |
| `test_acoustic_profile_overrides.py` | SAP GUI `operator_overrides` API |
| `test_edl_qc.py` | EDL-level QC + `validate_edl` tooling |

**Fixture:** `tests/fixtures/runs/gap_closure_smoke/` — minimal `run_meta.json`, `source_acoustic_profile.json`, valid/invalid `nle_edits.json`, invalid `review_queue.json`.

**Helpers:** `tests/run_fixtures.py` — `isolated_run_ctx`, `ctx_from_fixture`, `patch_server_ctx` (keeps pytest off repo `data/run_*`).

**Phase 6 complete:** re-run `pytest tests/ -q` once (see [gap-closure final verification](./gap-closure-agent-commands.md#final-verification-run-once-after-all-commands)).

---

## Wave 1 — Core library

| Check | Command / action |
|-------|----------------|
| Config merge | `python -c "from interview_mux.config import load_config; load_config()"` |
| Run context | Create run via CLI; verify `.stage_done` and `gui_log.jsonl` |
| Prompt load | Run one LLM stage on fixture; `understanding/stage_runs/<stage>/` exists |

---

## Wave 1.5 — GUI platform

| Check | Action |
|-------|--------|
| Server starts | `./scripts/run.sh` |
| ASSETS input picker | WAV under `ASSETS/input/` appears on home **Input audio**; start execution creates `ASSETS/executions/exec_*` — [assets-and-executions.md](../cross-cutting/assets-and-executions.md) |
| Resume | Stop server; `./scripts/run.sh`; open same run from **Previous executions**; stages + log tail intact |
| Log panel | Execute stage; refresh page; lines persist in `gui_log.jsonl` |
| Job file | Long execute shows `gui_job.json` running → done |
| G0 panel | Analysis pauses; complete review; analysis continues |
| G2 panel | Set flow; `run_meta.json` updates |
| API contract | Spot-check routes vs [api-reference.md](../workflows/api-reference.md) |

---

## Wave 2 — Shared analysis

```bash
python tools/run_analysis.py --run-id <id>
```

**Artifacts required:**

- `ingest/normalized.wav`
- `transcript/full.json`
- `segments/manifest.json`
- `understanding/gap_report.json`
- `analysis_complete.json`

**G1 path:** Leave `delivery: record` gaps unrecorded → pipeline exits with message; record `vo_pickup/*.wav`; rerun `--from-stage vo_ingest`.

**G0 path:** Pause at transcript review; fix corrections; mark complete.

---

## Wave 3a — Flow 1

```bash
# run_meta.selected_flow must be flow1
python tools/run_flow.py --flow flow1 --run-id <id>
python tools/verify_master.py <run>/flow_1_master/master.wav
```

| Criterion | v1 | Target (Wave 5–6) |
|-----------|-----|-------------------|
| File plays | Required | Required |
| Duration > 0 | Required | Required |
| Speech order matches selection | Manual listen | Required |
| VO audible in master | Not required v1 | Required (BUILD-067, 065) |
| SFX audible | Not required v1 | Required (BUILD-065) |
| LUFS −16 ±1 and true peak ≤ −1 dBTP | `verify_master.py` (non-zero exit on fail) | **done** (BUILD-070) |
| Assembly bus measured before limiter | `gui_log.jsonl` `master_flow*` lines; `pytest tests/test_mastering_bus.py` | **done** (BUILD-071) |

---

## Wave 3b — Flow 2

```bash
python tools/run_flow.py --flow flow2 --run-id <id>
python tools/verify_master.py <run>/flow_2_highlights/master.wav
```

**Pass:** ≤5 clips worth of content; montage SFX present in v1; target: shared transition asset (BUILD-065).

---

## Wave 3c — Flow 3 (shipped, BUILD-080)

```bash
python tools/run_flow.py --flow flow3 --run-id <id>
```

**Pass:**

- `flow_3_description/show_description.json` validates
- `show_description.md` exists (BUILD-046)
- Third person; ~150–250 words
- No `master.wav` under flow_3_description
- Examples: [podcast-show-description.examples.md](../prompts/_shared/examples/podcast-show-description.examples.md)

---

## Wave 5 — Sound design

| Check | Method |
|-------|--------|
| SDP valid | JSON schema validate `sound_design_plan.json` |
| Asset reuse | Multiple cues share one `asset_id`; one WAV on disk |
| No voice in SFX | Listen + [elevenlabs-prompt-regression.md](../prompts/_shared/examples/elevenlabs-prompt-regression.md) |
| Ducking | Speech intelligible over beds (manual QA) |

---

## Wave 6 — Assembly honesty + QA

| Check | Method |
|-------|--------|
| EDL has VO | Inspect `edl.json` for pickup placements |
| NLE applied | Edit in GUI; rerun ranking; selection changes |
| Preview before SFX | `assembly_preview.wav` exists; operator signed off in log |
| LUFS / true peak | `verify_master.py` fails on out-of-spec master (non-zero exit) |

---

## Wave 7 — LLM routing

| Check | Method |
|-------|--------|
| Arbiter accept | `attempt_*.json` contains `arbiter_result.verdict: accept` |
| Shard on long fixture | `shard_count` > 0 when over token budget |
| Tier respect | Stage uses matrix tier from [llm-stage-model-matrix.md](../cross-cutting/llm-stage-model-matrix.md) |

---

## Regression before PR

1. Ticket acceptance from [ticket-specs.md](./ticket-specs.md)
2. [doc-maintenance.md](./doc-maintenance.md) checklist
3. `pytest` if touching validation or review
4. Relevant smoke section from [smoke-test.md](../workflows/smoke-test.md)
5. Update [README.md](./README.md) ticket status + [repository-map.md](./repository-map.md) gap table

---

## Related

- [smoke-test.md](../workflows/smoke-test.md) — end-to-end operator checklist
- [e2e-automation.md](../workflows/e2e-automation.md) — autonomous `./scripts/e2e.sh` runner
- [troubleshooting.md](../workflows/troubleshooting.md) — failure symptoms
- [evaluation-metrics.md](../cross-cutting/evaluation-metrics.md) — master pass/fail thresholds
