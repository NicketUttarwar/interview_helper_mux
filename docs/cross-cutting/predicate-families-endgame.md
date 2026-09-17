# Predicate families — endgame (mastering / delivery seal)

Living checklist of **late-delivery failure families** that keep recurring across full-auto forensics even after per-predicate iN patches. Scope is **G-EDL → G-VO bind → G-Mix / junction → G-Ship (PMQ)** — the mastering seal, not early analysis.

**Doctrine:** Predicates are **gate failure names**, not root causes. Forensics `exec_*` / `forensics_errors.*` / campaign iN notes are **HINTS ONLY**. Rows need **HEAD proof** (`file:function`) that the invariant can still be violated (or that a partial patch lacks a durable `MUX_FORENSICS=0` fixture). Prefer **reopening an existing F\*/H\* family** when the same invariant already has a closed row whose fixture would still pass if product regressed.

**Why this ledger exists:** Forensics patches stop the *exact* crash; cousins return in the same neighborhood because **authority / completeness / heal-pin** conflicts stay open. Cluster surface fails into **End-A…F** before inventing new IDs.

**Related:** [predicate-families-head.md](./predicate-families-head.md) (H\* identify ledger) · [predicate-families.md](./predicate-families.md) (F1–F7 closed campaign ledger) · [air-order-boundary.md](./air-order-boundary.md) · [publishability-contract.md](./publishability-contract.md) · [mastering-quality-hardening.md](./mastering-quality-hardening.md)

**Hint corpus (optional):** `exec_11630_d19c15b58ab4_20260915T033341Z` — 11 major surface issues mapped below; `operator/forensics_errors.json` unique predicates ≈26 (orientation thrash dominates volume).

---

## Agent iteration protocol

### Phase 1 — Identify (populate only)

On each identify invocation:

1. Read this file.
2. For each `open` / `partial` End-\* row (or unmapped major hint), fill or refresh: **Example predicates**, **Producer stage(s)**, **HEAD proof**, **Likely code**, **Maps from (surface)**. Do **not** patch.
3. If a hint belongs to a closed F\*/H\* invariant, note **Reuse** and leave End-\* as `partial` only if HEAD still lacks fixture coverage for the cousin; otherwise mark `superseded` in notes and do not duplicate work.
4. Reply with identify deltas only; next step is operator-approved resolve queue.

### Phase 2 — Resolve (one family per turn)

**Work queue order:** `End-A` → `End-B` → `End-D` → `End-F` → `End-C` → `End-E`

On each resolve invocation:

1. Read this file. Pick the **first** ID in the queue whose Status is `open` or `partial` (ignore `closed` / `superseded`).
2. Work **only that one family** this turn.
3. Investigate HEAD proof + likely code; summarize the failure in plain language. Exec/forensics may inform; they do not gate the row.
4. **Ask the operator** 1–3 concrete resolution questions (policy / tradeoffs) before patching. Wait for answers.
5. Patch **producer invariant** + add fixture pytest with `MUX_FORENSICS=0`; run the new/related tests.
6. Update this ledger row: Status → `closed`, fill **Fixture / test** with paths + pytest node id(s); refresh **HEAD proof** if needed.
7. Reply with exactly: `COMPLETE: <ID> — <one-line summary>` and name the **next** queue ID still open/partial (or `QUEUE EMPTY`).

Do not start a forensics run for discovery. Do not open a second family in the same turn. Do not edit F1–F7 / H\* rows except to note **Reuse** here.

---

## Copy-paste agent prompts

**Parallel-safe identify:** open **6 Agent chats**, paste one block each. Each chat writes **only** its sidecar under `docs/cross-cutting/predicate-families-endgame-identify/` — never the main ledger. When all six report `IDENTIFY COMPLETE`, open a **7th chat** and paste **MERGE**.

### Chat 1 — End-A

