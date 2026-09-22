# DP-LOCAL-ML-RETRY — Local ML fail must reclaim, wait 5s, retry, then escalate

- status: closed
- created: 2026-09-21T17:07:00Z
- closed: 2026-09-21T19:40:00Z
- blocks: (resolved) Shared local-ML fault order — MusicGen / Chatterbox / S2S / MMAudio / DeepFilter / STT
- resume_hook: (closed — see decision_log)
- solution_swarm_agents: 1 (file-search / HEAD audit; no product patches)

## TL;DR (read this first)
- What’s wrong (1–2 sentences): Partial Zero §0.3b wants **kill related jobs → sleep 5s → retry same class → then escalate**. HEAD has pieces (hang kill, 5s GPU *cooldown*, 30s *abort backoff*, fidelity ladders) but **no runner implements that full order**.
- What you’d notice in Partial: Metal/OOM thrash → immediate step-down or hard raise; DeepFilter/STT fail once with no reclaim; Chatterbox/S2S retry without a settle sleep; MMAudio fidelity-steps without backoff; MusicGen waits **~30s** (not 5) and often escalates model size in the same breath as reclaim.
- Why we can’t ignore it for ironclad Partial: Fault tolerance over wall-clock is campaign law; skipping reclaim burns escalations and leaves stale GPU holders.
- Agent recommendation: Option **A** — one shared reclaim→5s→same-class-retry helper, then existing ladders.
- What that recommendation gives up: Longer wall-clock on every local-ML fail; some implement cost to wire six runners + tests.

## Context (enough to decide)
- Where in the journey (phase / stage / handoff / junction): Delivery + analysis local stacks — music stems, VO synth, SFX, preclean, STT/diarization; also GPU gate entry for any `local_gpu.consumers` job.
- Cousin family name (plain English): **Local ML reclaim / settle before degrade**.
- Glossary (only if needed):
  - **Reclaim:** stop the failed subprocess and clear other stale related heavy jobs still holding unified memory / Metal.
  - **Same-class retry:** one more attempt at the *same* backend/params class before lighter models / CPU / mlx fallback.
  - **Cooldown vs abort backoff:** HEAD uses both; they are *not* §0.3b.

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Shared helper: reclaim → fixed 5s → same-class retry → then today’s ladders | Ironclad Partial fault order everywhere | Implement/test cost across six runners |
| B | Retune existing knobs only (`abort_backoff_sec=5`, call `wait_abort_backoff` before retries) | Cheap partial alignment | Still no “related jobs” reclaim; still mixes escalate with reclaim |
| C | Per-runner ad-hoc `sleep(5)` + one retry; leave ladders as-is | Fast local patches | Divergent cousins; easy to miss STT/DF |
| Defer | Wait for live Partial fail evidence | Avoid premature churn | Partial ships with known thrash path |

## Option A — Shared §0.3b reclaim helper (recommended)
**What we would do** (plain steps, then code pointers).
1. Add one helper (e.g. on `heavy_task_policy` / `hang_escalation`) that: kills the hung Popen tree (reuse `kill_process_tree`), best-effort clears other stale related heavy workers still holding the GPU class, `time.sleep(5)` (fixed; configable but default 5), returns “ok to same-class retry once.”
2. Wire **before** fidelity / CPU / mlx ladders in: `musicgen_runner`, `mmaudio_runner` (+ `stages/sfx_mmaudio` legacy path), `chatterbox_runner` / `s2s_runner`, `deepfilter_runner`, `stt_runner` (speech), and any other `run_runtime_script` consumers that fail closed today.
3. Keep existing escalate ladders **after** that single reclaim retry.
4. Tests: unit for order; runner fakes that assert sleep(5) and no ladder until after retry.

