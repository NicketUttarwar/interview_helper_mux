# Plan: Delivery thrash hardening (post-exec_5196)

**Goal:** Make the high-risk junctions from `exec_5196` deterministic so full-auto cannot reseat/omit/seed-rewind/invalidate itself into heal-spins.

**Scope:** Remaining gaps only. Items already in the working tree from the forensics campaign are listed under **Excluded (already built)** and must not be rebuilt.

**Success:** A fresh full-auto run can pass G1 → EDL → mix → finalize without VO seat thrash, premature consumer pins, pair-only VO rewinds, or publishability archiving the EDL finalize needs — without agent one-off JSON edits.

---

## Excluded (already built — do not redo)

These landed in product code (+ tests) during/after exec_5196. Treat as done; only wire call-sites if a gap below explicitly says so.

| Item | Location |
|---|---|
| Hosted VO floor: WAV-prefer reseat + noop when floor met | `vo_contract.ensure_hosted_framing_vo_seats` |
| Clamp seats to rendered WAVs | `vo_contract.clamp_hosted_seats_to_rendered_wavs` |
| Gap-line heal: keep omit on non-seated lines | `tools/full_auto_driver.py` gap-line heal |
| Premature-complete prefer `mix` when `assembly.wav` exists | `full_auto_driver` premature guards |
| Premature cap pin ranking producer when `selection.json` missing | `delivery_guardrails.premature_cap_hard_pin` |
| Empty `mmaudio_qa` heal before incompleteness | `stage_completion` + agenda |
| Seed-front: skip `vo_synthesize` for pair-only gaps after assembly | `homunculus/agenda.py` + `llm_flow_hardening.py` |
| VO script↔WAV bind; refuse silent rebind; purge; block mix/edl | `vo_synthesis_audit` (`wav_sha256`, `VoScriptWavRebindError`) |
| Adjudicate skip when WAV fresh; nuke on adjudicate text change | `vo_line_adjudicate` + `line_vo_wav_fresh` / `nuke_all_synth_*` |
| Transition staging: fall back to committed WAV | `transition_vo.current_pair_wav_usable` |

**Also out of scope for this plan:** remastering shipped `exec_5196` audio; committing the existing working-tree patches (ops, not design).

---

## Principles (highest leverage — implement as invariants)

Encode these as named helpers + tests, then call them from every mutation path:

1. **One writer per authority** — seats/omit → `vo_contract` only; script↔WAV → `vo_synthesis_audit` only; stage_done completeness → `stage_completion` only; pair set → `transition_vo` only.
2. **Monotonic delivery after assembly** — if `master/assembly.wav` exists and G1 green, seed-front may not pin `vo_synthesize` except for seated **script↔WAV mismatch** (rebind already forbidden).
3. **Mismatch ⇒ delete + regenerate** — never stamp audit onto old bytes (done); extend to any new heal that touches VO.
4. **Producer before consumer** — premature / identical / ladder / finalize always pin earliest incomplete **producer**, never the failing consumer alone.
5. **Clamp after every seat mutation** — any omit/seat/filter path ends with `clamp_hosted_seats_to_rendered_wavs` + contract validate (wire remaining call-sites).
6. **Invalidation must not eat the heal target** — soft publishability / repair must not `clear_from(edl)` archive live `master/edl.json` that finalize needs.

---

## Workstreams (remaining high-risk)

### W1 — Freeze spoken transition pair set (High)

**Problem:** Mid-delivery pair expansion marks `vo_synthesize` incomplete and fights seed-front / mix.

**Do:**
- On first successful EDL commit (or first green G1+transitions write), stamp `master/transitions_pair_freeze.json` = frozen `(after, before)` set + generation.
- Later selection/EDL deltas that add pairs go to `deferred_transition_pairs` — synth only in mix last-chance, never unmark full `vo_synthesize`.
- `stage_artifact_incompleteness("vo_synthesize")` ignores deferred pairs when freeze exists + G1 green.

**Tests:** freeze present → new pair does not flip vo incompleteness; mix last-chance still synths deferred.

### W2 — Publishability / invalidation must not archive live EDL (High)

**Problem:** `checkpoint_publishability(post_edl)` → repair → `invalidate_downstream(edl)` → archives `edl.json` → `master_finalize` thrash on missing ledger/seam.

**Do:**
- Soft/advisory publishability failures: write repair plan **without** `clear_from("edl")`, or archive only *downstream of mix*, never the just-committed EDL/ledger.
- Hard publishability block: may invalidate, but must re-emit EDL+ledger in the same heal before returning.
- `master_finalize` input check: if EDL missing but `.archived/*/master/edl.json` fresh → restore or pin `edl`, not ranking.

**Tests:** post_edl soft fail leaves `master/edl.json`; finalize pins `edl` when ledger missing but EDL present.

### W3 — Finalize ↔ ledger / seam producer pin (High)

**Problem:** Finalize blocked on `assembly_ledger` / `seam_autopsy`; identical_failures spin without a single producer pin.

**Do:**
- Map missing ledger → resume `edl` (ledger writer); missing seam_autopsy → `junction_snip_qa` (or edl if never mixed).
- Driver identical-failure / stage-input heal uses that map (no premature_cap to mix/finalize).
- Ensure `write_assembly_ledger` runs at EDL commit and is re-runnable without full NLE.

**Tests:** finalize with EDL+no ledger → pin edl once; after ledger write, finalize input clears.

### W4 — Clamp-after-mutate audit (Medium — wire gaps)

**Problem:** Clamp exists but not every omit/filter/heal path calls it → rare seat thrash regressions.