```text
IDENTIFY ONLY — End-A (sidecar; parallel-safe).

Read:
- docs/cross-cutting/predicate-families-endgame.md (Phase 1 + End-A row + constitutional Q for End-A)
- docs/cross-cutting/predicate-families-head.md (Reuse HF/HG/HE/HC as relevant)
- docs/cross-cutting/predicate-families.md (Reuse F2/F3 as relevant)
- Hint only: ASSETS/executions/exec_11630_d19c15b58ab4_20260915T033341Z/operator/forensics_errors.json

Family: End-A — Seat / omit / freeze constitution

Rules:
- IDENTIFY ONLY — no product/test patches, no runs/forensics, do not mark closed.
- Write ONLY docs/cross-cutting/predicate-families-endgame-identify/End-A.md (fill the template).
- Do NOT edit predicate-families-endgame.md or any other End-*.md.
- Subagents unlimited OK; they must not write files — only you write End-A.md.

Fill: plain-language failure, predicates, producers, HEAD proof (file:function), likely code, Reuse/gap vs F*/H*, 1–3 unanswered policy questions, fixture gap, one-line summary, status suggestion.
Reply: IDENTIFY COMPLETE: End-A — <one line>
```

### Chat 2 — End-B

```text
IDENTIFY ONLY — End-B (sidecar; parallel-safe).

Read:
- docs/cross-cutting/predicate-families-endgame.md (Phase 1 + End-B row + constitutional Q for End-B)
- docs/cross-cutting/predicate-families-head.md (Reuse HV-2, HE-2, HC-3 as relevant)
- docs/cross-cutting/predicate-families.md (Reuse F2)
- Hint only: ASSETS/executions/exec_11630_d19c15b58ab4_20260915T033341Z/operator/forensics_errors.json

Family: End-B — Bind / promote authority

Rules:
- IDENTIFY ONLY — no product/test patches, no runs/forensics, do not mark closed.
- Write ONLY docs/cross-cutting/predicate-families-endgame-identify/End-B.md (fill the template).
- Do NOT edit predicate-families-endgame.md or any other End-*.md.
- Subagents unlimited OK; they must not write files — only you write End-B.md.

Fill: plain-language failure, predicates, producers, HEAD proof (file:function), likely code, Reuse/gap vs F*/H*, 1–3 unanswered policy questions, fixture gap, one-line summary, status suggestion.
Reply: IDENTIFY COMPLETE: End-B — <one line>
```

### Chat 3 — End-C

```text
IDENTIFY ONLY — End-C (sidecar; parallel-safe).

Read:
- docs/cross-cutting/predicate-families-endgame.md (Phase 1 + End-C row + constitutional Q for End-C)
- docs/cross-cutting/predicate-families-head.md (Reuse HE as relevant)
- docs/cross-cutting/predicate-families.md (Reuse F4)
- Hint only: ASSETS/executions/exec_11630_d19c15b58ab4_20260915T033341Z/operator/forensics_errors.json

Family: End-C — Glue before EDL

Rules:
- IDENTIFY ONLY — no product/test patches, no runs/forensics, do not mark closed.
- Write ONLY docs/cross-cutting/predicate-families-endgame-identify/End-C.md (fill the template).
- Do NOT edit predicate-families-endgame.md or any other End-*.md.
- Subagents unlimited OK; they must not write files — only you write End-C.md.

Fill: plain-language failure, predicates, producers, HEAD proof (file:function), likely code, Reuse/gap vs F*/H*, 1–3 unanswered policy questions, fixture gap, one-line summary, status suggestion.
Reply: IDENTIFY COMPLETE: End-C — <one line>
```

### Chat 4 — End-D

