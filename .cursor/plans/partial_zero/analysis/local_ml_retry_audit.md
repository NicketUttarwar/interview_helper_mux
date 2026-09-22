# Local ML retry audit — reclaim → 5s → retry → escalate

**Date:** 2026-09-21  
**Scope:** HEAD under `src/interview_mux/` — MusicGen, Chatterbox, S2S, MMAudio, DeepFilter, local speech (STT).  
**Doctrine:** Partial Zero §0.3b — on local ML fail: kill related jobs → sleep **5s** → retry same class → **then** escalate.  
**Packet:** [`../packets/DP-LOCAL-ML-RETRY.md`](../packets/DP-LOCAL-ML-RETRY.md)  
**Status:** **CLOSED** — Option A landed (`reclaim_for_same_class_retry`).

## Verdict

**Implemented.** Shared helper on `heavy_task_policy`; six runners call it before escalate ladders.

## Desired vs current (post-A)

| Step | Desired (§0.3b) | HEAD now |
|------|-----------------|----------|
| 1. Fail detected | Missing/bad output, hang, kill | Unchanged per-runner detect |
| 2. Kill related jobs | Stop failed job; GPU serialize blocks siblings | `kill_process_tree` on failed proc when passed; serialize prevents overlap |
| 3. Sleep 5s | Fixed settle after reclaim | `reclaim_settle_sec` default **5** (`local_gpu.reclaim_settle_sec` / env) |
| 4. Retry same class | One more attempt same backend/params | Once per `consumer:fingerprint` |
| 5. Escalate | Lighter models, CPU, mlx, omit | Existing ladders after reclaim returns False |

## Per-runner (post-A)

| Runner | Same-class reclaim before escalate? |
|--------|-------------------------------------|
| MusicGen | Yes — before ladder/CPU |
| MMAudio | Yes — before `next_fidelity_rung` |
| Chatterbox | Yes — between attempts + pre-escalate |
| S2S | Yes — on transient continue |
| DeepFilter | Yes — single + batch enhance |
| STT | Yes — one reclaim retry then raise |

## Tests

`tests/test_heavy_task_policy.py` — settle default 5s; fingerprint once then escalate (`MUX_FORENSICS=0`).
