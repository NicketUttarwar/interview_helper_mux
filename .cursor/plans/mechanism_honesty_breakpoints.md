# Mechanism honesty — breakpoint report

**Mode:** investigation only. No product patches in this pass.  
**Date:** 2026-09-20  
**Scope:** seat/precedence/freeze · done/hollow/pin · ship/driver wait  
**Fresh execution:** not run (deferred). Evidence is current working-tree code + existing cascade tests.

**How to use this file:** each **BP-*** is a decision you own. Fill `Decision:` (`undecided` until you pick). A later patch plan should implement only the options you choose.

---

## Index (awaiting your decision)

| ID | Family | Severity | One-line | Status |
|----|--------|----------|----------|--------|
| [BP-A1](#bp-a1--junction-before-mix-gates-disagree) | Seat | thrash / ship-block cousin | Runtime lets junction run when `assembly.wav` exists; agenda/hardening follow SSOT only | **confirmed** |
| [BP-A2](#bp-a2--two-freeze-constitutions) | Freeze | ship-block vs stuck-PMQ | End-A allowlist vs ship-blocking omit vs packaging/catastrophe | **confirmed** |
| [BP-A3](#bp-a3--gap--sdp-writes-that-skip-seat-freeze) | Freeze | honesty / seat thrash | Many `gap_report` / SDP writers never call End-A | **confirmed** |
| [BP-A4](#bp-a4--seed-sticky-fail-open-on-fingerprint) | Freeze | honesty | Exception path treats any freeze `fingerprint` as hard sticky | **confirmed (exception-only)** |
| [BP-A5](#bp-a5--assert_consumer-skips-commitment-whenever-ssot-true) | Seat | honesty | Pre-mix recut skip is wider than “first mix missing” | **confirmed** |
| [BP-B1](#bp-b1--compound-token-pins-mix-ahead-of-vo_g1) | Pin | thrash | `mix_unseated` checked before `premature_class_pin` | **confirmed** |
| [BP-B2](#bp-b2--short-needle-stage-id-substring) | Pin | thrash | `"mix" in "remix…"` pins mix | **confirmed** |
| [BP-B3](#bp-b3--unknown-premature_complete-class-is-a-fake-stage) | Pin | thrash | `premature_complete:not_a_stage` returns that string | **confirmed** |
| [BP-B4](#bp-b4--mark_done-silent-authoritydenied) | Done | honesty lie | `mark_done` logs and returns; callers treat as stamped | **confirmed** |
| [BP-B5](#bp-b5--esr-clears-wait-on-bare-is_done) | Done | ship honesty | Exception / ship-pin path trusts hollow `.stage_done` | **confirmed** |
| [BP-B6](#bp-b6--two-incompleteness_resume_stage-defs) | Pin | maintenance | First def dead; substring table, no `premature_class_pin` | **confirmed (dead)** |
| [BP-C1](#bp-c1--wrong-pin-still-esr-waits-on-fresh-masterwav) | Ship | operator wait | i5 early-exit only when **that pin** is done | **confirmed** |
| [BP-C2](#bp-c2--driver-keep-join-requires-is_done) | Ship | operator wait | Stalled finalize without marker keep-joins forever | **confirmed** |
| [BP-C3](#bp-c3--driver-uses-raw-wait_vs_halt-when-master-missing) | Ship | caller split | Pipeline/agenda/runner use `should_wait`; driver does not on that path | **confirmed (narrowed)** |
| [BP-C4](#bp-c4--vo--musicgen-mtime-leases-after-job-stall) | Ship | operator wait | Wav mtime &lt;180s/120s forces lease even when job is stalled | **confirmed** |
| [BP-C5](#bp-c5--five-meanings-of-done) | Ship | honesty | ESR / runner / driver / agenda / G-Publish disagree | **confirmed (vocabulary)** |

### Hypotheses dropped or already closed in WIP (not decisions)

| Hypothesis | Verdict |
|------------|---------|
| H-A1 “SSOT unused by agenda/hardening” | **Dropped as stated.** Agenda + `llm_flow_hardening` **do** call `junction_recut_precedes_mix`. Disagreement is runtime’s **extra** assembly short-circuit (BP-A1). |
| i1 bare `premature_complete:vo_g1` → transitions | **Closed in WIP** — `tests/test_r4_premature.py` + `premature_class_pin`. Compound/substring cousins remain (BP-B1/B2). |
| i2 listen_delight ESR on vo_wavs | **Closed in WIP** — `_pin_keeps` + `test_listen_delight_pin_ignores_vo_wav_freshness`. |
| i5 pin=master_finalize done + master → no wait | **Closed in WIP** — `test_done_master_finalize_does_not_esr_wait_on_fresh_master`. Wrong-pin cousin remains (BP-C1). |
| H-C3 “driver never uses should_wait” | **Narrowed.** Driver skips `wait_vs_halt` when `master.wav` **exists** (goes to ship-heal). Split remains only when master is **missing** (BP-C3). |

---

## Family 1 — Seat / precedence / freeze

### Caller census: `junction_recut_precedes_mix`

Named SSOT: [`junction_snip_qa.py`](../../src/interview_mux/junction_snip_qa.py) `junction_recut_precedes_mix` — True if live incomplete-cut criticals **or** assembly missing **or** `mix_stale_versus_live`; False if mix done + assembly present + not live + not stale.

| Caller | Agrees with SSOT? | Extra logic |
|--------|-------------------|-------------|
| `homunculus/agenda.py:constrain_conductor_to_seed_front` | Yes | If front=`mix` and SSOT → pin `junction_snip_qa` |
| `llm_flow_hardening.py:maybe_require_upstream_llm_progress` | Yes | Bypass mix prereq only if SSOT |
| `homunculus/runtime.py:_seed_prereq_block` | **No** | If `assembly.wav` exists → **allow junction** *before* SSOT |
| `stage_input_checks.py:_check_junction_snip_qa` | Partial | Drops assembly require only when **missing** ∧ SSOT |
| `air_order.py:assert_consumer` | SSOT-gated, over-broad skip | Any SSOT True skips generation **and** commitment (BP-A5) |
| `delivery_guardrails.py:MUST_PRECEDE["junction_snip_qa"]` | Structural | Producers = `("edl",)` only — mix never required |
| `web/runner.py` | Inherits runtime | Uses `_seed_prereq_block` |

Existing tests: [`tests/test_i25_junction_recut_before_first_mix.py`](../../tests/test_i25_junction_recut_before_first_mix.py) locks live-residuals → junction first, and **clean EDL without assembly** → mix first. It does **not** fixture “assembly present + mix unmarked + no live cuts” (the remaster mid-flight split).

---

### BP-A1 — Junction-before-mix gates disagree

**What disagrees**

```125:129:src/interview_mux/homunculus/runtime.py
        if stage == "junction_snip_qa" and earliest == "mix":
            try:
                if ctx.artifact_exists("master/assembly.wav"):
                    return None
```

Comment cites exec_11130 remaster. SSOT at the same moment:

```621:622:src/interview_mux/junction_snip_qa.py
        if not live and not assembly_missing and not assembly_stale:
            return False
```

So: **fresh assembly, no live cuts, mix unmarked** (remaster unlinked `.stage_done/mix`) → runtime **allows junction**; agenda + hardening **keep mix first**. `write_staging` still runs hardening after runtime said OK → possible `SystemExit` / pin ping-pong.

**When it fires:** `junction_snip_qa` remaster unlinks mix done; re-dispatch or loud fail while previous `assembly.wav` still on disk; EDL currently clean.

**Forensics would see:** mix ⇄ junction identical-failure / seed_order_prereq on mix from hardening while runtime already dispatched junction — cousin of exec_11871, different trigger (assembly exists, not missing).

**Who is affected:** thrash; can block mix/finalize until halt.

**Tests miss:** no matrix across the five gates for “assembly present + mix unmarked + clean detect.”

**Options**

1. **Fold remaster-in-flight into SSOT** (True if mix unmarked ∧ assembly present ∧ junction is the active remaster owner) and delete the runtime short-circuit. All gates one call.
2. **Delete the short-circuit** so all gates follow today’s SSOT (mix first when clean + assembly exists). Remaster must re-mark mix or set stale explicitly.
3. **Leave as-is** — remaster can proceed from runtime; hardening may still refuse.

**Recommendation (advice):** option 1 — keep remaster legal, make every gate say the same thing.

**Decision:** A1-1 (fold remaster-in-flight into SSOT; delete runtime short-circuit)

---

### BP-A2 — Two freeze constitutions

**What disagrees**

Paper (G-4/H-3, [`cross_surface_gaps_report.md`](cross_surface_gaps_report.md)): **End-A allowlist only; otherwise freeze wins.**

Code has **three** proceed paths under freeze:

1. **End-A** — `HARD_FREEZE_ALLOWLIST_ACTIONS` in [`seat_authority.py`](../../src/interview_mux/seat_authority.py) (paperwork / orientation / strip). Used by `hard_freeze_action_permitted` → `seat_mutation_allowed`.
2. **Ship-blocking omit** — `_ship_blocking_omit_ids` in [`air_order_boundary.py`](../../src/interview_mux/air_order_boundary.py). `commit_selection_mutation` honors omit-only deltas whose reasons start `junction_snip_qa:` + `{on_a_roll, incomplete_clause, chapter_bleed_incomplete}`, or producers `edl_overlap_repair` / `segment_id_remap`. **Not** on the End-A list. Locked by i30/i37 in `tests/test_i29_junction_ladder_can_land_omit.py`.
3. **Packaging / catastrophe / one-shot** — `seat_mutation_allowed`: substring packaging (`media_ip_cta`, `cta_omit`, …) bypasses rewrite **budget**; with `require_meta_gate=False` proceeds as `packaging_budget_ok`. Catastrophe tokens (`g1_red`, `operator`, `missing_seated_wav`, `catastrophe`) proceed. `one_shot_rewrite` proceeds.

`hard_freeze_action_permitted` is only called from `seat_mutation_allowed` — selection order freeze is a **parallel** constitution in `commit_selection_mutation`.

**When it fires:** junction omit under freeze (i30); overlap-union retire (i37); CTA/sanitize under freeze; synth-fail unseat (`vo_bind_authority` uses `catastrophe_seated_bind_synth_failed` + `require_meta_gate=False`).

**Forensics would see:** either freeze restores the omitted id → mix `incomplete_cut_unresolved` forever (if you pick “allowlist only, refuse omit”), or continue today’s carve-out (if you keep 2).

**Who is affected:** audible order (omit) vs ship-block (restore) vs stuck PMQ.

**Tests:** End-A constitution tests do **not** require ship-blocking kinds to live on the allowlist. Packaging escape is untested as “must refuse.”

**Options**

1. **Permanent freeze = End-A only.** Register today’s ship-blocking omit/integrity as **named** allowlist actions (preserve i30/i37 without a second module). Delete packaging substring auto-allow; CTA either named allowlist or meta-gate always.
2. **Permanent freeze = End-A only, refuse ship-repair omits.** Mix/PMQ stay red until operator unlock. Matches “no narrow allowlist” literally; reopens exec_11871 deadlock class.
3. **Keep dual constitution** but document ship-blocking omit as the only second list; freeze packaging/catastrophe separately.

**Recommendation (advice):** option 1 — one list in `seat_authority.py`, no substring packaging, i30/i37 become named rows you explicitly keep.

**Decision:** A2-2 (End-A only; refuse ship-blocking omits; mix/PMQ stay red until unlock)

---

### BP-A3 — Gap / SDP writes that skip seat freeze

**What disagrees**

G-4: gap/selection/SDP mutation under freeze should hit End-A or refuse.

| Site | Freeze-gated? | Notes |
|------|---------------|--------|
| `timeline_optimizer/apply.py` gap promote | **Yes** | `gate_seat_mutation(..., reason="optimizer_promote_gap_report")` — **not** allowlisted → meta-gate or refuse |
| Same file **transitions** promote | **No** | writes `master/transitions.json` with no End-A |
| Same file **SDP** promote | **No** | writes `sound_design_plan.json` with no End-A |
| `commit_gap_report_doc` | **No** | sanitize persist; no `hard_freeze_action_permitted` |
| `vo_line_adjudicate` `write_json(GAP_REL)` | **No** | owner write; can run under **soft** freeze (after air_contract, before hard freeze) |
| `opening_orientation` retarget | Ownership freeze only | `write_permitted`, not seat freeze |
| `chapter_close_hitch.reattach_vo_to_gap_report` | **Yes** | `hitch_reattach_vo` — not allowlisted |
| `vo_bind_authority` synth-fail unseat | Catastrophe bypass | `require_meta_gate=False` |
| `air_script.compose_pass_b` | **Yes** | `compose_pass_b` → meta-gate under soft freeze |
| `omit_ledger` heals | Mixed | allowlisted revive vs `omit_ledger_heal_air_contract` refuse |
| `soundscape_verify` SDP patch | **No** | bed-trim write (i44 class historically) |
| `execution_contract` / `vo_contract` | Partial | some `gate_seat_mutation` |

**When it fires:** optimizer Take-best under freeze; adjudicate re-run after sanitize; remaster SDP cue patch.

**Forensics would see:** `authority_denied` **or** silent seat fingerprint drift after freeze stamp (harder to see).

**Who is affected:** seat honesty; possible WAV-demand expand (forbidden under H-3).

**Options**

1. **Every gap/selection/SDP write under freeze** must pass `hard_freeze_action_permitted` or skip-write (fail-closed). Optimizer SDP/transitions same as gap.
2. **Gate only fingerprint-changing writes** (seated/omitted/orientation ids); allow metadata/sanitize/SDP cue numbers.
3. **Leave writers as-is**; trust ownership ALLOW rows.

**Recommendation (advice):** option 2 — freeze is a **seat** constitution, not a global write ban; still close optimizer SDP/transitions and adjudicate seat-id changes.

**Decision:** A3-1 (every gap/selection/SDP persist under freeze: End-A or skip-write via `persist_frozen_seat_doc`)

---

### BP-A4 — Seed sticky fail-open on fingerprint

**What disagrees**

Happy path: `_hard_freeze_and_edl_done` = `hard_freeze_active` ∧ `is_done("edl")`.

Exception path:

```47:51:src/interview_mux/seed_policy.py
                freeze_art = bool(
                    fr.get("hard")
                    or lvl in {"hard", "hard_freeze"}
                    or fr.get("fingerprint")
                )
```

Soft freeze also stamps `fingerprint`. If `hard_freeze_active` throws, **soft + fingerprint + EDL done** sticky-completes `FREEZE_STICKY_SEED_STAGES` (framing / layup / SDP).

**When it fires:** rare — `hard_freeze_active` exception. Not the normal walk.

**Tests:** `test_seed_policy_probe_error_sticky_with_edl_and_freeze_artifact` uses `"hard": True` — does **not** prove soft-only fingerprint.

**Options**

1. Exception path requires `fr.get("hard")` or level `hard` — **never** fingerprint-alone.
2. Leave fail-open so probe errors still unstick seed (current intent of the fallback).
3. On probe error, never sticky (fail-open the other way — may rewind framing under freeze).

**Recommendation (advice):** option 1 — sticky only with hard evidence.

**Decision:** A4-1 (exception path sticky only on `hard` / level `hard` — never fingerprint-alone)

---

### BP-A5 — `assert_consumer` skips commitment whenever SSOT True

**What disagrees**

```713:724:src/interview_mux/air_order.py
    if (
        stage in {"mix", "junction_snip_qa", "master_finalize"}
        and not pre_mix_recut
        ...
    )
    if stage in {"junction_snip_qa", "master_finalize"} and not pre_mix_recut:
        verify_commitment(...)
```

`pre_mix_recut = junction_recut_precedes_mix` — True for **stale-only** or **missing-only**, not just live cuts. Junction can skip selection↔EDL commitment while a stale assembly exists.

**When it fires:** remaster / generation mismatch with SSOT True.

**Who is affected:** honesty (junction operating on uncommitted EDL).

**Options**

1. Skip generation/commitment **only** when assembly is missing (first recut); stale still asserts.
2. Keep skip whenever SSOT (current) so recut is never blocked by mix-era commitment.
3. Split: skip generation match, still require commitment.

**Recommendation (advice):** option 1.

**Decision:** A5-1 (skip generation/commitment only when assembly is missing)

---

## Family 2 — Done / hollow / pin

### Pin order (live `producer_pin_for_token`)

1. seed_order / g0 / voice_ref / high_gap / fuse / heard_wav  
2. **`mix_unseated` / `mix_outputs_seated` → `mix`**  
3. music_incomplete / hitch / selection_commit / gap_unsanitary / vo_audibility  
4. **`premature_class_pin`**  
5. exact then **substring** `PRODUCER_PIN_TABLE` (every `DELIVERY_ORDER` id auto-inserted, including `"mix"`)

`heal_pin_for` already consults `premature_class_pin`. Callers of `incompleteness_resume_stage` all use the **second** def `(ctx, consumer_stage)`.

---

### BP-B1 — Compound token pins mix ahead of vo_g1

**What disagrees:** `'mix_unseated and premature_complete:vo_g1'` returns **`mix`** because mix_unseated is checked first. Bare `premature_complete:vo_g1` correctly pins VO (i1 WIP).

**When it fires:** blended error strings (driver/heal concatenates incompleteness).

**Forensics would see:** heal to mix while G1 still open — premature_complete:vo_g1 cousin of exec_13165 i1.

**Tests miss:** no compound-token case in `test_r4_premature.py`.

**Options**

1. Named `premature_complete:<class>` **always first** among symptom needles.
2. Longest / most-specific token wins (score classes).
3. Leave mix_unseated first (mix seating is “more fatal”).

**Recommendation (advice):** option 1.

**Decision:** B1-2 (longest / most-specific structured token wins)

---

### BP-B2 — Short-needle stage-id substring

**What disagrees:** `for needle, pin in PRODUCER_PIN_TABLE.items(): if needle and needle in key` — `"mix" in "remix bed failed"` → mix. First insertion-order hit wins.

**When it fires:** any prose containing a short stage id as a substring (`mix`, `edl`, `sfx`).

**Options**

1. Word-boundary / min length (e.g. ≥ 8) / longest-match-first; never bare 3-letter ids.
2. Exact token / `artifact_missing:<stage>` only; drop auto stage-id needles.
3. Leave substring table (simple, false positives accepted).

**Recommendation (advice):** option 1.

**Decision:** B2-2 (exact tokens / `artifact_missing:<stage>` only; no bare DELIVERY_ORDER substring)

---

### BP-B3 — Unknown `premature_complete` class is a fake stage

```2564:2567:src/interview_mux/stage_completion.py
        if cls:
            return cls
```

`premature_complete:brand_new_class` → pin `brand_new_class` (not in DELIVERY_ORDER).

**Options**

1. Unknown class → refuse / empty / default `transitions` (bare premature).
2. Unknown class → allowlist of `_PREMATURE_NAMED_CLASSES` only; else None (fall through).
3. Keep return-cls (forward compatible for new classes without code).

**Recommendation (advice):** option 2.

**Decision:** B3-1 (unknown `premature_complete:<class>` → `transitions`)

---

### BP-B4 — `mark_done` silent AuthorityDenied

```561:567:src/interview_mux/run_context.py
                if isinstance(exc, AuthorityDenied):
                    self.log(...)
                    return
```

Return type is `None`. [`llm_flow_hardening.llm_stage_mark_progress`](../../src/interview_mux/llm_flow_hardening.py): `ctx.mark_done(stage_key); return True` — **True even if refuse**.

**When it fires:** hollow/ownership refuse during LLM “success” envelope.

**Forensics would see:** stage “complete” in flow-hardening logs, no `.stage_done`, later premature_complete.

**Options**

1. `mark_done` → `bool`; callers must check; hardening returns False if not stamped.
2. Raise AuthorityDenied (loud fail-stop).
3. Keep silent log (avoid crashing GUI/LLM path).

**Recommendation (advice):** option 1 — loud to callers, not necessarily SystemExit.

**Decision:** B4-2 (`mark_done` raises `AuthorityDenied`; runner/GUI catch → stage error / not-done)

---

### BP-B5 — ESR clears wait on bare `is_done`

```587:597:src/interview_mux/execution_status.py
            if seed_stage_complete(ctx, pin_s):
                return None
            if ctx.is_done(pin_s) and pin_s in {"master_finalize", *SHIP_AFTER_MASTER}:
                return None
        except Exception:
            try:
                if ctx.is_done(pin_s):
                    return None
```

Ship pins: hollow marker + any `master.wav` → no wait. Any exception in seed-complete → **any** pin with `is_done` → no wait (including hollow edl).

**Options**

1. Only `seed_stage_complete(pin)` (+ master file for ship) may clear wait; delete `is_done` escapes.
2. Keep ship-pin `is_done` (i5 cousin for markers without full seed-complete); delete the **exception** any-pin escape.
3. Keep both (maximize “don’t stall ship”).

**Recommendation (advice):** option 2 as minimum; option 1 if you want seed-complete as the only “done.”

**Decision:** B5-3 (keep `is_done` ship-pin and exception escapes)

---

### BP-B6 — Two `incompleteness_resume_stage` defs

First def `(reason, *, stage_id="")` uses PRODUCER_PIN_TABLE substring, **no** `premature_class_pin`. Second def shadows it. Live callers use `(ctx, stage)`.

**Options**

1. Delete the first def (or rename `incompleteness_prose_resume`).
2. Merge APIs explicitly.
3. Leave dead (hazard only).

**Recommendation (advice):** option 1.

**Decision:** B6-1 (delete the first `incompleteness_resume_stage`; keep `(ctx, consumer_stage)` only)

---

## Family 3 — Ship / driver wait

### What “done” means today (BP-C5 table)

| Surface | Predicate |
|---------|-----------|
| ESR `should_wait` None | `seed_stage_complete(pin)` + master file; **or** `is_done` on finalize∪SHIP + master; **or** exception + `is_done(pin)` |
| `progress_stale` / `wait_vs_halt` | lease → wait; fresh pin sources → wait; seed-complete+master → `done_pin_committed_master` (halt allowed) |
| Runner `status=complete` | Current **execute batch** finished |
| Runner ESR wait | job **`stalled`** (not durable running) |
| Driver `pipeline_complete()` | master.wav size&gt;1000 + `.stage_done/podcast_publish` + `episode_cover_generate` + `publish/cover.*` + `audio.mp3` |
| Agenda `ship_after_master_remaining` | `SHIP_AFTER_MASTER` stages lacking **`stage_outputs_present`** (not mere `.stage_done`) |
| `seed_stage_complete` | `is_done` ∧ outputs ∧ no incompleteness |
| G-Publish | Local package ≠ S3; advisory consent can hang remote while local ship bar is met |

These can all be true/false independently at the same wall-clock time.

---

### BP-C1 — Wrong pin still ESR-waits on fresh `master.wav`

**What disagrees:** i5 early-exit requires the **pinned** stage to be seed-complete/done. `_pin_keeps` for `mix` / `master_finalize` / `listen_delight*` still treats `master.wav` as producer freshness.

If pin=`mix` or `listen_delight_audit` (incomplete) **and** master already committed → `wait_vs_halt` can return **wait** `fresh:master.wav`. `should_wait` does not early-exit.

**When it fires:** post-master remaining work, heal still pinned to mix/delight (exec_13165 shape with a **wrong** pin).

**Tests:** `test_done_master_finalize_does_not_esr_wait_on_fresh_master` only pins `master_finalize`. Delight test only excludes vo_wavs.

**Options**

1. After committed master ∧ finalize seed-complete/done: never ESR-wait on `{mix, junction, listen_delight*, master_finalize} ∪ SHIP_AFTER_MASTER`.
2. After committed master: drop `master.wav` from freshness for non-active finalize pins.
3. Leave i5 as pin-self-only (wrong pin still waits).

**Recommendation (advice):** option 1.

**Decision:** C1-1 (post-master family never-wait when master committed and finalize done)

---

### BP-C2 — Driver keep-join requires `is_done`

[`tools/full_auto_driver.py`](../../tools/full_auto_driver.py) stalled path (~14128–14177): after dual sleep, **advance ship only if** `_ctx_stall.is_done(stage)`. Else if `stage in long_stages` (includes `master_finalize`, `episode_cover_generate`, `podcast_publish`) → **keep joining forever**.

**When it fires:** ESR `stalled` on finalize while pending writes / hollow refuse prevented `mark_done`; master.wav already on disk.

**Options**

1. Advance if master committed ∧ (`is_done` **or** `ship_after_master_remaining` **or** stage in ship set) — never infinite join.
2. Advance only on `is_done` (current) — safer against killing a live remaster.
3. Time-box keep-join then heal_navigate regardless of done.

**Recommendation (advice):** option 1.

**Decision:** C2-1 (advance if master committed and (`is_done` or ship remaining or stage in ship set))

---

### BP-C3 — Driver uses raw `wait_vs_halt` when master missing

Incomplete-after-conductor: **if master missing**, driver calls `expensive_stage_lease_active` then raw `wait_vs_halt` (not `should_wait_incomplete_after_conductor`). If master **present**, that wait block is skipped (ship-heal). Pipeline/agenda/runner always use `should_wait`.

**When it fires:** pre-master incomplete-after-conductor with a lease or fresh producer.

**Options**

1. Driver always uses `should_wait_incomplete_after_conductor` (parity).
2. Keep split: pre-master lease-wait is more aggressive by design.
3. Use `should_wait` but still honor lease execute-from lease_stage.

**Recommendation (advice):** option 1 + 3 combined (one helper, keep lease resume).

**Decision:** C3-1 (always `should_wait_incomplete_after_conductor`; keep lease_stage as resume target)

---

### BP-C4 — VO / MusicGen mtime leases after job stall

After WS5 (seed-complete + stalled job → no lease), code **still** treats:

- any `vo_pickup/synthesized/*.wav` mtime &lt; **180s** → lease `vo_synthesize`
- any `sound_design/assets/**/*.wav` mtime &lt; **120s** → lease `music_palette_compose`

**When it fires:** post-master backfill writes a VO wav; cover/publish ESR-waits as if Chatterbox is running.

**Options**

1. Suppress mtime leases when job status ∈ {stalled, idle, error} **and** pin is post-master/ship.
2. Suppress mtime leases whenever job is not running/starting (rely on pending_writes).
3. Keep ghosts (protects lagged gui_job during real synth).

**Recommendation (advice):** option 1.

**Decision:** C4-1 (suppress VO/MusicGen mtime leases when stalled/idle/error and post-master/ship)

---

### BP-C5 — Five meanings of done

Not a single bug — a vocabulary split that makes BP-C1–C4 possible. Aligning ESR “no wait,” driver `pipeline_complete`, and agenda `ship_after_master_remaining` is a **product** choice: local package vs remote S3 vs seed-complete finalize.

**Options**

1. Document the five predicates as intentional layers; only close C1–C4.
2. Pick one ship-bar SSOT (`pipeline_complete` **or** agenda remaining empty) and make ESR/driver consult it.
3. Treat G-Publish consent hang as the same class as ESR (probably wrong — operator product).

**Recommendation (advice):** option 1 for now; option 2 only if you want one operator-visible “DONE.”

**Decision:** C5-2 (`pipeline_complete()` is the ship-bar SSOT; G-Publish/S3 is not this bar)

---

## Suggested decision order

If you only want to spend attention on ship/thrash:

1. **BP-A2** freeze constitution (policy — everything else hangs on it)  
2. **BP-A1** precedes SSOT  
3. **BP-C1 + BP-C2** post-master wait/join  
4. **BP-B1 + BP-B4** pin/done honesty  
5. Rest as a bundle (A3–A5, B2–B3, B5–B6, C3–C5)

Reply with `BP-xx: option N` (or “leave / defer”) for the rows you care about; a follow-up plan can patch only those.
