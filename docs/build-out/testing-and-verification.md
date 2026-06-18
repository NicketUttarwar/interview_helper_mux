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

## June 2026 Wave 0 — Resilience harness

After [02-WAVE-0-resilience-harness.md](./june182026build/02-WAVE-0-resilience-harness.md) code changes; gate before Wave A.

```bash
source .venv/bin/activate
./tools/check_prerequisites.sh
pytest tests/test_stage_parity.py tests/test_artifact_cross_validate.py \
  tests/test_interview_spine_clap.py tests/test_preclean_offer.py tests/test_gates.py -q
pytest tests/test_sonic_context.py tests/test_coherence_duration_gate.py \
  tests/test_coherence_fixture_planted.py tests/test_wave0_resilience.py -q
python tools/audit_stage_plans_doc.py
```

| Check | Command / action |
|-------|------------------|
| Fail-open paths | `pytest tests/test_wave0_resilience.py -q` |
| CLAP fail-open | `pytest tests/test_interview_spine_clap.py -q` |
| Coherence 30m gate | `pytest tests/test_coherence_duration_gate.py tests/test_coherence_fixture_planted.py -q` |
| Scenario fixtures | `pytest tests/test_sonic_context.py tests/test_sound_design_scenario.py -q` |
| Volley parity | `python tools/audit_stage_plans_doc.py` (exit 0) |
| BUILD-072 preclean | `pytest tests/test_preclean_offer.py tests/test_audio_preclean.py -q` |
| Gates G0–G2 + profile | `pytest tests/test_gates.py -q` |
| Cross-artifact | `pytest tests/test_artifact_cross_validate.py tests/test_sdp_cross_validate.py -q` |

