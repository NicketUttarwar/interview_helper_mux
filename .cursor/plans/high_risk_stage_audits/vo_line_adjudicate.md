# High-risk stage audit — vo_line_adjudicate

tier: T1 | seed: #54 | runs_hit: 5/9  
status: `complete`  
mode: fix  
updated: 2026-09-25T18:10:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> Write this before anything else. Also open the chat with a short spoken summary of what this stage does, its main rules, and key considerations so a human can orient cold.

### What this stage does

Happy path (homunculus ≥0.1.0 + `adjudicate_before_synth=true`): read seated synthesize VO from `understanding/gap_report.json` + layup plan → deterministically pick body lines that need a second pass (flow pre-score + input-hash skip) → batched economy LLM adjudicate → seal **advisory** `understanding/vo_line_adjudication.json` (null-coerced) → read-only coverage warn + speakable gate on **disk** gap → Full-auto record→synth stamp rewrite (ALLOW) → `heal_or_refuse_mark`.

Does **not** rewrite gap body text, mint intro, or write allocation (S1–S3). Stamp-only omit skips remain ALLOW.

When the flag is off, or gap_report is missing, persist a schema-valid **skip stub** adjudication artifact and heal.

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `understanding/nugget_layup_plan.json`, `understanding/gap_report.json` | Contract hard inputs |
| Reads (soft) | corpus, omit_ledger, masks, content_brief | Flow / waive / packet |
| Writes (SSOT) | `understanding/vo_line_adjudication.json` | Sole product after S1–S3 |
| Stamp co-write | `understanding/gap_report.json` | Omit/delivery/targets ALLOW only — not body |
| Helpers (not stage) | `run_intro_compose`, `persist_allocation_plan` | Dead on stage path; backlog delete/relocate |

### Rules that govern it

- **Admit** — homunculus features on; `adjudicate_before_synth`; gap_report present
- **Refuse / loud** — `synthesize_vo_incomprehensible` on **disk** gap (empty/thin/scaffold/placeholder); optional loud on coverage when `adjudicate_fail_open=false`
- **Incomplete** — hosted floor `HOLLOW_ZERO` via `_heal_adjudicate_mark`; hollow mark_done refused if primary missing
- **Heal** — null→string seal on adjudication rows; skip stubs when no LLM work
- **Wait_for_gate** — none owned (G1 is adjacent on synth)
- **Done / hollow honesty** — batches run with `auto_complete=False`; seal primary only after all batches
- **Hard floors / QC bars** — speakable VO always (read-only); nugget air coverage fail-open by default
- **Freeze / ownership** — DENY unmark of live VO/WAVs; S9 layup sole body writer; stage does not attempt unpaid body lands

### Considerations & load-bearing policy

- **S9 honored:** adjudication is advisory; layup owns body copy. Intro coverage recovery is deferred upstream (not relocated yet).
- **Hosted VO floor** identified here but owned upstream.
- **Full-auto** record→synth delivery stamp owns on this stage (upstream of `vo_synthesize`).

### LLM / external calls

- Prompt: `docs/prompts/vo/vo-line-adjudicate.system.txt` via `run_flow_llm_stage` (batched; `auto_complete=False`)
- Intro helper exists but is **not** invoked from the stage
- ≤2 attempts per stage invoke
- Hollow meaning: mid-batch mark_done without sealed adjudication; empty skip without stub; `final_text: null` without `_seal_adjudication_row`

### What it deliberately does *not* do

- Does not mint VO WAVs (`vo_synthesize`)
- Does not mutate gap body text / mint episode_preface / write allocation
- Does not own selection / EDL / mix
- Does not clear G1 / handle operator pickup

### Operator-visible effects

- Blocks `vo_synthesize` until complete (seed-order + invalidates list)
- LoudStageFailure only on disk speakable failures (layup poison), not unpaid intro mint
- Skip stub when brain 0.0.0 or flag off

---

## 1. Job statement

Second-pass per-line VO adjudication log so `vo_synthesize` has an advisory decision artifact — without co-producing gap_report body copy.

---

## 2. Error-hint intake

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| schema `final_text: None` | `healed` | `_seal_adjudication_row` |
| hollow mark_done (mid-batch) | `healed` | `auto_complete=False` |
| spoken scaffolding on intro mint | `healed` (this stage) | S2 peeled intro from stage; remaining scaffold = layup disk poison |
| bad `nugget_intro_compose` schema | `downstream_of_X` / peeled | Helper remains; stage does not call |
| seed-order prereq for synth | `seed_order_noise` | Expected |

Report why-high-risk: Schema/hollow done; spoken scaffolding refusals

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `stages/vo_line_adjudicate.py::run_vo_line_adjudicate` (+ Full-auto stamp rewrite) |
| Core stage | `vo_line_adjudicate.py::run_vo_line_adjudicate_stage` |
| Need / flow / hash | `lines_needing_adjudication` |
| Batches + seal | `run_adjudicate_batches`, `_seal_adjudication_row` |
| Advisory trace | `apply_adjudicate_results` (no gap mutate / no WAV nuke) |
| Done | `_heal_adjudicate_mark` |
| Contract | `docs/cross-cutting/stage-contracts/vo_line_adjudicate.yaml` (primary only) |
| Tests | `tests/test_vo_line_adjudicate.py`, `tests/test_hv3_adjudicate_hollow_done.py` (27 passed @ rescore) |