```text
IDENTIFY ONLY — End-D (sidecar; parallel-safe).

Read:
- docs/cross-cutting/predicate-families-endgame.md (Phase 1 + End-D row + constitutional Q for End-D)
- docs/cross-cutting/predicate-families-head.md (Reuse HX-1..HX-5)
- tests/test_i24_commitment_remaster.py (existing partial)
- Hint only: ASSETS/executions/exec_11630_d19c15b58ab4_20260915T033341Z/operator/forensics_errors.json

Family: End-D — Mix / junction commitment seating

Rules:
- IDENTIFY ONLY — no product/test patches, no runs/forensics, do not mark closed.
- Write ONLY docs/cross-cutting/predicate-families-endgame-identify/End-D.md (fill the template).
- Do NOT edit predicate-families-endgame.md or any other End-*.md.
- Subagents unlimited OK; they must not write files — only you write End-D.md.

Fill: plain-language failure, predicates, producers, HEAD proof (file:function), likely code, Reuse/gap vs F*/H*, 1–3 unanswered policy questions, fixture gap, one-line summary, status suggestion (likely still partial).
Reply: IDENTIFY COMPLETE: End-D — <one line>
```

### Chat 5 — End-E

```text
IDENTIFY ONLY — End-E (sidecar; parallel-safe).

Read:
- docs/cross-cutting/predicate-families-endgame.md (Phase 1 + End-E row + constitutional Q for End-E)
- docs/cross-cutting/predicate-families-head.md (Reuse HM-2, HV-2, HE-2, HS-4, HC-4)
- Hint only: ASSETS/executions/exec_11630_d19c15b58ab4_20260915T033341Z/operator/forensics_errors.json

Family: End-E — Heal / stamp pin discipline

Rules:
- IDENTIFY ONLY — no product/test patches, no runs/forensics, do not mark closed.
- Write ONLY docs/cross-cutting/predicate-families-endgame-identify/End-E.md (fill the template).
- Do NOT edit predicate-families-endgame.md or any other End-*.md.
- Subagents unlimited OK; they must not write files — only you write End-E.md.

Fill: plain-language failure, predicates, producers, HEAD proof (file:function), likely code, Reuse/gap vs F*/H*, 1–3 unanswered policy questions, fixture gap, one-line summary, status suggestion.
Reply: IDENTIFY COMPLETE: End-E — <one line>
```

### Chat 6 — End-F

```text
IDENTIFY ONLY — End-F (sidecar; parallel-safe).

Read:
- docs/cross-cutting/predicate-families-endgame.md (Phase 1 + End-F row + constitutional Q for End-F)
- docs/cross-cutting/predicate-families-head.md (Reuse HPUB / HX as relevant)
- docs/cross-cutting/predicate-families.md (Reuse F6)
- tests/test_i25_pmq_omit_clarity.py (existing partial)
- Hint only: ASSETS/executions/exec_11630_d19c15b58ab4_20260915T033341Z/operator/forensics_errors.json

Family: End-F — Ship score honesty

Rules:
- IDENTIFY ONLY — no product/test patches, no runs/forensics, do not mark closed.
- Write ONLY docs/cross-cutting/predicate-families-endgame-identify/End-F.md (fill the template).
- Do NOT edit predicate-families-endgame.md or any other End-*.md.
- Subagents unlimited OK; they must not write files — only you write End-F.md.

Fill: plain-language failure, predicates, producers, HEAD proof (file:function), likely code, Reuse/gap vs F*/H*, 1–3 unanswered policy questions, fixture gap, one-line summary, status suggestion (likely still partial).
Reply: IDENTIFY COMPLETE: End-F — <one line>
```

### Chat 7 — MERGE (run once after chats 1–6 finish)

```text
MERGE identify sidecars → endgame ledger (identify only; no resolve).

Read all of:
- docs/cross-cutting/predicate-families-endgame-identify/End-A.md
- docs/cross-cutting/predicate-families-endgame-identify/End-B.md
- docs/cross-cutting/predicate-families-endgame-identify/End-C.md
- docs/cross-cutting/predicate-families-endgame-identify/End-D.md
- docs/cross-cutting/predicate-families-endgame-identify/End-E.md
- docs/cross-cutting/predicate-families-endgame-identify/End-F.md
- docs/cross-cutting/predicate-families-endgame.md

Rules:
- Do NOT patch product code or tests. Do NOT start runs. Do NOT mark rows closed (open/partial/superseded only as sidecars suggest).
- You are the ONLY writer of docs/cross-cutting/predicate-families-endgame.md for this turn.
- Fold each sidecar into the matching ledger row: Example predicates, Producer stage(s), HEAD proof, Likely code, Fixture / test notes, Status if suggested, refine constitutional questions if sidecars improved them.
- Tick Identify backlog checkboxes that sidecars completed.
- Leave sidecars in place (do not delete).

Reply with a table: ID | status | one-line | Reuse? | policy Q count
Final line: MERGE COMPLETE — ready for resolve queue End-A → B → D → F → C → E.
```

