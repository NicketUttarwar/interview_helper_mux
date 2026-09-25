# High-risk stage audit — framing_posture_decide

tier: T3 | seed: #17 | runs_hit: 9/9  
status: `complete`  
mode: investigate  
updated: 2026-09-25T18:17:38Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

### What this stage does

Happy path (homunculus 0.1.0+, feature on, hosted / gap-eligible tape): pack brief + topology + volley stats + eligibility → one advisory LLM call (`framing/framing-posture-decide.system.txt`) → persist `understanding/framing_posture_decision.json` (`decided_by=llm_advisory`, `advisory_only=true`) → `apply_host_gate` (no-op unless deterministic `native_only`) → analysis mark done via `run_analysis_llm_stage`.

Short-circuits: non-homunculus / feature-disabled → schema-complete **allow stub** (`recommended_framing=yes`, does **not** skip gap fill) + force mark. True monologue (`assess_gap_fill_eligibility` + `silent_skip_allowed`) → deterministic `native_only` decision + host-enforce gap-fill skip + mark.

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (soft) | `understanding/content_brief.json`, `speakers.json`, topology/adaptation, `segments/manifest.json`, optional ideal_cuts + comprehension risks | Contract soft inputs; LLM packet also attaches spine / conversation_context |
| Writes (SSOT) | `understanding/framing_posture_decision.json` | Sole ownership ALLOW row |
| Soft / side | `understanding/gap_fill_skip.json` (+ gap skip stubs via `ensure_gap_fill_skipped`) | Only when host-enforce fires on deterministic `native_only` |

### Rules that govern it

- **Admit** — brain has homunculus features + `analysis.framing_posture.enabled`; else stub
- **Refuse** — N/A as product refuse; seed-order may block *before* entry when earlier analysis incomplete
- **Incomplete** — schema sufficiency: non-empty `recommended_framing` + `posture_hint`
- **Heal** — stub/monologue paths use `heal_or_refuse_mark(..., force=True)`; no soft re-admit of gap membership
- **Wait_for_gate** — does not clear G-Framing; advisory feeds gate UI / Full-auto recommend
- **Done / hollow honesty** — stub always writes schema-complete decision so seed/delivery can proceed (HU-2)
- **Hard floors / QC** — LLM ≤2 via analysis LLM stage; host_enforce: LLM alone cannot force `native_only` skip (2M)
- **Freeze / ownership** — owns only `framing_posture_decision.json`; operator G-Framing remains authoritative binary

### Considerations & load-bearing policy

- **G-Framing** is the real switch; this stage recommends `yes` / `no` / `sparse` for UI / `recommended_framing_action`.
- Full-auto may auto-resolve hosted topologies to Yes **unless** posture said `no`/`sparse` or stub/homunculus_skip (HU-2: stub does not auto_resolve).
- Monologue host gate is the only path that skips the gap stack early; hosted LLM `native_only` hint is ignored for skip.
- Depends on `content_brief` existing (pipeline order: after `content_brief_reanchor`). Homunculus seed-order noise when `content_context` / brief incomplete is **agenda**, not stage logic bloat.

### LLM / external calls

Prompt: `docs/prompts/framing/framing-posture-decide.system.txt` · ≤2 attempts via `run_analysis_llm_stage` · hollow = missing/invalid decision fields. Skipped entirely on stub / monologue paths.

### What it deliberately does *not* do

- Override operator G-Framing Yes/No
- Compose interviewer lines / gap_report body / selection membership
- Skip gap fill from LLM advisory alone
- Re-run or heal `content_context` when seed-order blocks

### Operator-visible effects

- G-Framing gate rationale / recommend action from `recommended_framing` + `rationale_plain`
- Full-auto: monologue → silent gap skip; hosted stub → gate still presented
- Forensics: often listed as `seed_order_prereq` vs `content_context` when agenda races ahead (T3)

---

## 1. Job statement

Emit one advisory framing-posture decision (or allow-stub / deterministic monologue skip) so G-Framing and later gap stages know whether synthetic host VO is recommended — without owning the operator gate.

---

## 2. Error-hint intake

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `seed_order_prereq` / `complete content_context before running framing_posture_decide` | `seed_order_noise` | Confirmed on exec_13198 forensics (5 hits); earliest incomplete seed stage is `content_context`, not a posture bug |
| `RuntimeError: seed order: complete content_context…` | `seed_order_noise` | Same class; recovery walks earlier analysis |
| Hollow / missing `framing_posture_decision.json` pending | `downstream_of_content_context` (when brief gone) / normal pending | HU-2 stubs avoid pinning later stages on missing advisory |

