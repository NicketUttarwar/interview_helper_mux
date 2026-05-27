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

**Pass:** Python 3.12.x, ffmpeg/ffprobe, aws CLI, imports smoke, pip-audit clean (when BUILD-010 complete).

---

## Automated tests (BUILD-054–055, expand in #18)

```bash
pytest tests/
```

| Test file | Covers |
|-----------|--------|
| `test_prompt_validation.py` | JSON schema validation for stage outputs |
| `test_transcript_review.py` | Review queue / correction merge |

**Planned (steps-forward #18):**

- Gate helpers (`check_g1_vo`, transcript review pending)
- Pipeline smoke with fixture run directory (no live AWS/OpenAI)
- Schema fixture per stage key

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
| LUFS −16 ± tolerance | Not enforced | BUILD-070 |

---

## Wave 3b — Flow 2

```bash
python tools/run_flow.py --flow flow2 --run-id <id>
python tools/verify_master.py <run>/flow_2_highlights/master.wav
```

**Pass:** ≤5 clips worth of content; montage SFX present in v1; target: shared transition asset (BUILD-065).

---

## Wave 3c — Flow 3 (when BUILD-080 ships)

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
| LUFS | `verify_master.py` fails on out-of-spec master |

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