### Resolve (later — separate chats, one family each, after you answer policy Qs)

```text
RESOLVE — predicate-families endgame.

Read docs/cross-cutting/predicate-families-endgame.md.
Work ONLY the first open/partial ID in queue order (End-A → B → D → F → C → E),
unless I name one: End-A

Rules:
- One family this turn. MUX_FORENSICS=0 fixtures only.
- Ask 1–3 policy questions and WAIT if unanswered.
- Then producer invariant + pytest; update row to closed.
- Reply: COMPLETE: <ID> — <one line>; name next queue ID or QUEUE EMPTY.
```

---

## Status legend

| Status | Meaning |
|--------|---------|
| `open` | HEAD can violate the invariant; needs producer fix + `MUX_FORENSICS=0` fixture |
| `partial` | Campaign / iN patch landed; fixture incomplete, cousin still possible, or policy unset |
| `closed` | Producer invariant fixed + `MUX_FORENSICS=0` fixture green + row updated |
| `superseded` | Covered by an existing F\*/H\* family — do not re-patch here; track only if regression |

---

## Surface → family map (hint: exec_11630 eleven)

| # | Surface failure (forensics) | End-\* | Notes |
|---|-----------------------------|--------|-------|
| 1 | Opening orientation contract thrash (`audible_count=0`) | **End-A** | Omit / optional orientation under freeze |
| 2 | Bridge incompleteness (`seg_049→seg_056`) | **End-C** | Overlaps F4; deferred “count as bridged” policy |
| 3 | G1 / gap VO missing WAV + `seated_bind_stale` | **End-B** | Overlaps F2 / HV-2 |
| 4 | Air-contract ↔ `vo_synthesize` thrash | **End-A** | Overlaps HF-4 / F2 |
| 5 | VO copy / framing / forward-cue under G-Framing | **End-C** | Framing glue quality → EDL |
| 6 | Redundant transitions + seat-freeze sanitize | **End-A** | Freeze mutation legality |
| 7 | EDL narrative / blank interloper (`seg_041`) | **End-A** | Freeze undo vs blank exclude |
| 8 | Chapter absorb / `voice_speaker` stamp drift | **End-E** | Wrong pin / stamp authority mid-delivery |
| 9 | Junction hollow-done / commitment remaster `low_gain` → mix unseated | **End-D** | i24 partial; overlaps HX-2 |
| 10 | PMQ `scorecard_dimension_floors` + `omit_ledger_air_contract` | **End-F** | i25 partial; live clarity inputs |
| 11 | Truncated loudnorm / seed-order thrash (ops) | **End-E** | Heal / remutate pin discipline |

---

## Ledger

Identify fold: sidecars under [`predicate-families-endgame-identify/`](./predicate-families-endgame-identify/) (2026-09-15). One-liners below; full HEAD/fixture detail in each `End-*.md`.

