# Cross-surface gaps report

**Mode pin:** brain **0.2.0** · operator mode **partially_accelerated** (primary)  
**HEAD:** `e7658ccab` · investigated **2026-09-19T22:53Z** (decisions updated **2026-09-20**)  
**Campaign:** investigation-only (no product patches yet)  
**Plan:** [cross-surface_investigation_8e230ac3.plan.md](file:///Users/nicketuttarwar/.cursor/plans/cross-surface_investigation_8e230ac3.plan.md)

## Summary

Investigation catalogued cross-surface seams under Partial + 0.2.0. **Implement scope** (below) no longer includes DeliveryUnlock GUI or identical-halt recovery (dropped by operator). **G-Listen** product decision: default **`warn`** everywhere — not a release blocker.

| Status (investigation catalog) | Count |
|--------|------:|
| closed | 14 |
| covered | 9 |
| partial | 8 |
| open | 6 |
| needs_soak | 3 |
| **Total findings** | **40** |

**P0 implement:** nested synth skip-not-stamp (H-1)  
**P1 implement:** G-Listen → **warn** fleet-wide (P0-2/B-6); narrative QC soft (X-3); classify-before-registry (F-2)  
**P2 implement:** defaults inventory Partial column; transition sidecar staged test; ownership sidecar audit; Partial readiness addendum  
**Freeze policy (G-4 / H-3):** **End-A allowlist only; otherwise freeze wins** — see [Solutions § Freeze](#g-4--h-3--freeze-vs-gapomit--end-a-allowlist-only)  

**Dropped from implement (removed entirely):** DeliveryUnlock-without-GUI · identical ×3 halt limbo · seats unlock UI · G-2 unlock CTA copy  

**Solutions:** see [Solutions (decided)](#solutions-decided--progress-to-masterwav).

---

## Method

| Step | Result |
|------|--------|
| `tools/audit_artifact_ownership.py --write-sites-only --allow-unknown-write-sites` | `unknown_write_sites: 0`, matrix `e2265fb515280416` |
| Ownership smoke (`write_permitted`) | transition/vo/speech ALLOW for listed writers |
| Cascade pytest (`MUX_FORENSICS=0`) | **122 passed** — `test_hg4_*`, `test_vo_path_ready`, `test_nugget_layup`, `test_placement_qa`, `test_gap_framing_gates`, `test_asset_transcripts` |
| Code reads | `operator_gates`, `gap_vo_gates`, `gates`, `placement_qa`, `nugget_layup`, `heal_routing`, `homunculus/agenda`, `full_auto_driver` |
| Explore pass | Phase 2/3 seams ([explore agent](5ce299d3-7a11-492d-8d8a-1a184f0a3f37)) |

**Status vocabulary:** `closed` · `open` · `partial` · `needs_soak` · `covered`  
**Severity:** `P0` ship/thrash · `P1` Partial stall / heal spin · `P2` hygiene

---

## Phase 0 — Mode inventory (0.2.0 + Partial)

### Gate table (HEAD at investigation; G-Listen target = warn)

| Gate | Auto under Partial? | Human must act? | Heal if left open? | Evidence |
|------|---------------------|-----------------|--------------------|----------|
| **G0** transcript_review | No (driver waits) | **Yes** | Pause / timeout → needs_operator | `full_auto_driver.wait_for_operator_g0` |
| **Preclean** | Deferred until after G0 | Offer / auto_run after G0 | N/A | `operator-gates.md` |
| **G-Framing** | Often yes via 0.2.0 auto_resolve / `auto_accept_defaults` | If unset & no auto path | Heal pins missing_framing | `maybe_auto_accept_gap_gate_defaults` |
| **G-Speaker / VoiceRef / Delivery / Clone** | Auto when auto-accept armed | If pending without auto | Heal → missing_framing (HG-4) | `vo_path_ready` |
| **G1** | Chatterbox may be `automation_pending` | Optional skip / synth | Classified ladder | `operator_gate_view` |
| **G-Listen** | Advisory under target **`warn`** | No hard finalize stop | Continue without Continue/Skip | **Target:** `app.defaults` + docs + fallbacks = `warn` (not a release blocker) |
| **Timeline optimizer** | GUI Take best / Skip | Yes if pending | Full-auto `handle_gate` clears; Partial uses GUI | `clear_optimizer_remaster_for_finalize` |
| **G-Publish** | No S3 auto | **Yes** Upload/Skip | Driver waits | `wait_for_operator_g_publish` |
| **SFX G1.5 prompt** | Full-auto auto-approve | Partial GUI if warnings | MED stall | defaults_inventory |
| **Narrative QC** | Soft under Full-auto (Partial target: same) | Manual **SystemExit** on fail | — | `gates.check_narrative_qc` / FMR-B2 |

### Findings

| id | Finding | Status | Sev | Next action |
|----|---------|--------|-----|-------------|
| P0-1 | Defaults inventory is titled Full-auto; Partial behaviors are footnotes | partial | P2 | [Solutions § P0-1](#p0-1--defaults-inventory-partial-column) |
| P0-2 | `g_listen_mode`: HEAD code default was `block`; docs/fallbacks often `warn` | open | P1 | **Ship `warn` everywhere** — [Solutions § P0-2](#p0-2--b-6--g_listen_mode--warn-fleet-wide) |
| P0-3 | Brain 0.2.0 seed walk + `should_stamp_needs_operator` unattended path | closed | — | CSP-03 ruled; keep |
| P0-4 | Partial G0 + G-Publish waits are intentional product | covered | — | Soak: confirm GUI focus overlays |

---

## Phase 1 — Core tracks

### Track A — Ownership / write-path

| id | Finding | Status | Sev | Next action |
|----|---------|--------|-----|-------------|
| A-1 | Literal `write_json` AST audit: **0** unknown write sites | closed | — | Keep in CI / tape preflight |
| A-2 | `transcripts/transition/*.json` ALLOW (i5) | closed | — | Cascade test exists |
| A-3 | Transition/VO/speech smoke `write_permitted` ok | closed | — | — |
| A-4 | Transition sidecar test is predicate-only | partial | P2 | [Solutions § A-4](#a-4--transition-sidecar-staged-write-cascade) |
| A-5 | Dynamic sidecar helpers not fully covered by AST audit | partial | P2 | [Solutions § A-5](#a-5--ownership-audit-covers-sidecar-helpers) |

### Track B — Operator gate ladder (Partial + VO SSOT)

| id | Finding | Status | Sev | Next action |
|----|---------|--------|-----|-------------|
| B-1 | `vo_path_ready` SSOT (Workstream A) | covered | — | Landed |
| B-2 | HG-4 voice approve / heal pin | covered | — | Landed |
| B-3 | Pickup pending survives framing mark_done without confirm | covered | — | Landed |
| B-4 | synthesize-all hard refuse when not ready | covered | — | Landed |
| B-6 | G-Listen was `block` in defaults — release should not hard-stop | open | P1 | Align to **`warn`** — see P0-2 |

### Track C — QC accounting pairs

| id | Finding | Status | Sev | Next action |
|----|---------|--------|-----|-------------|
| C-1 | Orientation park credits air coverage (i2) | covered | — | Workstream B |
| C-2 | Air coverage aspirational + pick-best | covered | — | Workstream B |
| C-3 | Adjudicate aligned | covered | — | Workstream B |
| C-4 | Other clear↔credit pairs not fully matrixed | needs_soak | P2 | Soak |

### Track D — Remaster / sibling preserve

| id | Finding | Status | Sev | Next action |
|----|---------|--------|-----|-------------|
| D-1 | Theme XF floors + remaster preserve (i4 / C) | covered | — | Workstream C |
| D-2 | Oscillation residual soft when non-critical | covered | — | Workstream C |
| D-3 | Live remaster↔PMQ under Partial | needs_soak | P1 | Soak |

### Track E — Driver vs Partial GUI clears

| id | Finding | Status | Sev | Next action |
|----|---------|--------|-----|-------------|
| E-1 | Full-auto `handle_gate` clears timeline-optimizer + g_listen | closed | P2 | Secondary |
| E-2 | Partial relies on GUI for G0, G-Publish, optimizer, SFX warnings | covered | — | Soak checklist |

---

## Phase 2 — Whole-pipeline seams

### Track F — Seed / heal / thrash

| id | Finding | Status | Sev | Next action |
|----|---------|--------|-----|-------------|
| F-2 | `PLAYBOOK_REGISTRY` default resume can disagree with live classify | partial | P1 | [Solutions § F-2](#f-2--playbook_registry-vs-live-classify) |
| F-3 | EDL ↔ narrative conductor/heal pin agreement | closed | — | Category B tests |
| F-4 | mix→junction via `junction_recut_precedes_mix` | needs_soak | P1 | Soak; unit coverage exists |
| F-5 | Layup hash oscillation → pick-best | covered | — | Workstream B |

### Track G — Analysis ↔ delivery handoffs

| id | Finding | Status | Sev | Next action |
|----|---------|--------|-----|-------------|
| G-4 | gap_report multi-producer + freeze | decided | P1 | Allowlist only; freeze otherwise — [Solutions](#g-4--h-3--freeze-vs-gapomit--end-a-allowlist-only) |

### Track H — Delivery cluster

| id | Finding | Status | Sev | Next action |
|----|---------|--------|-----|-------------|
| H-1 | Nested EDL/transition synth vs VO ladder (Partial auto_accept / transitions ungated) | open | P0 | [Solutions § H-1](#h-1--nested-edl--transition-synth-vs-vo-ladder) |
| H-2 | pair_freeze only when G1 skipped/green | covered | — | Intentional |
| H-3 | omit ↔ air_contract under freeze | decided | P1 | Allowlist only; freeze otherwise — [Solutions](#g-4--h-3--freeze-vs-gapomit--end-a-allowlist-only) |

---

## Phase 3 — Ship under Partial

| id | Finding | Status | Sev | Next action |
|----|---------|--------|-----|-------------|
| S-1 | PMQ / GUI advisory vs blocking honesty | closed | — | F6 + qcSummaryState |
| S-2 | G-Publish Partial wait Upload/Skip | covered | — | Intentional |
| S-3 | `require_g_publish_clear` KEEP DEAD | covered | — | Clinic |
| S-4 | Aspirational local ship vs S3 | closed | — | Intentional |
| S-5 | Untitled/empty episode_meta refuse | covered | — | Clinic 6B |

---

## Clinic cross-check

| id | Finding | Status | Sev | Next action |
|----|---------|--------|-----|-------------|
| X-1 | CSP-01…06 ruled | closed | — | — |
| X-2 | Readiness scorecard Full-auto-centric | partial | P2 | [Solutions § X-2](#x-2--partial-readiness-addendum) |
| X-3 | Narrative QC SystemExit on Partial | open | P1 | Soft unattended — [Solutions § X-3](#x-3--narrative-qc-systemexit-on-partial) |

---

## Solutions (decided — progress to master.wav)

**Operator decisions** (bias: reach complete `master.wav`; defer to better-equipped stages; G-Listen must not block release).

| # | Topic | Decision |
|---|--------|----------|
| 1 | H-1 nested synth | **Skip illegal mint; continue.** Never Partial `auto_accept` stamp. WAV demand → G1 / `vo_synthesize` / mix. |
| 2 | X-3 narrative QC | **Soft Partial like Full-auto** (`is_unattended_run`); Manual stays strict. |
| 3 | P0-2 / B-6 g_listen | **`warn` everywhere** — `app.defaults`, docs, code fallbacks. **Not a release blocker.** |
| 4 | F-2 heal resume | Live classify **before** registry default. |
| 5 | P2 hygiene | P0-1, A-4, A-5, X-2 included. |
| 6 | G-4 / H-3 freeze | **Only** `HARD_FREEZE_ALLOWLIST_ACTIONS`; **otherwise freeze wins** (no expand). |
| 7 | Dropped | DeliveryUnlock GUI · identical ×3 halt card · seats unlock UI · unlock-CTA copy (G-2) — **removed from this plan.** |

### Design principles (anti-footgun)

| Do | Don't |
|----|--------|
| Skip illegal nested Chatterbox; let later VO/mix own missing WAVs | Hard-refuse whole EDL for open consent |
| Partial nested: never `auto_accept=True` | Stamp gates from EDL/transition |
| Soft narrative QC for unattended only | Soft Manual or flip global `narrative_qc.strict` |
| Ship `g_listen_mode=warn` in defaults + docs + fallbacks | Leave `block` as default (blocks finalize / release path) |
| Live classify before playbook registry | Trust stale registry resume alone |
| Under freeze: only End-A allowlist mutations | Expand allowlist for convenience; invent gap seats; broad omit revive |

---

### P0 — nested synth (implement first)

#### H-1 — Nested EDL / transition synth vs VO ladder

**HEAD note:** Gap resync calls `require_vo_path_ready(..., auto_accept=True)` (bad for Partial); can swallow errors; transitions resync has no check.

**Decided solution:**

1. Before any nested Chatterbox/S2S (gap **and** `resync_spoken_transitions`): if ladder not ready under Partial → **do not mint**, log/note `nested_synth_skipped:vo_path_not_ready`, **continue** the stage.
2. Never `auto_accept=True` on Partial nested paths. Full-auto may keep auto-accept when its driver already armed gates.
3. Do not catch readiness failure into “synth anyway.”
4. Missing WAVs surface later at G1 / `vo_synthesize` / mix incompleteness.

**Avoid:** Hard-stopping EDL; stamping gates from nested resync; fail-open synth after swallowed exception.

**Verify:** Partial + consent open + EDL/transition resync → stage completes, zero new clone WAVs, note present.

---

### P1 — stalls / honesty

#### P0-2 / B-6 — `g_listen_mode` → warn fleet-wide

**Decided:** G-Listen is **advisory only** for release. Default **`warn`** everywhere — finalize must not hard-stop on G-Listen pending.

1. Set [`config/app.defaults.json`](config/app.defaults.json) `sound_design.g_listen_mode` → **`warn`** (change from `block` if still `block` on HEAD).
2. Keep [`docs/workflows/operator-gates.md`](docs/workflows/operator-gates.md) aligned: default **warn**; optional Continue/Skip when UI shows it; not required for ship.
3. Runtime fallbacks in `gates.require_g_listen_clear` / junction helpers: missing key → **`warn`** (already often true — ensure no path still defaults to `block`).
4. Update defaults_inventory / Partial readiness notes: G-Listen is non-blocking under defaults.
5. Full-auto auto-clear can remain as belt-and-suspenders; Partial should progress without operator G-Listen action when mode is `warn`.

**Avoid:** Shipping `block` as the product default; documenting `block` as required for release.

**Verify:** With defaults, Partial/manual finalize does not SystemExit / stall solely on G-Listen pending; config key and docs both say `warn`.

#### X-3 — Narrative QC SystemExit on Partial

**Decided:** Soften for **all unattended** (Partial + Full-auto).

1. `check_narrative_qc`: use `is_unattended_run(meta)` instead of `is_full_auto_run` only.
2. Manual remains strict SystemExit.
3. Record QC summary + advisory; do not block ranking/EDL on Partial.

**Avoid:** Global `narrative_qc.strict=false`; soft Manual.

#### F-2 — PLAYBOOK_REGISTRY vs live classify

**Decided:** Live classify / resume helpers **before** registry default on escalate paths. Unit table for known families. Keep registry as cold fallback only.

**Avoid:** Delete registry; Partial-only remaps.

---

### P2 — hygiene (include; low risk)

#### P0-1 — Defaults inventory Partial column

**Smart solution:** Inventory Partial vs Full-auto defaults in code (`config/app.defaults.json`):

1. Add columns: `partial_auto` | `full_auto` | `must_act_partial` (or compact Phase-0 gate table).
2. Record G-Listen default **`warn`** (non-blocking).
3. `last_verified` bump; keep `code_is_king`.

**Avoid:** Deleting Full-auto forensics notes; inventing defaults not in code.

#### A-4 — Transition sidecar staged-write cascade

**Smart solution:** One `MUX_FORENSICS=0` test:

1. Stage as `master_transcript_build` → `write_transition_sidecar` → promote/flush.
2. Assert artifact on disk + `write_permitted` still true.

**Avoid:** Writing outside staging; broadening ALLOW to make the test pass.

#### A-5 — Ownership audit covers sidecar helpers

**Smart solution:** Extend [`tools/audit_artifact_ownership.py`](tools/audit_artifact_ownership.py):

1. Resolve `write_script_sidecar` / `KIND_FOLDERS` → `transcripts/{speech,vo,transition}/*.json`.
2. Assert ALLOW rows; hard fail on `missing_sidecar_allow`.
3. Hook into residual/tape preflight if already calling this audit.

**Avoid:** `transcripts/**` blanket ALLOW.

#### X-2 — Partial readiness addendum

**Smart solution:** Document Partial must-act gates vs Full-auto auto-accept:

1. Partial must-act: G0, G-Publish (and other true journey gates).
2. G-Listen under defaults = **warn / non-blocking**.
3. Narrative QC soft on Partial = intentional progress posture.

**Avoid:** Flipping clinic verdict to `not_ready` because Partial has intentional human gates (G0 / G-Publish).

---

### G-4 / H-3 — Freeze vs gap/omit: End-A allowlist only

**Decided (both cases):** One shared End-A list in [`seat_authority.py`](src/interview_mux/seat_authority.py) `HARD_FREEZE_ALLOWLIST_ACTIONS`. Under soft/hard seat freeze:

- **Allowed:** only actions on that allowlist (paperwork / shrink / orientation / pair-freeze trim — never expand WAV demand).
- **Otherwise:** **freeze wins** — refuse the mutation (`hard_freeze_blocks_action` / `seat_freeze_blocked_*`); do not reseat gap, do not broad-heal omit/air-contract.
- **Forbidden even if asked:** `protect_hosted_vo_floor_reseat` (`HARD_FREEZE_FORBIDDEN_ACTIONS`).

**Allowlist (SSOT — do not invent a second list):**

| Action | Plain meaning |
|--------|----------------|
| `omit_ledger_order_lock_rebuild` | Rebuild omit order-lock to match selection order |
| `omit_ledger_revive_orientation` | Revive orientation if wrongly omitted |
| `protect_orientation_from_omit` | Keep opening orientation off the omit path |
| `stamp_gap_omit_flags` | Stamp gap omit flags (paperwork) |
| `drop_seated_missing_from_gap` | Drop gap seats with no real seat/WAV (shrink only) |
| `clamp_hosted_seats_to_rendered_wavs` | Clamp hosted seats to existing WAVs |
| `drop_blank_segments_under_freeze` | Drop blank/zero segments |
| `stamp_pair_freeze` / `trim_pair_freeze` | Transition pair-freeze bookkeeping |
| `framing_dedupe` | Dedupe framing (no new WAV demand) |
| `normalize_omit_ids` | Normalize omit id lists |

**Ship-blocking omit is not a second constitution (A2-2):** `_ship_blocking_omit_ids` may classify a delta for logs; `commit_selection_mutation` does **not** honor it. Freeze restores order until End-A, one-shot, or `request_seat_rewrite` unlock. Mix may refuse `incomplete_cut_unresolved` until unlock.

**G-4 (gap_report):** producers may run post-freeze as **check/refuse**; only allowlisted gap paperwork above. No new lines, no general reseat, no optimizer gap promote under freeze. Direct gap / transitions / SDP persist uses `persist_frozen_seat_doc` (End-A or skip).

**H-3 (omit / air-contract):** heals may run allowlisted order-lock / orientation / normalize; broader revive/heal → freeze wins (`seat_freeze_blocked_heal*`). PMQ structural omit stays honest until allowlisted fix or human unlock seats.

**Implement note:** Prefer cascade tests that assert allowlisted actions proceed and unknown/forbidden actions refuse — **not** expanding the set. Stages stay non-redundant: pre-freeze they write; post-freeze they audit + allowlist-only.

**Avoid:** Adding allowlist entries “to unblock Partial”; auto-unlock seats; aspirational-soft of structural omit under freeze.

---

### Implementation order (locked)

**P0:** H-1 (skip-not-stamp nested synth)  
**P1:** P0-2 / B-6 (`g_listen` → **warn** fleet) → X-3 (narrative unattended soft) → F-2 (classify before registry) → **G-4/H-3 policy tests** (allowlist-only / freeze otherwise)  
**P2:** P0-1 inventory → A-4 test → A-5 audit → X-2 addendum  
**Then:** Partial soak (other needs_soak: C-4, D-3, F-4)  

---

## Partial soak recommendations

Run **one** Mohan-class tape on brain **0.2.0** + **partially accelerated** (not forensics Full-auto). Exercise:

1. **G0** — complete transcript review; confirm deferred preclean then runs  
2. **Framing ladder** — confirm pickup/voice-ref/delivery/consent; synth only when ready  
3. **G1** — skip or synth; confirm no illegal nested mint while consent open (H-1)  
4. **G-Listen** — with defaults `warn`, finalize should **not** require Continue/Skip  
5. **Timeline optimizer** — Skip or Take best via GUI if it appears  
6. **Finalize → PMQ** — advisory vs blocking paint; local package  
7. **G-Publish** — Skip or Sync S3  

**Do not** treat Full-auto forensics as proof of Partial reliability.

---

## Backlog map → general improvements

| Finding ids | Disposition |
|-------------|-------------|
| A-2, B-1–B-4, C-1–C-3, D-1–D-2, F-5 | **covered** — already landed A/B/C |
| C-4, D-3, F-4 | **needs_soak** (live validation only) |
| **G-4, H-3** | **decided** — End-A allowlist only; freeze otherwise (+ cascade tests) |
| B-5, G-1, E-3, F-1, G-2, G-3 | **dropped** — removed from implement plan |
| **H-1** | P0 — skip illegal nested mint |
| **P0-2, B-6** | P1 — **`g_listen_mode=warn`** fleet-wide (not a release blocker) |
| **X-3, F-2** | P1 — narrative soft; classify-before-registry |
| **P0-1, A-4, A-5, X-2** | P2 — hygiene |

**Implement:** P0 → P1 (incl. freeze allowlist policy tests) → P2 → Partial soak.

---

## Honest limits

This report does **not** claim the app is bug-free. Decided solutions above are ready for a follow-on implement campaign; they are not yet applied on HEAD (except where prior A/B/C work already landed).
