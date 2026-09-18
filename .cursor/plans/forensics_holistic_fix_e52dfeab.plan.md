---
name: Forensics holistic fix
overview: "Core guardrails + product bugs LANDED (2026-08-31). pytest/verify green. MUX_FRESH=1 forensics rerun is the remaining gate — not yet executed."
status: code_complete_rerun_pending
built_at: 2026-08-31
evidence_runs: exec_4628, exec_3751
todos:
  - id: music-epoch-predicate
    content: "Add music_epoch_complete() in delivery_guardrails.py; refactor mix_epoch_block (remove hollow QA bypass)"
    status: completed
  - id: wire-filter-agenda
    content: "Wire filter_delivery_candidates, agenda walk/skip, premature_cap_hard_pin to music_epoch_complete"
    status: completed
  - id: driver-safe-mix
    content: "Add _safe_mix_resume / _resolve_mix_from_stage in full_auto_driver; execute() intercept + key heal paths"
    status: completed
  - id: runtime-pipeline-parity
    content: "Tighten homunculus dispatch_stage; add mix_epoch_block to pipeline.py 0.0.0 path"
    status: completed
  - id: fix-layup-unbound
    content: "Remove inner repair_or_skip import in analysis_extended.py"
    status: completed
  - id: fix-role-tape
    content: "repair_role_tape_segment_types + driver/llm_preflight wiring + test"
    status: completed
  - id: vo-g1-harden
    content: "vo_synthesize_stability_block blocks G1 open + layup escalation; premature_cap pins layup"
    status: completed
  - id: recovery-resume-fix
    content: "resume_theme_generation / suggest_delivery_resume require music_epoch_complete before mix"
    status: completed
  - id: invalidation-bundle-restore
    content: "C1/C2 — invalidation_is_structural + maybe_restore_master_bundle (pre-existing; tests green)"
    status: completed
  - id: layup-before-vo-stability
    content: "vo_synthesize_stability_block layup/transitions/G1 (I3 partial — no separate layup_churn_block)"
    status: completed
  - id: recovery-controller-music
    content: "sdp_theme_wavs_missing → music_palette on budget_exhausted (pre-existing in recovery_controller)"
    status: completed
  - id: lazy-musicgen
    content: "referenced_musicgen_asset_ids + sfx_mmaudio filter (pre-existing); partial unmark on resume not added"
    status: cancelled
  - id: ship-before-master-guard
    content: "filter_delivery_candidates defers SHIP_AFTER_MASTER without master.wav (I6)"
    status: completed
  - id: seed-order-ranking-chain
    content: "G1 seed_stage_complete on delivery chain — covered by existing guardrails + homunculus tests"
    status: completed
  - id: secondary-validations
    content: "Existing tests pass (gap framing, ranking, mmaudio stale, CTA, exec_3751 replay)"
    status: completed
  - id: launch-fresh-protocol
    content: "Manual I9 protocol in rerun section — no daemon code change"
    status: cancelled
  - id: job-api-truth
    content: "Clear stale last_error; reconcile stages_done (I10/I11) — deferred"
    status: cancelled
  - id: driver-heal-audit
    content: "Central execute() mix intercept; skip_stale_mmaudio uses music_epoch_complete; speaker-role heal"
    status: completed
  - id: observability-wasted-work
    content: "record_wasted_work music_deferred events; D2 epoch stamps — pre-existing + extended"
    status: completed
  - id: tests-rerun-gate
    content: "pytest + verify_artifact_contract green — MUX_FRESH=1 Mohan rerun NOT YET RUN"
    status: pending
isProject: false
---

# Forensic run holistic fix plan

**Evidence:** exec_4628 + exec_3751 on `mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3` (homunculus 0.1.0, MUX_FORENSICS=1). Companion: [forensic_run_improvement_001_4d011d87.plan.md](forensic_run_improvement_001_4d011d87.plan.md).

---

## Build status (2026-08-31)