Promotion gate: [§15 in 02-WAVE-0](./june182026build/02-WAVE-0-resilience-harness.md#15-promotion-gate-for-wave-a).

---

## June 2026 Wave A — Early truth

After [03-WAVE-A-early-truth.md](./june182026build/03-WAVE-A-early-truth.md) code changes; gate before Wave B.

```bash
source .venv/bin/activate
pytest tests/test_wave_a_early_truth.py tests/test_sonic_context.py tests/test_mix_acoustic_profile.py tests/test_style_inference.py -q
python tools/run_value_spike.py --fixture tests/fixtures/value_analysis/spike_shared_ingest_transcribe.json
python tools/run_value_spike.py --fixture tests/fixtures/value_analysis/spike_shared_g0_and_profile.json
python tools/run_value_spike.py --fixture tests/fixtures/value_analysis/spike_shared_gaps_and_vo.json
```

| Check | Command / action |
|-------|------------------|
| H-ING-03 trust dips | `pytest tests/test_wave_a_early_truth.py -k trust -q` |
| G0 salience + stress | `pytest tests/test_wave_a_early_truth.py -k review -q` |
| H-GAP-01 specialist fail-open | `pytest tests/test_wave_a_early_truth.py -k specialist -q` |
| Scenario fixtures | `pytest tests/test_sonic_context.py tests/test_mix_acoustic_profile.py tests/test_style_inference.py -q` |
| Spike baselines | `run_value_spike.py` on three shared fixtures (≥ 3.738 / 4.037) |

Promotion gate: [Wave B gate in 03-WAVE-A](./june182026build/03-WAVE-A-early-truth.md#wave-b-promotion-gate).

---

## June 2026 Wave D — Output resilience

After [06-WAVE-D-output-resilience.md](./june182026build/06-WAVE-D-output-resilience.md) code changes; gate before step **07** finish sign-off.

```bash
source .venv/bin/activate
pytest tests/test_wave_d_output_resilience.py tests/test_stage_enrichment.py \
  tests/test_stinger_pause_alignment.py tests/test_placement_qa.py \
  tests/test_mix_acoustic_profile.py tests/test_flow2_crossfade.py -q
python tools/verify_master.py --help
python tools/validate_narrative.py --help
python tools/audit_stage_plans_doc.py
```

| Check | Command / action |
|-------|------------------|
| H-F1N-02 emphasis | `pytest tests/test_wave_d_output_resilience.py -k emphasis -q` |
| H-F2-02 quotability | `pytest tests/test_wave_d_output_resilience.py -k quotability -q` |
| H-F1S-02 placement / laughter | `pytest tests/test_stinger_pause_alignment.py tests/test_placement_qa.py -q` |
| Scenario fixtures | `pytest tests/test_sonic_context.py tests/test_sound_design_scenario.py -q` |
| Recovery drills D-W36–40 | `pytest tests/test_wave_d_output_resilience.py -k recovery -q` |
| Volley parity | `python tools/audit_stage_plans_doc.py` (exit 0) |

Promotion gate: [§13 in 06-WAVE-D](./june182026build/06-WAVE-D-output-resilience.md#13-wave-d-promotion-gate-for-shipped-default-on) — **Partial** shipped; no default-on until nine-scenario listen + §13.

---

## June 2026 step 07 — Finish sign-off

After [07-FINISH-signoff.md](./june182026build/07-FINISH-signoff.md); closes sequential build **01–07**.

```bash
source .venv/bin/activate
pytest tests/ -q
python tools/audit_stage_plans_doc.py
./tools/check_prerequisites.sh
python -c "
import sys; sys.path.insert(0, 'src')
from interview_mux.pipeline import ANALYSIS_ORDER, FLOW1_ORDER, FLOW2_ORDER, FLOW3_ORDER
from interview_mux.web.stages import EXECUTABLE_ORDER
for name, pipe in [('analysis', ANALYSIS_ORDER), ('flow1', FLOW1_ORDER), ('flow2', FLOW2_ORDER), ('flow3', FLOW3_ORDER)]:
    assert list(pipe) == list(EXECUTABLE_ORDER[name])
print('parity OK')
"
```

| Check | Command / action |
|-------|------------------|
| Cross-wave pytest | `pytest tests/ -q` (exit 0) |
| Volley parity | `python tools/audit_stage_plans_doc.py` |
| Toolchain | `./tools/check_prerequisites.sh` |
| Index links | [INDEX.md](../INDEX.md), [AGENTS.md](../../AGENTS.md) → `june182026build/00-INDEX.md` |
| Manual release | [definition-of-done-signoff.md](./definition-of-done-signoff.md) §1–6 on real `exec_*` |

**Operator manual follow-up:** nine-scenario listen matrix, G2×3 flows on fixture, master listen — not automated; see [07-FINISH-signoff.md § Operator manual follow-up](./june182026build/07-FINISH-signoff.md#operator-manual-follow-up-after-code-complete).

---

## Automated tests (BUILD-054–055, #18)

```bash
pytest tests/
python tools/codegen_zod_schemas.py   # after json-schemas/ edits
cd frontend && npm run build          # Zod validators must compile
```

| Test file | Covers |
|-----------|--------|
| `test_prompt_validation.py` | JSON schema validation; `fixtures/prompts/stage_artifacts.json` per stage key |
| `test_artifact_completeness.py` | Gap-fill merge, `artifact_status`, `write_validated_artifact`, `should_run_stage_for_artifact` |
| `test_transcript_review.py` | Review queue / correction merge |
| `test_gates.py` | Profile gate, G1 VO, flow selection, transcript review pending |
| `test_pipeline.py` | Flow 1/2/3 + analysis order smoke (stubbed stages, `fixtures/runs/base_smoke`) |
| `test_build073_llm_routing.py` | Arbiter + shard/collate routing |
| `test_g1_5_prompt_review.py` | MMAudio SFX prompt review API (GET/PUT/approve) |
| `test_preclean_offer.py` | BUILD-072 pre-clean offer API + run_meta |
| `test_source_audio_hash.py` | Pipeline WAV SHA-256, hash in run id parsing |
| `test_run_context_hash_id.py` | `allocate_run_id(source_hash=…)`, `run_meta` hash fields |
| `test_write_staging.py` | `.pending_writes/` staging, approve/discard, operational path bypass |
| `test_stage_execution_reuse.py` | Reuse candidates, hash match, copy-through-staging |
| `test_stage_guidance_parity.py` | GUI guidance vs `stage_guidance.py` |
| `test_master_qc.py` | LUFS / true-peak thresholds, sample-rate checks |
| `test_verify_master_cli.py` | CLI exit codes + flow path inference |
| **Gap closure (GC-F1–GC-D1)** | |
| `test_gap_foundation.py` | `acoustic_profile`, `audio_timeline` crossfade, `operator_quality.preclean_acknowledged` |
| `test_sound_design_crossfade.py` | Assembly preview speech crossfades |
| `test_mix_acoustic_profile.py` | SAP-driven duck / stinger policy in mix |
| `test_transcript_review_schema.py` | `validate_transcript_review_queue` fail-fast |
| `test_runner_preclean_gate.py` | `record_qc_summary` merge, runner preclean gate, strict NLE |
| `test_mmaudio_runner.py` | MMAudio runner / local generation contract |
| `test_mmaudio_runner.py` | Music v2 compose payload, duration clamp, prompt-influence prose |
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
| `test_edl_narrative_qc.py` | Final EDL narrative semantics + strict `edl_narrative_qc` gate |

**Fixture:** `tests/fixtures/runs/gap_closure_smoke/` — minimal `run_meta.json`, `source_acoustic_profile.json`, valid/invalid `nle_edits.json`, invalid `review_queue.json`.

**Helpers:** `tests/run_fixtures.py` — `isolated_run_ctx`, `ctx_from_fixture`, `patch_server_ctx`, `patch_executions_root`, `seed_analysis_complete`, `minimal_manifest`, `minimal_narrative_plan`, `minimal_gap_report`, `minimal_flow2_selection`, `minimal_content_brief` (keeps pytest off repo `data/run_*`).

**Stage parity:** `test_stage_parity.py` — stage ↔ GUI order parity + `STAGE_TEST_COVERAGE` registry.

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

**G0 path:** Pause at transcript review; fix corrections in synced dock (word edit + fuzzy batch replace) or chunk textarea; verify `words[].corrected` and `PATCH …/transcript/words`; mark complete.

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
| No voice in SFX | Listen + [sfx-prompt-regression.md](../prompts/_shared/examples/sfx-prompt-regression.md) |
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
- [troubleshooting.md](../workflows/troubleshooting.md) — failure symptoms
- [evaluation-metrics.md](../cross-cutting/evaluation-metrics.md) — master pass/fail thresholds
