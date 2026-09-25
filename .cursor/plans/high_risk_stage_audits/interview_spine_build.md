# High-risk stage audit — interview_spine_build

tier: T3 | seed: #7 | runs_hit: 9/9  
status: `complete`  
mode: rescore  
updated: 2026-09-25T18:35:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> Early analysis stage: turn frozen transcript + SAP into a time-aligned **interview spine** used by downstream understanding / boundary / volley compact. Report risk was AuthorityDenied when diarization verify rewrote `transcript/full.json` under the `transcribe` freeze — **peeled (S1/S2):** verify is now advisory repairs-only.

### What this stage does

Happy path (spine enabled): require `transcript/full.json` + complete `source_acoustic_profile` → optional fail-open `run_diarization_verify` (writes **only** `transcript/diarization_repairs.json`) → skip rebuild if `derived_from` hashes match → build word windows (pace-class length) → enrich DSP/prosody features from preclean or normalized wav → fuse boundary events → optional CLAP batch embeddings sidecar → speaker_stats → validate schema → write `understanding/interview_spine.json` → `heal_or_raise`. Disabled path: write schema-valid skip stub + `heal_or_refuse_mark(force=True)` (clinic KEEP-in-seed).

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `transcript/full.json`, `understanding/source_acoustic_profile.json` | Transcript **read-only**; hollow SAP refuse |
| Reads (soft) | `ingest/normalized.wav`, `preclean/isolated.wav` | Audio for features / CLAP / verify clips |
| Writes (SSOT) | `understanding/interview_spine.json` | Primary; ownership sole writer |
| Soft / side | `transcript/diarization_repairs.json`, CLAP embeddings under `understanding/` | Repairs ALLOW operational; advisory YES/absorb for fuse consumers |

### Rules that govern it

- **Admit** — spine enabled + transcript present + SAP not hollow/missing
- **Refuse** — missing transcript / missing or hollow SAP
- **Incomplete** — no force-heal without primary or skip stub
- **Heal** — `heal_or_raise` after valid spine; disabled stub uses `heal_or_refuse_mark(force=True)`
- **Wait_for_gate** — G0 must be clear before transcript is trustworthy
- **Done / hollow honesty** — disabled stub is honest skip; enabled path validates before write
- **Hard floors** — schema via `validate_interview_spine`; SAP incompleteness gate
- **Freeze / ownership** — owns spine + `diarization_repairs.json`; does **not** write transcript/speakers/flows

### Considerations & load-bearing policy

- Downstream: `speaker_roles`, `content_context`, `boundary_detection`; volley compact / coherence / framing posture attach.
- Diarization verify remains **hosted** in ISB (S3 safest = no split); pair verdicts land in repairs for fuse / roles evidence — word `speaker_id` on disk stays G0/`transcribe`.
- Clinic: disabled → skip stub + stay in seed. Default `interview_spine.enabled=true`.

### LLM / external calls

No OpenAI. Optional local CLAP + Sortformer/S2S pair verify. Fail-open when unavailable.

### What it deliberately does *not* do

- Persist word speaker_id relabels / rewrite speakers or speaker_flows
- Own STT / G0 corrections or speaker role assignment
- Boundary topic resplit / EDL

### Operator-visible effects

- Warning logs / `diarization_verify_unavailable` when local speech missing
- Forensics `authority_denied:persist:transcript/full.json:interview_spine_build:…` should stop on HEAD after S1/S2

---

## 1. Job statement

Build (or honestly skip) a schema-valid time-aligned `understanding/interview_spine.json` from transcript + SAP + audio — without mutating the frozen transcript.

---

## 2. Error-hint intake

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `authority_denied:persist:transcript/full.json:interview_spine_build:pre_soft_freeze:transcribe` | `healed` (S1/S2) | Unpaid writes removed; repairs-only |
| `understanding/interview_spine.json is pending` | `seed_order_noise` | Agenda/pending stamp race |
| Diarization verify unavailable | `healed` (fail-open) | By design |