**Pros:** Matches doctrine literally; closes cousin family at the root; Partial certainty high.
**Cons:** Broadest change surface; wall-clock cost on every fail.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High — law becomes code |
| Cousin closure | Closes reclaim-vs-degrade cousins across stacks |
| Complexity left | Low after helper lands; ladders stay runner-specific |
| What you give up | Speed; some “already degraded” paths get one extra attempt |
| Human work | Verdict + review of related-job kill scope |
| Implement cost | Medium–high (six surfaces + tests) |
| Regression risk | Medium (must not double-sleep with cooldown) |
| Reversibility | High if helper is feature-flagged |

**Cousin closure if chosen:** Local-ML fail cousins stop inventing per-stack settle policy.
**Tests we would add (HEAD-accurate):** Extend `tests/test_heavy_task_policy.py`; add order tests per runner with monkeypatched sleep/kill; assert MusicGen/MMAudio do not step fidelity until after reclaim retry.

## Option B — Align knobs to 5s; sprinkle `wait_abort_backoff`
**What we would do**
1. Change `local_gpu.abort_backoff_sec` default **30 → 5** in `config/app.defaults.json`.
2. Call `wait_abort_backoff` on MMAudio hang/kill before next fidelity rung; on Chatterbox/S2S transient retry; optionally DeepFilter/STT single retry.
3. Document that `gpu_exclusive` cooldown (already 5s) is inter-consumer settle, not fail reclaim.

**Pros:** Small diff; reuses `record_heavy_abort` / state file.
**Cons:** Backoff is “remainder since last kill,” not a fixed post-reclaim 5s; **no kill of related jobs**; MusicGen still fidelity-escalates in the same loop; DeepFilter/STT may still lack same-class retry.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium-low — looks like 5s but isn’t §0.3b |
| Cousin closure | Partial — duration aligned, order still wrong |
| Complexity left | High — related-job reclaim still open |
| What you give up | Doctrine honesty; may sleep 0 if abort state expired |
| Human work | Low |
| Implement cost | Low |
| Regression risk | Low–medium (shorter settle after real aborts) |
| Reversibility | Easy config revert |

**Cousin closure if chosen:** Weak — duration cousins only.
**Tests we would add (HEAD-accurate):** Update `test_abort_backoff_sec_default` for 5.0; add callsite coverage where backoff is newly invoked.

## Option C — Per-runner sleep(5) + one retry
**What we would do**
1. In each runner’s fail path: kill own proc if still alive, `time.sleep(5)`, retry once same args, else today’s escalate/raise.
2. No shared helper; no machine-wide related-job sweep.

**Pros:** Easy to reason per file; incremental.
**Cons:** Six divergent implementations; “related jobs” skipped; easy to miss speech/DeepFilter; double-sleep with `gpu_exclusive` cooldown.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium |
| Cousin closure | Poor — cousins reopen per runner |
| Complexity left | High drift risk |
| What you give up | Maintainability; consistent kill scope |
| Human work | Repeated reviews |
| Implement cost | Medium (scattered) |
| Regression risk | Medium (inconsistent) |
| Reversibility | Per-file reverts |

**Cousin closure if chosen:** Does not close family.
**Tests we would add (HEAD-accurate):** One test per patched runner (easy to skip one).

## Option Defer — Wait for live Partial fail tape
**What we would do:** Leave HEAD as-is until a Partial Mohan run shows thrash; then reopen this DP with live fingerprints.

**Pros:** No implement risk now.
**Cons:** Campaign law already knows this gap; thrash on first Partial is expensive.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low |
| Cousin closure | None |
| Complexity left | Unchanged (large) |
| What you give up | Preemptive ironclad |
| Human work | Watch live runs |
| Implement cost | Zero now |
| Regression risk | Zero now |
| Reversibility | N/A |

**Cousin closure if chosen:** None.
**Tests we would add (HEAD-accurate):** None until reopened.