| ID | Family | Invariant (one sentence) | Example predicates | Producer stage(s) | HEAD proof (file:function) | Likely code | Fixture / test | Maps from (surface) | Status |
|----|--------|--------------------------|--------------------|-------------------|----------------------------|-------------|----------------|---------------------|--------|
| **End-A** | Seat / omit / freeze constitution | Under seat freeze, only an explicit allowlist of mutations is legal (omit order-lock rebuild, redundant-transition strip, orientation omit sync); seating / order / gap reseat that expands WAV demand must refuse or pin the owning writer — never thrash EDL. **Ownership constitution:** hard freeze keeps on-air hosted lines only; never `catastrophe_hosted_vo_floor`; unmet floor pins `nugget_layup_compose`. | `HARD: opening orientation contract still failing after one EDL resume`; `opening_orientation_audible_count=0` / `opening_orientation_inaudible`; `air_contract_needs_sanitize:drop_seated_missing_from_gap` (+ `protect_orientation_from_omit`); `air_contract_unsanitary`; `transitions_needs_sanitize:stamp_pair_freeze`; blank interloper vs freeze undo (`seg_041`); `seat_freeze_blocked_*` / `omit_ledger_order_lock_stale`; `hosted_vo_floor_unmet` | `air_contract_sanitize`, `omit_ledger` (heal/revive/order-lock), `transitions`, `edl`, `opening_orientation`, selection commit (`air_order_boundary`), seat meta-gate (`seat_authority` / `run_meta`), `nugget_layup_compose` (floor pin) | `seat_authority.py:HARD_FREEZE_ALLOWLIST_ACTIONS` / `hard_freeze_action_permitted` / `hard_freeze_blocks_action` / `seat_mutation_allowed` (end_a_allowlist; blocks hosted floor catastrophe); `vo_contract.py:ensure_hosted_framing_vo_seats` (keep-on-air; no catastrophe); `artifact_ownership.py` DENY/ALLOW | `seat_authority.py`, `vo_contract.py`, `artifact_ownership.py`, `artifact_sanitize/air_script.py`, `omit_ledger.py`, `air_order_boundary.py` | `tests/test_enda_hard_freeze_constitution.py` + `tests/test_artifact_ownership_constitution.py` (`test_hard_freeze_floor_no_catastrophe`, `test_ensure_hard_freeze_pins_layup`). Sidecar: `End-A.md` | #1, #4, #6, #7 | `closed` |
| **End-B** | Bind / promote authority | Seated synthesize lines have omit ledger + sha-bound WAV; no consumer (EDL glue, gap repair, pending promote) may seat or promote bytes that fail bind — heal pins `vo_synthesize`, never soft-complete EDL | `seated_bind_stale`; `vo_unsanitary`; `gap VO lines missing WAV` / `edl: gap VO lines missing WAV`; `vo_seated_coverage`; `VO coverage not rendered`; `G1 VO pickup missing` / `missing_g1_pickup`; `Synthetic VO script/WAV mismatch`; coverage-ladder | `vo_synthesize` (owner promote/flush), `edl` (consumer refuse), `g1_vo_pickup`, write_staging promote/flush | `write_staging.py:_should_skip_stale_vo_pickup_promote` / `_discard_skipped_stale_vo_pending` / `flush_stage_writes` / `promote_staged_side_effects` / `promote_owner_vo_pickup` / `_commit_stage_writes`; reuse F2 discard + HE-2/HV-2 pins | `write_staging.py`, `vo_bind_authority.py`, `heal_routing.py`, `execution_contract.py` | `tests/test_endb_flush_bind_authority.py` (`test_endb_flush_bypasses_stale_vo_skip`, `test_endb_orphan_commit_skips_stale_vo`, `test_endb_missing_g1_pickup_pins_vo_synthesize_not_edl`); related `test_promote_owner_skips_stale_pending_over_audited_wav`, F2/HV-2/HE-2. Policy recorded below. Sidecar: `End-B.md` | #3 | `closed` |
| **End-C** | Glue before EDL | Every reorder join has durable glue before EDL (`transitions[]` text, destination `placement=before` VO, hitch, or **beyond-pair-freeze** deferred); bare deferred text is not complete; heal never soft-passes EDL without e2e waiver; framing/forward-cue pins layup/compose, never EDL | `bridge_completeness` / `bridge_incomplete` / `HARD: bridge incomplete`; `Reorder seam missing` / ungrounded / stub bridge; `naked_seam` / `seam_mint_reorder`; `edl_narrative:vo_g1`; `missing_forward_cue` / framing-before-impact QC; deferred text-as-bridged (seg_049→seg_056) | `transitions`, `seam_glue` / `ensure_seam_glue`, `gap_framing_compose`, `nugget_layup_compose`, `vo_synthesize`, `edl` (consumer), driver bridge-heal / `seam_mint_reorder` | `bridge_completeness.py:deferred_pair_is_durable` / `bridge_heal_may_soft_complete` / `_bridged_pairs` (deferred durable-only); `artifact_sanitize/transitions.py` stamps `beyond_pair_freeze`; `heal_routing.py:classify_heal_error` (bridge→`transitions`, framing→layup/compose); `stage_completion.py:PRODUCER_PIN_TABLE`; `edl_narrative_qc.py:_validate_framing_before_impact`; `tools/full_auto_driver.py` bridge-heal refuse soft without waiver | `bridge_completeness.py`, `artifact_sanitize/transitions.py`, `heal_routing.py`, `stage_completion.py`, `tools/full_auto_driver.py`, `edl_narrative_qc.py` | `tests/test_endc_glue_before_edl.py` (`test_endc_deferred_text_only_not_complete`, `test_endc_beyond_freeze_deferred_is_durable`, `test_endc_vo_before_target_still_covers_seam`, `test_endc_soft_complete_refused_without_waiver`, `test_endc_bridge_incomplete_pins_transitions_not_edl`, `test_endc_framing_quality_pins_compose_or_layup_never_edl`); related F4 + flipped `test_deferred_spoken_pair_covers_reorder_bridge`. Policy recorded below. Sidecar: `End-C.md` | #2, #5 | `closed` |
| **End-D** | Mix / junction commitment seating | `.stage_done/mix` and junction commitment require seated assembly (`mix_outputs_seated` + generation match); **commitment** remaster must not refuse as `low_gain`; hollow `junction_snip_qa` done must refuse so `master_finalize` cannot skip | `commitment_remaster_refused` / `junction_commitment_remaster_refused` / `junction_commitment_remaster_failed`; `low_gain`; `mix_unseated` / `mix_outputs_seated` / `assembly_seating_stale`; `mix_seat` / `premature_complete:mix_seat`; `seed order: complete junction_snip_qa before master_finalize`; hollow junction; `junction_commitment_mismatch` | `junction_snip_qa`, `mix`, `master_finalize` | `junction_snip_qa.py:_budgeted_remaster_mix` (commitment bypasses low_gain + budget/osc); `stage_completion.py:_junction_commitment_incompleteness`; `homunculus/agenda.py:stage_outputs_present` (junction requires commitment match); `air_order.py:mix_outputs_seated` / `ensure_assembly_mtime_seats_edl` | `junction_snip_qa.py`, `stage_completion.py`, `homunculus/agenda.py`, `air_order.py` | `tests/test_endd_commitment_seating.py` (`test_endd_commitment_bypasses_budget_and_low_gain`, `test_endd_hollow_junction_not_seed_complete`, `test_endd_committed_junction_is_seed_complete`, `test_endd_hollow_done_refuses_seed_complete_for_finalize`); related i24 + HX-2. Policy recorded below. Sidecar: `End-D.md` | #9 | `closed` |
| **End-E** | Heal / stamp pin discipline | Seed-order / incompleteness resumes the **named** producer (never sealed `edl`/`mix`/`master_finalize` by default); empty pin **refuses execute** (no delivery rewind / no `music_palette_compose` coalesce); chapter absorb stamps selection via `full_master_ranking`, voice stamp via `vo_synthesize` (not `edl`); `master_finalize` mark/restamp requires committed master integrity | `seed_order_prereq`; `seed order: complete <producer> before <consumer>`; wrong-producer heal; empty heal pin; chapter continuity absorb; `missing voice_speaker_id`; truncated loudnorm / pending `master.wav` | heal routing / `heal_navigate`; `artifact_ownership.heal_pin_for`; `stage_completion` pin table; driver `_heal_resume`; `master_finalize` / loudnorm | `artifact_ownership.py:heal_pin_for` / `assert_execute_from_stage`; `stage_completion.py:producer_pin_for_token` (default `""`); `tools/full_auto_driver.py:_heal_resume` (refuse empty / refuse music coalesce); `delivery_invariants.py:parse_seed_order_producer` | `artifact_ownership.py`, `stage_completion.py`, `thrash_hardening.py`, `tools/full_auto_driver.py` | `tests/test_ende_heal_stamp_pin.py` + `tests/test_artifact_ownership_constitution.py` (`test_heal_pin_no_sealed_default`, `test_empty_execute_from_stage_refused_mid_pipeline`). Sidecar: `End-E.md` | #8, #11 | `closed` |
| **End-F** | Ship score honesty | PMQ clarity reflects **live unresolved** `_pack_conflicts` (applied leftovers ignored); every clarity-reading path refreshes autopsy; scorecard floors stay NORTH_STAR rubric (aspirational); omit air-contract remains structural; no e2e soft greenwash | `scorecard_dimension_floors` (clarity ← live pack overlay); `scorecard_overall_floor`; `omit_ledger_air_contract` / `omit_ledger_order_lock_stale`; `post-master quality failed: scorecard_dimension_floors, omit_ledger_air_contract` | `master_finalize`, `post_master_quality`, `omit_ledger`, `seam_autopsy` / `junction_snip_qa` (clarity upstream) | `post_master_quality.py:refresh_live_post_master_autopsy` / `build_listener_scorecard` (live `_pack_conflicts` overlay) / `require_publishable` (refresh then re-eval); `run_post_master_quality` (rebuilds autopsy); `omit_ledger.py:heal_omit_ledger_air_contract` (i25 order-lock under freeze); `seam_autopsy.py:_pack_conflicts` (unresolved-only); `aspirational_quality.py` — omit structural, scorecard rubric | `post_master_quality.py`, `omit_ledger.py`, `seam_autopsy.py`, `stages/mastering.py`, `aspirational_quality.py`, `quality_status.py` (F6 envelope only) | `tests/test_endf_pmq_score_honesty.py` (`test_endf_applied_leftovers_do_not_tank_clarity_scorecard`, `test_endf_unresolved_pack_conflicts_lower_live_clarity`, `test_endf_scorecard_floors_reflect_live_clarity`, `test_endf_omit_heal_then_pmq_omit_contract_passes`, `test_endf_require_publishable_refreshes_before_reeval`). Related: i25 + F6 / HPUB-1. Policy recorded below. Sidecar: `End-F.md` | #10 | `closed` |

