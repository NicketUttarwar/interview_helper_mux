# Execution status recordkeeper (ESR)

Per-run progress SSOT for thrash halt decisions. Artifact: `operator/execution_status.json`.

## Why

Sticky heal, forensics stall, identical_failures, and `needs_operator` historically watched stage_done / error hashes while long producers (Chatterbox, MusicGen, MMAudio, mix, junction) were still writing disk. That caused false HARD stuck.

## Progress sources

- VO: `vo_pickup/synthesized/*.wav` count + mtime
- SFX/music: `sound_design/assets` (+ `_candidates`) wav/json/gen mtime
- Mix: `master/assembly.wav`, `assembly_preview.wav`, `master.wav`
- Junction: `seam_autopsy.json`, `operator/nle_edits.json`
- Job: gui_job running + heartbeat
- Telemetry: recent `wasted_work` expensive_start / music_deferred (busy, not stuck)

**Not** progress: `e2e_soft` flags alone; hollow `.stage_done` when `stage_artifact_incompleteness` is non-empty.

## SLAs (`thrash_spine.progress_sla`)

| Stage class | Default seconds |
|---|---|
| vo_synthesize / vo_line_adjudicate | 180 |
| mmaudio / music / sfx craft | 480 |
| mix / master_finalize | 600 |
| junction_snip_qa | 360 |
| default | 300 |

## Halt policy

`wait_vs_halt(ctx)` / `may_hard_halt(ctx)` — HARD escalate only when `progress_stale=true`. Lease active or fresh disk activity → **wait**.

Shared helper is used by `full_auto_driver`, `pipeline`, `homunculus/agenda`, and `web/runner` incomplete-after-conductor paths (`should_wait_incomplete_after_conductor`).

## Post-master never-thrash-wait (ESR_POST_MASTER / DP-C1–C4)

After committed `master.wav` + honest `master_finalize` (Done Authority):

| Law | Helper |
|-----|--------|
| C1 wrong-pin never-wait | `post_master_never_wait` / `pin_in_post_master_family` |
| C2 stalled advance to ship | `stalled_expensive_can_advance` / `stalled_expensive_advance_stage` |
| C3 one wait helper | callers must use `should_wait_incomplete_after_conductor` |
| C4 ghost mtime leases | `skip_post_master_mtime_lease` (stalled/idle/error) |

Ship-bar vocabulary (`pipeline_complete`) is **C5** — separate family.

Matrix: `tests/test_esr_post_master_family.py` (`MUX_FORENSICS=0`).

## Ship-bar vocabulary (DP-C5 / SHIP_BAR_VOCAB)

**Partial DONE** = `pipeline_complete(ctx)` / `ship_bar_complete(ctx)` only:

| Predicate | Role |
|-----------|------|
| `pipeline_complete` | Local ship-bar SSOT (master + cover + mp3 + package_ready) |
| `ship_after_master_remaining` | Agenda work list after master — **not** DONE |
| ESR `should_wait` | Short-circuits when ship bar complete |
| Runner batch complete | Job slice finished — **not** episode DONE |
| G-Publish / S3 | Operator consent / remote — **never** part of ship bar |

Holes: `ship_bar_incomplete_reasons(ctx)`. Matrix: `tests/test_ship_bar_vocab.py`.

## Related

- Seat freeze: `run_meta.delivery_epoch.vo_seats_freeze` (see air-order / seat_authority)
- Epoch domains: `selection` / `framing` / `vo_seats` / `junction_residuals_generation` / `music` / `mix_input` on `delivery_epoch`
- Seed policy sticky stages: [`seed_policy.py`](../../src/interview_mux/seed_policy.py) — freeze-no-op stages are force-marked done so ESR / seed-order do not thrash
- Identical failures: class signatures include residual/epoch `generation` (`record_class_failure`)
- Timeline reopen gate log: `mastering/timeline_reopen_gate.jsonl`