---

## 4. Business-logic walk

**Skip paths:** no homunculus → force heal; flag off / no gap → skip stub + heal.

**Part A (advisory):** body synthesize lines → `lines_needing_adjudication` (hash match skip; else flow &lt; threshold) → batches seal adjudication.json → advisory `apply_adjudicate_results` (trace only).

**Peeled:** intro mint, allocation persist, gap body rewrite, scrub-land.

**Post:** re-read disk gap → coverage evaluate (fail-open warn) → speakable LoudStageFailure if disk VO junk → ensure adjudication artifact → Full-auto delivery stamp → heal.

---

## 5. Over-engineering scorecard

### 5a — Baseline (pre S1–S5)

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **5** | body LLM+seal · apply/WAV · intro · allocation/coverage · speakable scrub+gate |
| Dual / competing SSOTs | **yes** | adjudication vs gap body vs layup-owned allocation/intro |
| Soft-heal / thrash re-admit loops | **partial** | scaffolding loud on unpaid intro |
| Co-producer / unpaid land | **yes** | rewrite/intro vs S9 |
| Brittle predicates vs simple rules | **yes** | flow + move 0.35 + lint |
| Disproportionate shard/memo/resume | **partial** | Part A/B + allocation |
| “Fix everything downstream” behavior | **yes** | intro coverage recovery |

**Over-engineered?** `yes`  
**Scorecard verdict:** `FAIL`

### 5b — Re-score (MODE=fix S6/S7 2026-09-25T18:10:00Z)

| Check | Answer | Fail-if? | Evidence on HEAD |
|-------|--------|----------|------------------|
| Responsibilities count | **2** | no | (1) advisory LLM+seal (2) folded `_pre_synth_gap_stamps` ALLOW suite + read-only speakable/coverage + heal |
| Dual / competing SSOTs | **no** | no | Primary adjudication.json; stamps field-ALLOW only |
| Soft-heal / thrash re-admit loops | **no** | no | Core peel holds |
| Co-producer / unpaid land | **no** | no | S6: rewrite/orientation persist as `vo_line_adjudicate` (no synth spoof) |
| Brittle predicates vs simple rules | **partial** | no | Flow threshold remains |
| Disproportionate shard/memo/resume | **partial** | no | Dead intro/allocation helpers remain |
| “Fix everything downstream” behavior | **no** | no | Stamps are readiness ALLOW, not body kitchen |

**Fail-if hits:** 0  
**Over-engineered?** `no`  
**Scorecard verdict: PASS**

Prior: §5a FAIL · post-S1–S5 PASS · entry-wrapper rescore FAIL · S6/S7 PASS.

S7 safest pick: **keep-and-fold** on adjudicate (do not peel back to synth — would undo vo_synthesize/edl simplify pins).

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P0 | decided: A advisory-only | **done** | `done:` apply traces only; no body/WAV land | dual SSOT, unpaid land | No stage write of `interviewer_lines[].text` |
| S2 | P0 | decided: peel (no relocate) | **done** | `done:` stage does not call `run_intro_compose` | responsibilities, unpaid land | No episode_preface from stage |
| S3 | P1 | decided: stop persist | **done** | `done:` no `persist_allocation_plan` from stage | dual SSOT | No allocation artifact from stage |
| S4 | P0 | unambiguous | **done** | `done:` re-read disk gap before speakable | thrash | No loud-fail on unpaid mint |
| S5 | P2 | unambiguous | **done** | `done:` drop move_candidate | brittle | One need rule |
| S6 | P0 | unambiguous | **done** | `done:` rewrite + orientation persist with `stage_key=vo_line_adjudicate` | unpaid land | No synth spoof on gap delivery stamp |
| S7 | P0 | decided: keep-and-fold | **done** | `done:` `_pre_synth_gap_stamps` single suite on entry (kept here vs peel-to-synth) | responsibilities | Entry calls fold once; count ≤2 |

**Open ship rows:** none.  
**Operator decisions:** S1=A · S2=peel · S3=stop allocation · S7=keep-and-fold (safest vs cross-stage thrash).  
**Backlog:** delete dead intro/allocation helpers; optional intro into layup.

---

## 7. Root-cause verdict

Advisory peel (S1–S5) holds. Entry-wrapper FAIL was unpaid synth spoof + split stamp responsibilities. S6 honest writer + S7 keep-and-fold restore PASS without undoing vo_synthesize/edl peels.

---

## 8. Recommended next action

`leave`

---

## 9. Scope fence

Upstream poison owner (if any): `nugget_layup_compose` (thin/scaffold body; coverage shortfall)  
Downstream victims (names only): `vo_synthesize`, `edl`, `edl_narrative_audit`  
Did **not** redesign other stages.