Report why-high-risk: Authority vs `transcribe` freeze

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `src/interview_mux/stages/interview_spine_stage.py` |
| Key helpers | `interview_spine/*`; `diarization_suspicion.run_diarization_verify` (repairs-only) |
| Primary writes | spine + `transcript/diarization_repairs.json` |
| Freeze / ownership | ALLOW spine + repairs; transcript sole `transcribe` |
| Tests | `test_isb_s1_s4_simplify.py`, `test_interview_spine.py`, `test_diarization_suspicion.py`, `test_hu1_sap_hollow.py` |

---

## 4. Business-logic walk

1. Disabled → stub + force heal.
2. Prereqs → missing transcript / hollow SAP raise.
3. Diarization host → probe YES on disposable word copy; land repairs only; fail-open on errors.
4. Idempotent skip via `derived_from` hashes.
5. Build windows → enrich → boundaries → CLAP → stats → validate → write spine → heal.
6. LLM N/A.

---

## 5. Over-engineering scorecard

### 5a — Baseline (pre S1–S4)

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count | **2** | spine + diarization host |
| Dual / competing SSOTs | **no** | |
| Soft-heal / thrash re-admit loops | **no** | |
| Co-producer / unpaid land | **yes** | unpaid transcript/speakers/flows writes |
| Brittle predicates vs simple rules | **no** | |
| Disproportionate shard/memo/resume | **no** | |
| “Fix everything downstream” behavior | **no** | |

**Over-engineered?** `partial`  
**Scorecard verdict:** `FAIL`

### 5b — Re-score after changes (MODE=rescore 2026-09-25T18:35:00Z)

Hard fail-if (skill): responsibilities ≥3 · dual SSOT=yes · soft-heal=yes · co-producer unpaid=yes · brittle=yes · shard/memo=yes · fix-downstream=yes.

HEAD verified: `run_diarization_verify` writes only `REPAIRS_REL` (no `write_json("transcript/…")`); YES uses probe copy; stage comment repairs-only; contract lists repairs + read-only transcript; ownership ALLOW spine + repairs, transcript → `transcribe`. Pins: **4 passed** (`test_isb_s1_s4_simplify` + advisory YES).

| Check | Answer | Delta | Evidence now |
|-------|--------|-------|--------------|
| Responsibilities count | **2** | same vs fix | spine build + hosted advisory verify (S3 no-split) |
| Dual / competing SSOTs | **no** | — | single spine writer |
| Soft-heal / thrash re-admit loops | **no** | — | fail-open verify; no transcript re-admit |
| Co-producer / unpaid land | **no** | held | repairs ALLOW only; unpaid land gone on HEAD |
| Brittle predicates vs simple rules | **no** | — | ownership rule matches behavior |
| Disproportionate shard/memo/resume | **no** | — | lineage skip only |
| “Fix everything downstream” behavior | **no** | — | |

**Fail-if hits:** 0  
**Over-engineered?** `no`  
**Scorecard verdict:** `PASS`

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P0 | needs_you | done | done: decided A — never mutate transcript; advisory repairs only | Co-producer unpaid land | HEAD + `test_isb_s1_s4_simplify::test_s1_s2_*` |
| S2 | P0 | unambiguous | done | done: peeled unpaid transcript/speakers/flows writes; YES probe copy; dead refresh helpers removed | Co-producer unpaid land | `test_verify_yes_advisory_repairs_does_not_mutate_transcript` |
| S3 | P1 | needs_you | done | done: no stage split — verify stays hosted in ISB | Responsibilities stay 2 (ok) | `test_s3_verify_stays_hosted_in_spine_stage` |
| S4 | P2 | unambiguous | done | done: contract + INDEX + dependency data list repairs; transcript read-only | ops clarity | `test_s4_contract_*` |

Operator decisions: S1=A, S3=leave hosted (no new stage).

Open rows: none — leave/monitor. No new fail-if hits → no S5+.

---

## 7. Root-cause verdict

Authority friction from unpaid transcript persist under `transcribe` freeze. Spine algorithm was never the bloat. S1–S4 peel writes to repairs-only; forensics predicate should clear on new runs.

---

## 8. Recommended next action

`leave` — PASS after S1–S4; monitor forensics for gone AuthorityDenied on ISB.

---

## 9. Scope fence

Upstream poison owner (if any): `transcribe` / G0 labels  
Downstream victims (names only): fuse/roles still consume advisory repairs; word labels unchanged  
Did **not** redesign other stages (fuse gap line_id fixture tweak only in diarization test).
