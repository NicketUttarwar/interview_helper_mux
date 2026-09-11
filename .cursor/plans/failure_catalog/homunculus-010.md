# Homunculus 0.1.0 — conductor / tools / dispatch

Identify-only. HEAD.

## Architecture (HEAD)

| Piece | Path |
|-------|------|
| Conductor prompt | `docs/prompts/homunculus/conductor/system.txt` (+ mlx variant) |
| Loop gateway | `homunculus/loop.py` — `nested_chat_create`, tool loop |
| Packer | `homunculus/packer.py` — `apply_pack_to_kwargs` (tape facts; G0 lock) |
| Registry | `homunculus/registry.py` — `stage_tool_specs` → `run_stage_<id>`, host tools, prompts |
| Runtime | `homunculus/runtime.py` — `dispatch_stage`, seed prereq blocks |
| Agenda | `homunculus/agenda.py` — walk, invalidate, ship_path, remaining |
| Budget | `homunculus/budget.py` — LimitExhausted → `limit_exhausted.json` |
| Version | `run_meta.homunculus_version` locked at start |

---

### H010-LOOP-01 — nested_chat_create always packs; budget counting subtle

- Surface: homunculus-tool / LLM
- Modes: all (when 0.1.0)
- Call graph: stage LLM → `nested_chat_create` → `apply_pack_to_kwargs` → OpenAI create; ledger admit
- Invariant: packets packed facts only; schema retries don't double-count identity
- Why weak: open_stage detection via ledger start/close counts can desync if ledger rows corrupt; CTA cover budget exempt path skips some checks
- Likelihood: L2 | Severity: S3
- Evidence: `homunculus/loop.py:nested_chat_create`
- Fix-cluster: `homunculus-budget-ledger`
- Status: OPEN_RISK

### H010-LOOP-02 — LimitExhausted blocks ship

- Surface: homunculus
- Modes: Full-auto | Partial | Manual
- Call graph: `check_dispatch` / audio serialize → LimitExhausted → `mastering/homunculus/limit_exhausted.json`
- Invariant: ship blocked when limit exhausted
- Why weak: operator may not see clear CTA to raise budget vs wrong from-stage; Manual confusion
- Likelihood: L2 | Severity: S3
- Evidence: `homunculus/budget.py`, mastering-homunculus.md
- Fix-cluster: `homunculus-budget-ledger`
- Status: LIKELY_MITIGATED_ON_HEAD

### H010-DISPATCH-01 — dispatch_stage seed prereq vs conductor reorder

- Surface: homunculus
- Modes: all
- Call graph: conductor tool `run_stage_*` → `dispatch_stage` → `_seed_prereq_block` / music epoch / VO stability
- Invariant: conductor cannot run consumer before producer seed-complete
- Why weak: if prereq block and conductor disagree, thrash or skip; hollow skip blocked in agenda but tool path must match
- Likelihood: L2 | Severity: S4
- Evidence: `homunculus/runtime.py:dispatch_stage`, `agenda.py`
- Fix-cluster: `homunculus-dispatch-prereq`
- Status: OPEN_RISK

### H010-TOOL-01 — run_stage tools for every pipeline stage

- Surface: homunculus-tool
- Modes: all
- Call graph: `registry.stage_tool_specs` builds `run_stage_{stage}` for order stages
- Invariant: every ANALYSIS+DELIVERY stage has a tool
- Why weak: stub stages / alias stages (e.g. synthetic_framing_plan in ALL_LLM but not always in DELIVERY_ORDER) may confuse conductor
- Likelihood: L2 | Severity: S2
- Evidence: `homunculus/registry.py:stage_tool_specs`; ALL_LLM includes `synthetic_framing_plan`, `connector_seam_adjudicate` not in DELIVERY_ORDER
- Fix-cluster: `homunculus-tool-surface`
- Status: OPEN_RISK

### H010-GATE-01 — 0.1.0 gate controller vs G0 human

- Surface: gate / homunculus
- Modes: Manual | Full-auto | Partial
- Call graph: operator_gates / gate_decisions.json; G0 still human when open
- Invariant: needs_operator only for journey gates (G0, voice-ref, unlock, G-Publish) on unattended — not VO coverage
- Why weak: Manual still sees VO coverage banners; mismatch between docs and GUI NEEDS YOU can train wrong clicks
- Likelihood: L2 | Severity: S1
- Evidence: mastering-homunculus.md; `operator_gates.py`
- Fix-cluster: `gate-banner-honesty`
- Status: OPEN_RISK

### H010-RERUN-01 — rerun_stage / surgical re-run vs epoch lock

- Surface: homunculus-tool
- Modes: all
- Call graph: `rerun_stage` tool → invalidation → G-DeliveryUnlock if structural under lock
- Invariant: structural rerun blocked until unlock when delivery_epoch.locked
- Why weak: heal-only misclassified as structural (or reverse) → stuck or wipe
- Likelihood: L2 | Severity: S3
- Evidence: `registry.py` rerun_stage; delivery unlock API
- Fix-cluster: `invalidation-blast`
- Status: OPEN_RISK
