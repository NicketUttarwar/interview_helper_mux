# Smoke test

End-to-end validation checklist for a new machine.

**Release candidate:** Run `pytest tests/` plus this checklist for manual sign-off before calling the repo done.

## Prerequisites

Install from the **anchor lock** (exact pins in repo-root `requirements.lock`; doc mirror: [anchored-requirements.lock](../cross-cutting/anchored-requirements.lock)). Policy: [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md).

```bash
./scripts/bootstrap_venv.sh   # venv + pip install -r requirements.lock
source .venv/bin/activate
./tools/check_prerequisites.sh # ffmpeg, ffprobe, Python 3.12.x, pip-audit on lock, import smoke
```

**Fail fast:** If `pip-audit` reports HIGH/CRITICAL CVEs against the lock, refresh the lock or record an accepted advisory in [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md#accepted-advisories) before continuing.

**Before a long delivery run:**

1. `python tools/progression_chain_sanity.py --scope full` (progression regression)
2. `./scripts/build_gui.sh` if `frontend/src` changed
3. ASSETS venvs for audio tail (DeepFilterNet, MMAudio) when running past `edl`
4. GUI **delivery readiness** banner clear on `topic_coverage_audit` (`GET …/delivery-readiness`)

See [flow1-progression-matrix.md](../cross-cutting/flow1-progression-matrix.md) for stage/checkpoint map.

**Pre-audio (SFX / mix):** require `master/assembly_preview.wav` before `mmaudio_sfx`; SDP cues before `mix`. `GET …/delivery-readiness?scope=pre_audio` lists blockers.

## Config

- `config/secrets/secrets.env` has `OPENAI_API_KEY` (the only required credential — STT, diarization, S2S, denoise, and SFX all run locally)
- At least one `.wav` under `ASSETS/` (recommended: `ASSETS/input/interview.wav`)

## GUI path (preferred)

1. `./scripts/run.sh`
2. Home → pick a file under **Input audio** (or resume **Previous executions**)
3. Note `run_id` (e.g. `exec_001_a1b2c3d4e5f6_20260523T120000Z`) from the workspace header — includes a 12-char source-audio hash segment

**Resume check:** stop the server, run `./scripts/run.sh` again — the GUI should open the **Start** tab (session cleared by default). Pick source audio or resume a prior run from **Executions**. Use `MUX_PRESERVE_SESSION=1 ./scripts/run.sh` to keep the last active pointer across that launch. Stage markers and `gui_log.jsonl` remain under `ASSETS/executions/<run_id>/`.

**Steps sidebar:** expand a pipeline step to see its gate substeps. Completed steps collapse with a **Step complete** banner; click a todo substep to jump to the matching panel.

**Refresh check:** with an active run, refresh the browser — same run, Pipeline tab, stage focus, and log tail should return without clicking Resume.

**Fresh launch:** `./scripts/run.sh` clears ephemeral ASSETS state by default (session pointer, `.gui/sessions/*`, stale locks inside exec_*); resume manually from **Executions → Resume**. Use `MUX_PRESERVE_SESSION=1` to keep the pointer across a launch. Directories under `ASSETS/executions/` are never auto-deleted.

**Reuse check (optional):** start a second execution on the same WAV; confirm **Same audio** on Executions tab; at a pending stage, confirm **Previous execution reuse** offers the first run when that stage completed.

See [assets-and-executions.md](../cross-cutting/assets-and-executions.md).

## Artifact validation (optional)

```bash
pytest tests/test_artifact_completeness.py tests/test_prompt_validation.py -q
python tools/codegen_zod_schemas.py
cd frontend && npm run build
```

After analysis stages, GUI **Stage outputs** should show **complete** for `understanding/content_brief.json` and related JSON (not stuck on **partial**). Spec: [artifact-generation-and-validation.md](../cross-cutting/artifact-generation-and-validation.md).

## Analysis (CLI)

```bash
python tools/run_analysis.py --run-id exec_001_a1b2c3d4e5f6_20260523T120000Z
```

Use the `run_id` from the GUI step above. For headless-only setups, `INPUT_AUDIO_PATH` in `secrets.env` remains a fallback — not required when the run was created via the GUI asset picker.

**Optional spot-check:** `understanding/stage_runs/<stage>/attempt_001.json` records the call. Each stage gets at most **2** attempts via `llm_simple.py`, then hard-stops — there is no shard/collate/arbiter fallback.

Expect under `ASSETS/executions/exec_001_…/` (legacy: `data/run_001/`):

- `ingest/normalized.wav`
- `transcript/full.json`
- `transcript/review_queue.json` with `sort_mode: salience` after G0 prep (Wave A)
- `understanding/value_features.json` optional `quality_trajectory_flags` after `content_context` auto-extract
- `segments/manifest.json`
- `understanding/gap_report.json`
- `analysis_complete.json`

If G1 triggers, record VO to `vo_pickup/` and re-run with `--from-stage vo_ingest`.


**Narrative excellence soft-gate:** After palettes / before gap framing, research + Shape stages write `mastering/research_dossier.json` and `mastering/mastering_plan.json` (`pass` provisional→confirmed). Listen delight audit after `assembly_preview` is **advisory only**. Human listen rubric: [NORTH_STAR.md](../../NORTH_STAR.md). Prefer/forbid: `docs/cross-cutting/narrative-mode-prefer-forbid.json`.

**Gap framing path (recommended Yes):** After `source_topology_build` / before gap LLM stages, choose Yes/No in GUI (required). Yes → confirm least-spoken pickup speaker → approve voice reference → **grant clone consent with scopes** (cold open / bridges / outro) if Chatterbox is chosen → choose Chatterbox or record → `gap_framing_compose` → G1 synthesize/record. Unattended/E2E: set `analysis.gap_fill.auto_accept_defaults` or `INTERVIEW_MUX_AUTO_ACCEPT_GATES=1` (or use `tools/e2e_pipeline_driver.py`, which accepts the same defaults). Chatterbox verify in `./scripts/verify_local_models.sh` is **WARN** when venv missing (mlx-audio fallback). Audit: `vo_pickup/synthesis_report.json`. Consent audit: `mastering/voice_clone_audit.json`.

**Optional at G1:** If pickup recordings are noisy, accept VO-scoped pre-clean offer (BUILD-072) before continuing.

## Delivery

There is one delivery path. Flow 2 / Flow 3 and the G2 flow picker were removed; `--flow` is accepted and ignored.

```bash
python tools/run_delivery.py --run-id exec_001_a1b2c3d4e5f6_20260523T120000Z
python tools/validate_narrative.py --run-id exec_001_a1b2c3d4e5f6_20260523T120000Z --include-edl
python tools/verify_master.py ASSETS/executions/exec_001_a1b2c3d4e5f6_20260523T120000Z/master/master.wav
```

**Expectations:** Playable `master.wav`. `verify_master.py` enforces integrated LUFS −16 ±1, true peak ≤ −1 dBTP, sample rate 44100 or 48000, duration > 0. Exits non-zero on failure. `validate_narrative.py --include-edl` covers upstream narrative, EDL timeline, and EDL narrative QC; run `verify_edl.py` if you need schema-only diagnostics. Listen-test VO + SFX audibility before sign-off.

## MMAudio SFX path (optional)

After delivery reaches polish with sound design enabled:

1. `sfx_prompt_craft` → approve prompts (G1.5 if `g1_5_require_prompt_approval`).
2. `mmaudio_sfx` → `sound_design/assets/*.wav`, `sound_design/mmaudio_qa.json`.
3. GUI post-listen pass/fail; optional refine (`POST /sfx-prompts/refine`) and per-asset regenerate.
4. When `sound_design.post_listen_gate_mode` is `block`, confirm mix is blocked after a deliberate listen fail (`Mix gate: post_listen_gate_mode=block` in log).
5. When `mix.intelligibility_qc.enabled`, confirm `QcSummaryCard` shows `mix_intelligibility` on mix/master stages after `mix`.
6. `mix` → `master_finalize`; listen master under speech.

See [mmaudio-prompt-tuning.md](../cross-cutting/mmaudio-prompt-tuning.md).

## Mastering quality hardening (advisory)

Canon: [mastering-quality-hardening.md](../cross-cutting/mastering-quality-hardening.md). Gates ship `advisory` (fail-open) under `mastering.quality_hardening.*`.

When the Shape Engine / Realization runtime is wired:

1. Confirm L0 emits `mastering/shape/eval_rubric.json` beside the agenda.
2. After L2: `diversity_report.json` — near-clones reminted or flagged.
3. Before L4: `feasibility.json` allow-list and `semantic_integrity.json` clean of critical findings.
4. Auditions: `mastering/auditions/{candidate_id}/manifest.json` for up to `max_auditions` survivors (render optional in advisory mode).
5. L4: `cross_critique.json` with ≥6 critic reports merged by the L4 panel arbiter in `mastering_critics.py`; survivors feed `pareto.json`.
6. Clone path: granting `vo_clone_*` without consent fails feasibility / voice gate; guest clone always rejected.

The `research_routing` and `polish` gates are inert — their config keys remain but `mastering_research_router.py` and `mastering_polish_loop.py` were removed, so no `routing.json`, `polish_audit.json`, or `prompt_promotions.json` is written.

CI coverage (no network): `pytest tests/test_mastering_quality_*.py`.

## Pass criteria

- No unhandled exceptions
- Master WAV plays; duration > 0
- `verify_master.py` exits 0 for `master/master.wav`
- Before trusting E2E delivery: `./scripts/verify_local_models.sh` then
  `STRICT_LOCAL_SMOKE=1 python tools/smoke_local_runtimes.py --generate`
  (Chatterbox, S2S, MMAudio, CLAP, DeepFilter golden WAVs under `ASSETS/smoke/local_runtimes/`)
- Autopsy recent masters: `python tools/audit_execution_breakages.py --limit 25`

## Coherence (H-ORC-03, optional)

For interviews ≥ 30 minutes:

```bash
.venv/bin/pytest tests/test_coherence_*.py -q
curl -s "$BASE/api/runs/$RUN_ID/coherence-report" | jq '.gate,.summary'
```

The Stage panel should show **Coherence risks** when `gate.activated` is true.

## If something fails

Use [troubleshooting.md](./troubleshooting.md) and [operator-stage-checklists.md](./operator-stage-checklists.md) to narrow the stage, then [feedback-loops-and-reruns.md](./feedback-loops-and-reruns.md) for `--from-stage` commands.