| Layer | Status |
|-------|--------|
| **Wave 0** — `music_epoch_complete`, mix epoch, schedule/dispatch/commit | **Built** |
| **Wave 1** — layup UnboundLocalError, speaker role/tape repair | **Built** |
| **Wave 2** — VO/G1 stability + premature-cap pins | **Built** (G1 in stability block; hollow VO `mark_done` in runtime not separately hardened) |
| **Wave 3b** — I1/I2/C1/C2, I3, I4, I6 | **Built or pre-existing** |
| **Wave 3b** — I5 partial unmark, I7/I8 explicit tests | **Deferred** (lazy slot filter pre-exists; no per-slot unmark) |
| **Wave 3b** — I9 daemon, I10/I11 job API | **Deferred** (manual launch protocol only) |
| **Wave 4** — wasted_work, epoch, reconcile | **Pre-existing + music_deferred logging** |
| **Wave 5** — driver mix audit | **Built** (central `execute()` intercept + key heals) |
| **Verification** | **270 passed** in `verify_artifact_contract.sh`; `audit_config_keys` OK |
| **Forensics rerun** | **Pending** — operator must run MUX_FRESH=1 Mohan tape |

**Verdict:** Plan is **code-complete for rerun** (minimal + full path). Not **operationally complete** until `master/master.wav` on a fresh forensics run.

### Key files changed

- [src/interview_mux/delivery_guardrails.py](src/interview_mux/delivery_guardrails.py) — `music_epoch_complete`, `safe_mix_resume_stage`, tightened `mix_epoch_block`, filter, `premature_cap_hard_pin`, `vo_synthesize_stability_block`
- [src/interview_mux/delivery_recovery.py](src/interview_mux/delivery_recovery.py) — `resume_theme_generation`, `suggest_delivery_resume`
- [src/interview_mux/homunculus/agenda.py](src/interview_mux/homunculus/agenda.py) — walk filter, music skip
- [src/interview_mux/homunculus/runtime.py](src/interview_mux/homunculus/runtime.py) — music skip + dispatch guards
- [src/interview_mux/pipeline.py](src/interview_mux/pipeline.py) — mix epoch + music skip
- [src/interview_mux/speaker_role_evidence.py](src/interview_mux/speaker_role_evidence.py) — `repair_role_tape_segment_types`
- [src/interview_mux/stages/analysis_extended.py](src/interview_mux/stages/analysis_extended.py) — layup import fix
- [src/interview_mux/llm_preflight.py](src/interview_mux/llm_preflight.py) — role-tape repair attempt
- [tools/full_auto_driver.py](tools/full_auto_driver.py) — `_resolve_mix_from_stage`, `execute()` intercept, heals

### Tests added/updated

- `test_hollow_mmaudio_qa_does_not_complete_music_epoch`
- `test_repair_role_tape_segment_types_clears_dense_conflicts`
- `test_delivery_walks_to_master_when_wav_missing` — expects no hollow walk when mix deferred

---

## Execution notes → plan coverage

| Your note | Status |
|-----------|--------|
| Shared `music_epoch_complete`; prevent mix scheduling, not heal-by-crash | **Built** |
| Layup UnboundLocalError + speaker role/tape | **Built** |
| VO pin loops hardened | **Built** (stability block + premature-cap) |
| Premature-complete + walk-to-master mix scheduling | **Built** |
| Invalidation / lazy MusicGen / ops | **Partial** — see deferred below |

**Success (still to prove on tape):** `master/master.wav`; no `premature_complete:mix` loop; `wasted_work.json` shows `music_deferred` not orphan MusicGen.

---

## Core diagnosis

**Before:** premature-complete and `delivery_walk_to_master` scheduled `mix` → guards rewound music → MusicGen reran → driver tried `mix` again.

**Now:** `music_epoch_complete` defers mix at **schedule** time via `filter_delivery_candidates`, `execute()` intercept, homunculus dispatch, and `safe_mix_resume_stage`.

---

## Wave 0 — Music epoch ✅

- `music_epoch_complete(ctx)` — G5 + all `MUSIC_BEFORE_MIX` `seed_stage_complete` + SDP WAV parity; no hollow QA bypass.
- `mix_epoch_block` — uses predicate; stamps `music_complete_at` only when true.
- `filter_delivery_candidates` — defers mix/junction/finalize/ship; ship requires `master.wav`.
- `safe_mix_resume_stage` / driver `_resolve_mix_from_stage` + `execute()` redirect.
- Agenda walk filtered; music skip only when epoch complete.
- Runtime + pipeline parity.