---

## Constitutional questions (ask at resolve time)

Fill answers into the row **Invariant** / notes when resolving; do not invent policy in identify. Sidecar refinements (1–3 each):

| ID | Ask the operator |
|----|------------------|
| **End-A** | **Decided (resolve):** (1) Legal under hard freeze: omit order-lock rebuild; `drop_seated_missing_from_gap`; orientation omit sync (`protect_orientation_from_omit` / revive / `stamp_gap_omit_flags`); blank drop via `_drop_blank_segments_under_freeze`; transition strip (`stamp_pair_freeze` / `trim_pair_freeze` / `framing_dedupe`); clamp shrink. **Illegal:** `protect_hosted_vo_floor_reseat` (WAV-expanding reseat). (2) When `opening_orientation.required=true`, revive is allowlisted without meta-gate (omit must not keep fighting the orientation id). (3) Transition strip/stamp/trim/dedupe stay legal under hard seat freeze. |
| **End-B** | **Decided (resolve):** (1) Stale bind + newer pending → keep sha-bound dest; promote pending only if it matches audit sha; otherwise discard pending and leave heal to resynth/omit (never blind promote). (2) Skipped stale pending is **deleted** so flush/orphan cannot re-promote. (3) Every owner flush path (`flush_stage_writes`, orphan `_commit_stage_writes`→approve→flush, `promote_staged_side_effects`) shares the same bind skip. |
| **End-C** | **Decided (resolve):** (1) Deferred text is temporary — durable only with WAV / omit / hitch / **beyond-pair-freeze** stamp (mix last-chance); bare deferred text does not complete bridges. Durable mint stays in `transitions[]` (F4). (2) Destination-only `placement=before` VO (`vo_before_targets`) remains valid one-host-turn glue. (3) Framing / forward-cue quality pins `nugget_layup_compose` when layup owns, else `gap_framing_compose` — never EDL; bridge incomplete pins `transitions`; driver soft-complete / outer→EDL only under e2e quality waivers. |
| **End-D** | **Decided (resolve):** (1) Commitment remaster always bypasses low_gain; cosmetic/feel still subject to timeline-reopen. (2) Commitment also bypasses remaster **budget/oscillation** (still remasters to reseat; real remaster failure loud-fails). (3) `stage_artifact_incompleteness` / `stage_outputs_present` for `junction_snip_qa` require `_junction_commitment_matches_assembly` — autopsy/QA files alone cannot seed-complete finalize. |
| **End-E** | **Decided (resolve):** (1) Resume map: parse named seed-order producer in `producer_pin_for_token` + `heal_navigate` **and** fix driver stamp `stage_key`s — table alone is not enough. (2) Chapter absorb stamps selection as `full_master_ranking`; missing `voice_speaker_id` stamps gap as `vo_synthesize` (never `edl` writer); resume-`edl` remains legal as **consumer rebuild** after those producer stamps. (3) Hollow/truncated/pending `master.wav` → unmark+rerun `master_finalize` (never restamp); integrity size floor required before `mark_done` / live authority. Mix with seated assembly may still restamp+resume consumer. |
| **End-F** | **Decided (resolve):** (1) Clarity / pack conflicts stay **unresolved-only** forever — applied leftovers never tank scorecard clarity (no soft-advisory count). (2) `scorecard_dimension_floors` / overall stay **aspirational/rubric** (NORTH_STAR listen-delight); `omit_ledger_air_contract` stays structural. (3) Every clarity-reading path refreshes live autopsy (`refresh_live_post_master_autopsy` + live `_pack_conflicts` overlay in `build_listener_scorecard`); `require_publishable` refresh-then-reeval — finalize-only is not enough. |

