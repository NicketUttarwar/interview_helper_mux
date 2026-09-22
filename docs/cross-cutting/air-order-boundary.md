# Air order boundary bus

Federated contract for **`master/selection.json`** air order: stages keep autonomous domain logic; the boundary bus validates tape-time physics, checkpoints at handoffs, and notifies downstream when order changes.

**Code:** [`src/interview_mux/air_order_boundary.py`](../../src/interview_mux/air_order_boundary.py) · [`src/interview_mux/air_order_integrity.py`](../../src/interview_mux/air_order_integrity.py)

---

## Constitution (shared invariants)

1. **Tape monotonicity** — adjacent air pairs must not reverse source `start_ms` beyond `reverse_jump_margin_ms`, except pairs declared in `understanding/reorder_bridges.json`.
2. **Opening sub-rule** — host-intro letter-split families (`seg_001*`) air early together as **one opening family** for slot budgeting; violations key on parent first-air index, not each fragment. Typed-exclude (`opening_skipped_duplicate`) when guest-first open is established — never mid-episode.
3. **Consumer parity** — EDL speech clip order must match selection when EDL is done (`assert_selection_leads_edl`).
4. **NLE overlay exception** — when the operator applied NLE timeline edits, intentional non-monotonic tape order is **allowed**. Checkpoints **warn** in `master/air_order_integrity.json`; they do **not** block commit.

---

## Three pillars

| Pillar | Role |
|--------|------|
| **Constitution** | Detector/reporter in `air_order_integrity.py` |
| **Checkpoints** | `checkpoint_air_order()` after domain logic, before persist |
| **Lifecycle** | `commit_selection_mutation()` — write + invalidate stale transitions/EDL when `ordered_segment_ids` changes |

Stages decide editorial content. The bus only asks: *Is this order physically valid on tape, and did consumers get notified?*

---

## Boundary map

| ID | Producer | Checkpoint mode (rollout) | Notes |
|----|----------|---------------------------|-------|
| B1 | `full_master_ranking` | `repair` → block if criticals remain | Ranking persist via `commit_selection_mutation` |
| B2 | `order_reconcile` | `repair` | Revert LLM order on critical when flagship |
| B3 | `transitions` | `repair` + prerepair | Opening adjacency + integrity audit |
| B4 | `transitions` commit | lint + integrity | Transitions artifact write |
| B5 | `edl_narrative_remutate` | **`detect` only** | Lifecycle on selection repair |
| B6 | `junction_snip_qa` | **`detect` only** | Lifecycle on micro-exclude |
| B7 | `air_order` | **`detect` only** | Sealed generation commit |
| B8 | `post_master_quality` | audit backstop | Publish gate |

---

## Lifecycle

`commit_selection_mutation()` is the sole selection persist API (checkpoint → write →
`on_selection_order_changed`). Hot JSON also routes through
[`artifact_sanitize/one_writer.py`](../../src/interview_mux/artifact_sanitize/one_writer.py)
when callers use `write_json` / `write_committed_json`.

---

## Rollout (warn-first)

Default **`mastering.air_order_integrity.block_ranking_on_critical: false`** during soak.

- Phase C: lifecycle gaps (B5–B7) — log + invalidate, no new halted runs.
- After soak: set `block_ranking_on_critical: true` for B1–B4.

**Blocking rule:** block only when **critical violations remain after repair**. If repair fixed the order, commit proceeds.

---

## Operator troubleshooting

| Symptom | Check |
|---------|--------|
| Run blocked at ranking | `master/air_order_integrity.json` · `resolved_policy` · `operator/air_order_integrity.log.jsonl` |
| Stale transition bridge | Order changed without lifecycle — grep for raw `master/selection.json` writes |
| Montage episode flagged | Ensure pair is in `understanding/reorder_bridges.json` |
| NLE timeline reorder | Expected — integrity warns, does not block |

**Audit:** `python tools/audit_air_order_integrity.py [--execution-id …]`

**CI:** `./tools/check_selection_write_paths.sh`

---

## What stays decentralized

Ranking LLM choices, hard-keep/topo, CTA, transitions copy, finale-tail / 051-signoff / late-intro / post-coda specialist repairs — unchanged internally. The constitution catches **gaps between** specialists (e.g. exec_188 mid-arc intro replay).

---

## VO seat freeze (Pillar B)

Seat/omit fingerprint lives under `run_meta.delivery_epoch.vo_seats_freeze` (`seat_authority.py`):

| Stamp | When |
|-------|------|
| **soft** | After successful `air_contract_sanitize` |
| **hard** | After `vo_synthesize` + seated WAV parity |

After soft freeze, writers that would change the seat fingerprint must **no-op**, take an **operator unlock** (G1 / gap CRUD), or pass the **seat rewrite meta-gate**. `unlock_delivery_epoch(..., unlock_seats=False)` leaves seats frozen by default.

**End-A only (G-4 / H-3):** under soft or hard freeze, gap / selection / SDP / transitions persist only via `HARD_FREEZE_ALLOWLIST_ACTIONS` (or one-shot / `request_seat_rewrite`). Ship-blocking omit is **not** a second constitution — freeze restores order until unlock; mix may refuse `incomplete_cut_unresolved`. Direct persist uses `persist_frozen_seat_doc` (End-A or skip-write).

Holistic review (`holistic_seat_review`) gates `transitions` / `vo_line_adjudicate` / `edl` inputs and pins resume to `air_contract_sanitize` (not Pass B remutate).

See also: [`execution-status.md`](execution-status.md) · `mastering/seat_rewrite_gate.jsonl` · `mastering/timeline_reopen_gate.jsonl`.

## Selection constraint lattice

Total order at ranking / `commit_selection_mutation` (via [`selection_constraints.apply_selection_constraints`](../../src/interview_mux/selection_constraints.py)):

1. Unplayable / blank / zero-ms — cannot hard-keep or never-exclude
2. CTA / never-touch packaging
3. Seat / epoch freeze (commit gate)
4. `never_exclude_primary_impact` — playable non-CTA only
5. Hard-keep restore
6. Framing VO-cover excludes (selection_framing_apply)

Specialists remain in `hard_keep.py` / `framing_coverage_guard.py` / `media_ip_cta.py`; the lattice is the single post-pass arbiter.

## Seed policy (freeze sticky)

[`seed_policy.py`](../../src/interview_mux/seed_policy.py): under hard seat freeze + EDL done, `selection_framing_apply` and `gap_framing_recompose` are sticky-complete (force-mark) and must not raise `seed_order_prereq`. Epoch fingerprints live under `run_meta.delivery_epoch` (including `junction_residuals_generation`).