---

## Wave 1 — Product bugs ✅

- Layup inner import removed (`analysis_extended.py`).
- `repair_role_tape_segment_types` + driver heal + preflight attempt + test.

---

## Wave 2 — VO G1 hardening ✅ (partial runtime commit)

- `vo_synthesize_stability_block`: G1 open, layup escalation, layup/transitions stale.
- `premature_cap_hard_pin`: mix → music; vo + G1 → layup.
- **Not done:** explicit `runtime.mark_done` G1 check; `web/runner` “Finished” downgrade test.

---

## Wave 3 — Secondary validations ✅ (existing tests)

Covered by existing pytest: gap framing, hard-keep, stale SDP, CTA, exec_3751 replay, transitions survive layup heal.

---

## Wave 3b — Exec hiccups

| ID | Status |
|----|--------|
| I1 Invalidation blast radius | **Pre-existing** `invalidation_is_structural` + tests |
| I2 Bundle restore | **Pre-existing** `maybe_restore_master_bundle` + test |
| I3 Layup before VO | **Built** via `vo_synthesize_stability_block` |
| I4 Recovery controller dead-end | **Pre-existing** `music_palette_compose` on `budget_exhausted` |
| I5 Lazy MusicGen partial unmark | **Deferred** — `referenced_musicgen_asset_ids` + lazy test exist; resume still unmarks all music stages when WAVs missing |
| I6 Ship before master | **Built** in `filter_delivery_candidates` |
| I7/I8 Ranking seed-order | **Covered** by G1 guardrails (no new dedicated test) |
| I9 MUX_FRESH launch | **Manual protocol** — no daemon code change |
| I10/I11 Job API truth | **Deferred** |

---

## Wave 4 — Observability ✅ (mostly pre-existing)

- `record_wasted_work` with `music_deferred` events on filter defer.
- `delivery_epoch` stamps, checkpoint, reconcile batch — pre-existing.

---

## Wave 5 — Driver heal audit ✅

- Central `execute()` mix → `_resolve_mix_from_stage`.
- `skip_stale_mmaudio` uses `music_epoch_complete`.
- Speaker-role heal calls `repair_role_tape_segment_types`.
- Not every literal `from_stage=mix` grep site replaced — intercept covers `execute()` path.

---

## Deferred (post-rerun or optional)

| Item | Notes |
|------|-------|
| I5 per-slot unmark on `resume_theme_generation` | Lazy generation exists; unmark discipline not tightened |
| I9 daemon `fresh_pending` code hardening | Manual stop/clear before MUX_FRESH=1 |
| I10/I11 job API `last_error` / `stages_done` truth | Monitoring only |
| G10 prepare fingerprint gates | Optimization |
| ASSETS replay fixture | Predicate tests exist |
| Hollow VO `mark_done` in runtime | Wave 2 partial |

---

## Verification (completed)

```bash
.venv/bin/python -m pytest tests/test_delivery_guardrails.py \
  tests/test_delivery_recovery.py tests/test_speaker_role_evidence.py -q
# 35 passed

.venv/bin/python tools/audit_config_keys.py   # OK
./scripts/verify_artifact_contract.sh         # 270 passed
```

---

## Rerun gate (PENDING — operator)

```bash
python tools/full_auto_daemon_launch.py stop
pkill -f 'full_auto_keepalive_loop\.py' 2>/dev/null || true
pkill -f 'full_auto_driver\.py' 2>/dev/null || true
rm -f ASSETS/full_auto_current_run.txt ASSETS/full_auto_fresh_pending.json

MUX_RUN_MODE=full-auto MUX_FRESH=1 \
  MUX_FORENSICS=1 MUX_KEEPALIVE=1 \
  MUX_INPUT_AUDIO=ASSETS/input/mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3 \
  ./scripts/run.sh --full-auto --input ASSETS/input/mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3
```

Brain: leave `MUX_HOMUNCULUS_VERSION` unset (product default `latest` → **0.2.0**). Do not pin `0.1.0`.

Do **not** resume exec_4628 or exec_3751 for ship validation.

After ship: update [full_auto_forensics_state.md](full_auto_forensics_state.md) and mark `tests-rerun-gate` completed.
