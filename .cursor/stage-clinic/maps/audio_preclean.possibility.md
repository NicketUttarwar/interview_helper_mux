# Possibility Map — audio_preclean

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index (copy from dossier when filled)

- tier: process (contract) / host+local DeepFilter orchestration — `IN_CODE`
- primary: `preclean/isolated.wav` (SSOT disk path) OR `preclean/skip.json` (skip path) — `CODE_DOC_CONFLICT` vs single primary
- gate adjacency: preclean offer / checkpoint `before_ingest` (+ later `g1_vo_pickup`) — `IN_CODE`
- LLM class: none (local DeepFilter / ffmpeg fallback)

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | No contract hard inputs; uses `ctx.input_audio()` or (rebuild) `ingest/normalized.wav` | IN_CODE | `stages/audio_preclean.py` `_selected_scope` / `run_audio_preclean` |
| hard missing | N/A (empty hard list) | IN_CODE | contract `inputs.hard: []` |
| soft missing | Soft claim `ingest/normalized.wav` often absent at first run; body reads raw input | CODE_DOC_CONFLICT | contract soft vs `ctx.input_audio()` |
| soft stale | Lineage sha skip reuse if unchanged | IN_CODE | `_can_skip_full_source` |
| hollow `{}` / `[]` | N/A for WAV primary | IN_CODE | |
| schema-valid semantic junk | N/A | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | First seed stage; source is run input | IN_CODE | ANALYSIS_ORDER[0] |
| producer invalidated | Accept path `invalidate_after_preclean_accept` clears from audio_preclean / delivery | IN_CODE | `invalidate_after_preclean_accept` |
| epoch / delivery drift | VO pickup scope can clear edl via timeline reopen gate | IN_CODE | same |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| gate open / waiting | Preclean is offer/checkpoint, not PARTIAL_MUST_ACT | IN_CODE | `partialOperatorGates.ts`; `operator_quality.OPTIONAL_PIPELINE_STAGES` |
| gate answered | accept/dismiss in `run_meta.audio_preclean.decisions` | IN_CODE | `_selected_scope` / `preclean_checkpoint_decision` |
| illegal skip | Dismiss → `ensure_preclean_skipped` writes skip.json | IN_CODE | `ensure_preclean_skipped` |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | Enhance → provider+lineage → `mark_done` | IN_CODE | `run_audio_preclean` |
| soft fail | DeepFilter unavailable → ffmpeg_local if `local_fallback_enabled` | IN_CODE | `_enhance_source_to_output` |
| hard fail | Missing source FileNotFoundError; fallback disabled raises | IN_CODE | |
| partial persist | Lineage/provider may exist without done if mark refused | IN_CODE | |
| done-without-primary | **Skip path writes `skip.json` then `heal_or_refuse_mark(force=True)` but incompleteness still requires `isolated.wav` → refuse; `is_done` stays false** while agenda `prepare_outputs_present` treats skip as present | CODE_DOC_CONFLICT | probe HEAD; `heal_or_refuse_mark` vs `agenda.PREPARE_STAGE_OUTPUTS` / HP-3 |
| retry / heal loop | Subprocess stage; thrash lists include identity | IN_CODE | `thrash_hardening` / `runner.SUBPROCESS_STAGES` |
| identical halt | Unknown stage-local identical surface | UNKNOWN | |

## 5. Side effects

- Writes (actual): `preclean/isolated.wav`, `preclean/provider.json`, `preclean/lineage.json`, `preclean/skip.json`; VO path `vo_pickup/clean/*.wav` — `IN_CODE`
- Forbidden writes risk: low (ownership ALLOW for preclean/*) — `IN_CODE`
- Invalidates: on accept, `clear_from(audio_preclean)` analysis + delivery from topic_coverage / edl for VO — `IN_CODE`
- Consumers: ingest prefers isolated; spine/SAP may prefer isolated — `IN_CODE`

## 6. Complexity traps

- OpenAI/external control vs rules: none
- Multi-heal / caps: heal refuse on skip vs prepare_outputs dual SSOT
- Dual SSOT: `STAGE_ARTIFACT_DISK_PATHS` primary isolated.wav vs skip.json completion story
- Local heavy ML: invokes DeepFilterNet (ASSETS venv); internals N/A per §3.4a

## 7. Contract honesty (declared-vs-actual)

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard inputs [] | true | IN_CODE |
| soft ingest/normalized.wav | first-run uses input_audio; normalized only for rebuild scope | CODE_DOC_CONFLICT |
| outputs isolated+provider+lineage+skip | matches writes | IN_CODE |
| invalidates [] | accept path clears downstream in code | CODE_DOC_CONFLICT |
| remediation volley_retry | not OpenAI; host rerun | CODE_DOC_CONFLICT |
| docs "Never auto-run" | defaults `auto_run_before_ingest: true` + auto-enable in `_selected_scope` | CODE_DOC_CONFLICT |

## 8. External service variance (OpenAI / cloud)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A (no external LLM) | N/A | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults happy path | `auto_run_before_ingest` true → mutates meta enabled+accept → DeepFilter/ffmpeg → done with isolated.wav | IN_CODE | `config/app.defaults.json` + `_selected_scope` |
| human stall required? | Defaults: no (auto-run). If dismiss/skip path: **done may not stamp** → seed can stall | CODE_DOC_CONFLICT | heal refuse on skip |
| GUI-only action dependency? | Defaults no; dismiss/accept UI for offer | IN_CODE | |
| auto-accept / default must fire | default_action=run / auto_run | IN_CODE | |
| partial-only fix risk | Fixing skip mark-done helps Full-auto dismiss paths too; do not require new GUI wait | FULL_AUTO_REGRESSION_RISK | |

## DoD threats (tag which §0.2 checks this stage threatens)

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions for operator

1. Should dismissed preclean complete via `skip.json` alone (HP-3 intent) even when `stage_artifact_incompleteness` still names `isolated.wav`?

## discovery_status

`complete`