Report why-high-risk: Seed-order vs `content_context` (homunculus)

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `src/interview_mux/stages/framing_posture_decide.py` (~70 LOC) |
| Key helpers | `src/interview_mux/framing_posture.py` — input pack, stub/monologue builders, persist, `apply_host_gate`, `should_run_framing_posture_llm` |
| Primary writes | `understanding/framing_posture_decision.json` via `write_validated_artifact` |
| Freeze / ownership | `artifact_ownership.py` ALLOW sole producer; contract YAML consumers: missing_framing, gap_framing_compose, transitions, vo_synthesize |
| G-Framing consumer | `homunculus/gates.py` `recommended_framing_action` |
| Tests (non local-ML) | `tests/test_framing_posture_decide.py`, `tests/test_hu2_framing_posture_stub.py` (+ parity / registry) |

---

## 4. Business-logic walk

1. **Brain / feature gate** — `has_homunculus_features` false or `framing_posture_enabled` false → `build_allow_stub_decision` → persist → `heal_or_refuse_mark(force=True)`. Gap fill **not** skipped.
2. **Monologue skip** — `should_run_framing_posture_llm` false when ineligible + `silent_skip_allowed` → `build_monologue_decision` (`no` / `native_only`) → `apply_host_gate` → `ensure_gap_fill_skipped` → mark done. No LLM.
3. **LLM path** — `build_framing_posture_input` (brief, volley_stats, exclusion hints, topology, eligibility, optional risks/spine) → `run_analysis_llm_stage` persist with `llm_advisory` → `apply_host_gate` (ignores LLM `native_only` unless decided_by ∈ {deterministic_monologue, operator_g_framing, forced_skip}).
4. **Done honesty** — stubs always schema-valid; advisory_only true only for LLM path.
5. **Seed-order** — `_seed_prereq_block` / earliest incomplete in ANALYSIS_ORDER can refuse entry until `content_context` (and prior) complete — explains 9/9 T3 hits without stage thrash.

---

## 5. Over-engineering scorecard

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **2** | (1) Persist advisory/stub/monologue decision; (2) host-enforce gap skip only on deterministic `native_only` |
| Dual / competing SSOTs | **no** | Single decision artifact; G-Framing is separate authoritative gate, not a second writer of the same file |
| Soft-heal / thrash re-admit loops | **no** | No selection/gap re-admit; force mark on stubs only |
| Co-producer / unpaid land | **no** | Gap skip via shared `ensure_gap_fill_skipped` is intentional monologue product path, not thrash land |
| Brittle predicates vs simple rules | **no** | Eligibility + silent_skip; seed-order errors are agenda, not in-stage predicates |
| Disproportionate shard/memo/resume | **no** | Standard analysis LLM stage; ~335 LOC total module+stage; no shard resume |
| “Fix everything downstream” behavior | **no** | Advisory-only; does not heal content_context or rewrite gap_report for hosted tapes |

**Over-engineered?** `no` — one product job + a narrow monologue host gate; report risk is seed-order noise, not stage bloat.

**Scorecard verdict:** `PASS`

- Would only flip to FAIL if host-gate gap co-writes grew into unpaid thrash or a second SSOT for framing consent.

### 5b — Re-score after changes (MODE=fix / MODE=rescore only)

_(not applicable — investigate only)_

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| — | — | — | — | No open cuts; scorecard PASS → leave/monitor | — | — |

Optional backlog (not required for PASS): if seed-order spam becomes operator-painful, harden agenda brief-restore / heal that archives `content_brief` — **outside this stage**.

---

## 7. Root-cause verdict

**Not over-engineered.** Corpus “high risk” is **homunculus seed-order friction**: agenda attempts `framing_posture_decide` while `content_context` (shared brief path) is still incomplete or unmarked after heals. Stage body is a thin advisory LLM with honest stubs and a locked 2M host gate. Product poison for framing/VO lives in later T0 stages (`missing_framing`, layup, etc.), not here.

---

## 8. Recommended next action

`leave`

---

## 9. Scope fence

Upstream poison owner (if any): `content_context` / brief heal-archive (seed-order), not this stage’s logic  
Downstream victims (names only): G-Framing recommend path, `missing_framing`, `gap_framing_compose` (consumers of advisory)  
Did **not** redesign other stages.