## Recommendation (not a decision)
- Preferred: Option **A**
- Why this is best for **error-free Partial**: Doctrine §0.3b is explicit; HEAD’s 5s cooldown and 30s abort backoff are *adjacent* mechanisms, not the law. Only a shared reclaim→fixed-5s→same-class-retry gate stops every cousin from “fail fast to degrade.”
- Honest downside: Wall-clock and a careful definition of “related jobs” (avoid killing unrelated GUI/server processes).
- Devil’s-advocate note: Option B might be enough if live thrash is rare and cooldown already settles Metal — but that optimizes for speed/complexity, which Partial Zero forbids prioritizing.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | High on 16GB Apple Silicon when escalate-without-reclaim |
| Thrash tax | High — Metal abort → CPU ladder / mlx fallback hours |
| Cousin surface area | Six runners + GPU gate |
| Benefit under Partial | Host honesty + fewer false escalations |
| Replaceability | Cannot replace with “just longer timeouts” |

## Evidence appendix
- HEAD code + live behavior (**SSOT / evidence**):
  - **Doctrine:** `.cursor/plans/partial_zero/agent_swarm_protocol.md` § Local ML fault order; plan `~/.cursor/plans/partial_zero_protocol_dcd491c4.plan.md` §0.3b.
  - **5s cooldown (wrong phase):** `config/app.defaults.json` `local_gpu.cooldown_sec: 5` + `gpu_exclusive.py` sleeps in `finally` after *any* exit — inter-consumer settle, not fail→retry.
  - **30s abort backoff (wrong duration / conditional):** `heavy_task_policy.abort_backoff_sec()` default 30; `wait_abort_backoff` sleeps *remainder* only if `.heavy_abort_state.json` has recent kill. Called from `gpu_exclusive` before lock acquire and from `musicgen_runner` between ladder steps on heavy kill.
  - **MusicGen:** hang → `proc_h.kill()` (`musicgen_runner._spawn_musicgen`); `record_heavy_abort`; ladder + optional CPU retry; `wait_abort_backoff` then next *lighter* model — reclaim mixed with escalate; not fixed 5s same-class retry.
  - **MMAudio:** hang/kill → `next_fidelity_rung` immediately (`mmaudio_runner.generate_text_to_audio`); `HeavyTaskKilled.retry_after_backoff = True` but **no caller** invokes `wait_abort_backoff` on that flag. Legacy `stages/sfx_mmaudio._generate_with_retry` retries once with **no sleep**.
  - **Chatterbox:** 2 attempts same voice-ref, **no sleep**; timeout → mlx/s2s step-down (`chatterbox_runner.synthesize_line`).
  - **S2S:** up to 3 Chatterbox attempts on transient markers, **no sleep**; then mlx fallback (`s2s_runner._synthesize_line_render`).
  - **DeepFilter:** single `run_runtime_script`; nonzero → raise (`deepfilter_runner`) — **no retry**.
  - **Local speech / STT:** single `run_runtime_script("speech", …)`; nonzero → raise (`stt_runner.transcribe_audio`) — **no retry**.
  - **Kill scope:** `hang_escalation.kill_process_tree` kills the hung Popen only; no machine-wide “related jobs” reclaim beyond GPU serialize preventing overlap.
  - **Tests encode 30s default:** `tests/test_heavy_task_policy.py::test_abort_backoff_sec_default`.
- Docs / clinic / plans (**hints only** — verify or drop): Partial Zero README law #3; protocol §0.3b (verified against HEAD above).
- Mohan HINT only: (none collected this packet).
- Solution-swarm raw notes: `solution_swarm/DP-LOCAL-ML-RETRY/` (not written; audit lived in analysis note).

## Your verdict
- choice: **A**
- notes: shared `reclaim_for_same_class_retry` → fixed 5s → same-class once → existing ladders; six runners wired
- date: 2026-09-21T19:05:00Z
- implemented: 2026-09-21T19:40:00Z

## YOUR NEXT ACTIONS
Closed. Paste PROGRESS_NOW from STEP_OFF.md for the next open DP.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=LOCAL-ML-RETRY
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