**Do:**
- Inventory all writers of `vo_seats` / gap omit flags (`air_script`, `omit_ledger`, `execution_contract`, driver heals, hitch).
- Require terminal `clamp_hosted_seats_to_rendered_wavs` (or document why N/A).
- Add one regression: omit Pass B → clamp → active count ≤ rendered WAVs and ≥ floor when WAVs allow.

### W5 — Hollow `stage_done` hard rule (Medium)

**Problem:** Done stamped without artifacts → consumer fail → heal remakes done.

**Do:**
- Centralize: `mark_done` / seed_complete refuse when `stage_artifact_incompleteness` non-None (except explicit skip stubs).
- Driver forensics: never `mark_done(..., force=True)` for VO/EDL/mix without incompleteness None.

**Tests:** force-done with missing G1 WAV → incompleteness still blocks seed-complete.

### W6 — Monotonic delivery guardrail (Medium — formalize)

**Problem:** Principle partially implemented; still possible for other heals to unmark `vo_synthesize` after assembly.

**Do:**
- Single helper `may_rewind_to_vo_synthesize(ctx) -> bool` (G1 red **or** seated script↔WAV mismatch only).
- All driver/agenda/llm_flow unmark paths call it; log wasted_work on refuse.

**Tests:** assembly+G1 green+pairs deferred → unmark vo refused; seated stale hash → allowed.

---



### W7 — Stale transitions EDL pin (High — exec_5400)

**Problem:** Layup stamps `master/transitions.json` stale; EDL execute 500s; `playbook_upstream_stale_rerun(edl)` returned `[]` because `upstream_stale_blockers` only checked transitions for `vo_synthesize`. Identical execute ×5 → sticky GUI "Run Transitions" / driver stop.

**Do (landed in stale-transitions autoheal):**
- `STALE_PREFLIGHT_CONSUMERS` + `_TRANSITIONS_STALE_CONSUMERS` include `edl` / `edl_narrative_audit` / `assembly_preview`.
- `playbook_upstream_stale_rerun` disk fallback; driver `_heal_stale_transitions_execute`; suppress needs_operator for marked-stale / seed-order; sticky job reconcile.
- Seams seed-prereq honesty when `seed_stage_complete(air_script_seams)`.

**Unstick exec_5400 (same run, after pytest green):**
1. Clear identical halt / sticky `gui_job` needs_operator (reconcile or idle + message).
2. Confirm `air_script_seams` seed-complete.
3. Resume partial-auto `MUX_FRESH=0` `from_stage=transitions` on `exec_5400_…`.
4. Expect transitions regenerate → EDL continues without operator CTA.

## Explicitly deferred (not in this plan)

| Item | Why deferred |
|---|---|
| Junction remaster oscillation caps | Partial product exists; lower 5196 impact than W1–W3 |
| MusicGen ↔ listen_delight seal | Music epoch already partially sealed; not top 5196 thrash |
| Full “one writer” refactor of all JSON mutators | Principles + W4 call-site audit first; big-bang rewrite later |
| Remaster exec_5196 mismatched VO | Content fix for one ship; not thrash hardening |

---

## Implementation order

1. **W2** (stop deleting EDL) + **W3** (finalize pin) — unblocks ship bar thrash  
2. **W1** (pair freeze) — stops late VO seed thrash  
3. **W6** + **W4** — lock monotonic + seat authority  
4. **W5** — hollow done  

Each workstream: patch → pytest asserting **predicate flip** (stage advances or incompleteness clears) → no second fresh exec required for unit proof.

## Verify

```bash
pytest tests/test_execution_flow_hardening.py \
  tests/test_delivery_guardrails.py \
  tests/test_vo_wav_fresh.py \
  tests/test_synthesis_report.py \
  tests/test_homunculus.py \
  # + new tests for W1–W3
```

Optional: one fresh `MUX_FRESH=1` forensics campaign after W1–W3 land (not to verify old 5196).

---

## Done when

- [x] W1–W3 merged with tests  
- [x] W4 call-site inventory complete; missing clamps wired  
- [x] W5–W6 helpers enforced on agenda/driver unmark paths  
- [x] Plan checklist does not re-implement Excluded table  
- [x] Spoken text cascades (gap + transitions) + hash-fresh transition completeness (post-exec_5401)

## Follow-on (T1–T8)

See [thrash_edge_case_hardening](thrash_edge_case_hardening_f9dfad74.plan.md) for sticky halts, filter-empty incomplete, canonical pins, artifact_usable, regen blast radius, pending honesty, forensics suppress budget.

### Unstick exec_5402 (same run)

1. Restart `interview_mux serve` + partial-auto driver so code loads.
2. Reconcile: `promote_complete_orphan_stage_done` + `seal_phase_a_if_stable` on the run.
3. Resume `MUX_FRESH=0` `from_stage=music_palette_compose` — no second fresh exec.

### Productized (1–2)

- **Unstick playbook:** `delivery_unstick.run_delivery_unstick` + `POST /api/runs/{id}/delivery/unstick` + GUI buttons on thrash / needs_operator.
- **Dual-driver:** `driver_singleton` claim file; `ensure_e2e` refuses second healer without `force`; serve start runs `on_serve_restart_harden` (hydrate + clear stale claims).

### Productized (3–6 follow-on)

- **Claim release on exit:** `atexit` + `__main__` finally → `release_driver_run`.
- **heal_navigate-only driver entry:** `_heal_resume` replaces hardcoded edl/narrative resume sites (qc, missing EDL, transition heal, narrative_qc, premature mix drift).
- **Ship-path honesty:** `enforce_job_complete_honesty` demotes false complete when master exists but encode/PMQ/publish incomplete (respects g-publish pending/skip).
- **Why pinned banner:** `delivery_pin_summary` + `operator/delivery_pin.json` from `heal_navigate`; GUI “Why pinned” line.
