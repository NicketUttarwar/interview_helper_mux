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