---

## Closeout rule

Flip `Status` → `closed` only when all are true:

1. Producer-side invariant in product code (not forensics waiver / `MUX_FORENSICS` heal).
2. Fixture pytest under `tests/` with **`MUX_FORENSICS=0`** asserting predicate flip / dirty `stage_done` refused / correct heal pin.
3. Ledger row updated with fixture path + test node id(s).

**Tape acceptance (after QUEUE EMPTY):** ≥1 plain Mohan full-auto (`MUX_FORENSICS` unset) ship bar green without End-A…F heals. Prefer 2× when changing freeze/bind constitutions.

---

## Post-End residual track (no End-G)

End-A…F stay **closed**. Further ownership / soft-pass / GUI / promote / hollow / heal-flush work lives in the residual campaign plan (`residual_still-likely_fixes`), **not** a seventh seal family. Cousin fixtures under `tests/test_end_cousin_fixtures.py` and constitution modules must not reopen ledger rows.

## Identify backlog (next pass)

- [x] Walk HEAD for End-A allowlist vs actual freeze gates; cite `file:function`
- [x] Diff End-B cousins against F2 / HV-2 / HE-2 fixtures; mark `superseded` or keep `open` with gap named → owner flush/orphan closed under promote_pending constitution
- [x] Diff End-C against F4; document deferred-bridged policy hole
- [x] End-D: list remaining cousins beyond i24 (e.g. premature mix lease vs commitment)
- [x] End-E: inventory residual tokens that still pin `edl` / `mix` / `master_finalize`
- [x] End-F: confirm live `_pack_conflicts` + omit rebuild cover all PMQ clarity paths used at finalize → **closed** (`test_endf_pmq_score_honesty.py` + i25)
