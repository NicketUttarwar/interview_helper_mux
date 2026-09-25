# High-risk stage audit — vernacular_segment_sanitize

tier: T3 | seed: #19 | runs_hit: 9/9  
status: `complete`  
mode: fix  
updated: 2026-09-25T18:21:57Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> Write this before anything else. Also open the chat with a short spoken summary of what this stage does, its main rules, and key considerations so a human can orient cold.

### What this stage does

Happy path: after `audio_probe_build` has zones and `segment_classification` / `boundary_topic_resplit` have a segment manifest, this stage finds parents that intersect `transcript/protected_zones.json`, N-way splits them into special (vernacular) vs ordinary children via `sanitize_manifest_with_zones`, optionally merges flow-level `audio_tags` onto overlapping children, then lands (1) rewritten `segments/manifest.json`, (2) `vernacular/resplit_report.json`, (3) `analysis/vernacular_must_keep.json`, (4) zone `segment_ids` rebound to special children. Ends with `heal_or_refuse_mark(..., force=True)`.

Missing/empty zones or missing/corrupt manifest → honest skip stub (`skipped: …`) + heal (HS-5). Sanitize/write exceptions under default `fail_open` → empty/error report + heal (never bare limbo).

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (soft) | `transcript/protected_zones.json` | From `audio_probe_build`; also rewritten here |
| Reads (soft) | `segments/manifest.json` | Co-producer rewrite after classification/resplit |
| Reads (soft) | `vernacular/audio_tags_by_flow.json`, `transcript/speaker_flows.json` | Advisory tag merge |
| Writes (SSOT claim) | `vernacular/resplit_report.json` | Primary done honesty artifact (HS-5) |
| Writes (co-producer) | `segments/manifest.json` | ALLOW co-writer (i4); restamp marks this producer |
| Soft / side | `analysis/vernacular_must_keep.json` | Must-keep ids + `enforcement_mode` (not golden facts) |
| Soft / side | `transcript/protected_zones.json` | Rebind `segment_ids` after children minted |

### Rules that govern it

- **Admit** — zones present (or honest skip); sanitize returns; writes land; heal marks done
- **Refuse** — only when `audio_probes.fail_open=false` and corrupt/exception (raises)
- **Incomplete** — missing / schema-hollow resplit_report **and** no vernacular-restamped manifest → resume here (`_vernacular_segment_sanitize_incompleteness`)
- **Heal** — skip/error stubs are honest land, not body soft-rewrite; force heal after stub or success
- **Wait_for_gate** — none (G0 / probes upstream)
- **Done / hollow honesty** — HS-5: `{}` hollow fails; skip stub, `rows` list, or `error` string ok; alt-complete if this producer restamped manifest
- **Hard floors / QC bars** — `min_child_ms` (default 800); enforcement shadow vs authoritative is consumer policy
- **Freeze / never_touch / ownership** — ALLOW manifest co-write; must_keep sidecar; does **not** write `run_golden_facts` (i4 / exec_11871)

### Considerations & load-bearing policy

- **Report heat is seed-order:** T3 “same class as `content_context`” — agenda races when earlier analysis is incomplete; not a vernacular logic bug.
- **Manifest shared bus:** classification → vernacular resplit → low_conf / fuse / ranking also ALLOW — intentional rematerialize, not unpaid thrash.
- **Must-keep covenant:** shadow default (advisory); `authoritative` hard-blocks auto_pack / shape gates — see `vernacular-evidence-covenant.md`.
- **STT lexicon islands** are a **separate** soft-boost path: catalog producers are `full_master_ranking` (islands) and `low_conf_island_scan`→`full_master_ranking` (boosts) after VSS S1 — not this stage.
- Full-auto: fail_open=true (clinic VSS-B5 / 7A kept); no operator gate.

### LLM / external calls

N/A — deterministic process. (Local ML STT lives in upstream `audio_probe_build`.)

### What it deliberately does *not* do

- Does not invent protected zones or listen/answers (probes)
- Does not classify / fuse / rank segments
- Does not mutate `analysis/run_golden_facts.json`
- Does not write STT lexicon island/boost JSON (S1 catalog producers = FMR / low_conf)
- Does not own selection membership or VO

### Operator-visible effects

- GUI Audio Probes panel can surface must_keep / zones (read-only API)
- No dedicated gate; incompleteness pins resume this stage
- Shadow mode logs `vernacular.shadow.recorded` when must_keep non-empty

---

## 1. Job statement

Deterministically N-way re-split segment parents that hit vernacular protected zones, land an honest resplit report + must_keep sidecar, and keep zone→segment bindings coherent — so later island-scan / fuse / ranking see special children instead of coarse parents.

---

## 2. Error-hint intake

From the high-risk report. Classify each predicate.

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| Seed-order vs `content_context` (homunculus) | `seed_order_noise` | Seed #19 sits after content_context / framing / resplit; recoveries spam when earlier analysis incomplete |
| Same seed-order class (T3 frequent, usually recovered) | `seed_order_noise` | Report clusters with `#17 framing_posture_decide` |
| AuthorityDenied on `segments/manifest.json` (exec_11871 heritage) | `healed` | i4 ALLOW co-producer; tests `test_i4_vernacular_manifest_ownership` |
| Hollow done / missing resplit_report | `healed` | HS-5 incompleteness + skip stubs (`test_hs5_vernacular_hollow`) |
| DENY writing must_keep into golden facts | `healed` | Side-car `vernacular_must_keep.json` only |
| Ghost ALLOW `analysis/stt_lexicon_*.json` under this stage | `healed` | S1: islands→FMR; boosts→low_conf+FMR (auth FMR); heal_pin fixed |

Report why-high-risk: Same seed-order class

Classification values: `root_here` | `downstream_of_X` | `seed_order_noise` | `authority_friction` | `still_present_on_HEAD` | `healed`

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `stages/audio_probes.py::run_vernacular_segment_sanitize` |
| Skip / heal helpers | `persist_vernacular_skip`, `_heal_vernacular_done` (same file) |
| Core split | `vernacular_sanitize.py::sanitize_manifest_with_zones` |
| Enforcement / loaders | `enforcement_mode_for_ctx`, `load_must_keep_segment_ids`, `vernacular_must_keep_ids` |
| Done honesty | `stage_completion._vernacular_segment_sanitize_incompleteness` (+ `_honest_*` / `_vernacular_restamped_manifest`) |
| Agenda present | `homunculus/agenda.py` → `stage_artifact_incompleteness` |
| Freeze / ownership | `artifact_ownership` ALLOW: manifest co-write, resplit_report, must_keep, protected_zones; stt_lexicon re-homed (S1) |
| Contract | `docs/cross-cutting/stage-contracts/vernacular_segment_sanitize.yaml` |
| Covenant | `docs/cross-cutting/vernacular-evidence-covenant.md` |
| Tests (non local-ML) | `test_hs5_vernacular_hollow.py`, `test_i4_vernacular_manifest_ownership.py`, `test_vss_s1_stt_lexicon_ownership.py`, `test_audio_probes.py` |

---

## 4. Business-logic walk

1. **Preflight** — Read zones / manifest; missing or empty → `persist_vernacular_skip` + force heal; corrupt manifest → fail_open skip or raise.
2. **Resplit** — `sanitize_manifest_with_zones(manifest, zones, min_child_ms)` → children with `is_special` / `must_keep` / report rows (`pattern` SW\|EN).
3. **Tag merge** — If flow tags present, copy passion/speech_act/keywords/spans onto overlapping children; mark `near_special_flow` when adjacent.
4. **Persist** — Fingerprint-write manifest + resplit_report; write must_keep sidecar; rebind zone `segment_ids` to special overlaps; never touch golden facts.
5. **Write-fail path** — Prefer error stub + heal (VSS-B3); if stub cannot land, return unmarked so incompleteness pins resume.
6. **Done** — `_heal_vernacular_done` → `heal_or_refuse_mark(..., force=True)`. No LLM.

---

## 5. Over-engineering scorecard

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **2** | (1) N-way resplit + zone/tag coherence on hit parents; (2) honest land of report / must_keep / skip stubs. Not a third product job. |
| Dual / competing SSOTs | **no** | Product SSOT is resplit_report (+ intentional must_keep sidecar). Manifest is shared rematerialize bus, not a second competing vernacular SSOT. Ghost stt_lexicon ALLOW ≠ dual product SSOT (same as RA S1 hygiene). |
| Soft-heal / thrash re-admit loops | **no** | Fail-open skip/error stubs are honest completes; no remutate / re-admit loop in body. |
| Co-producer / unpaid land | **no** | Manifest write is paid ALLOW rematerialize after zones; not unpaid thrash of a foreign unpaid body. |
| Brittle predicates vs simple rules | **no** | Done = honest report shape or this-producer restamp; simple. |
| Disproportionate shard/memo/resume | **no** | ~230-line entry + ~210-line pure helper; no shard/resume theater. |
| “Fix everything downstream” behavior | **no** | Emits children + must_keep; fuse/ranking/selection own their jobs. |

**Over-engineered?** `no` — ≤2 responsibilities; zero hard fail-if rows.

**Scorecard verdict:** `PASS`

- Report heat is seed-order reflection of earlier analysis incompleteness, not stage bloat.
- What would flip FAIL → PASS: N/A (already PASS).

### 5b — Re-score after changes (MODE=fix · HEAD after S1)

| Check | Answer | Delta vs §5a | Evidence now |
|-------|--------|--------------|--------------|
| Responsibilities count | **2** | — | Unchanged; S1 was catalog hygiene only. |
| Dual / competing SSOTs | **no** | ghost catalog cleared | stt_lexicon producers = FMR / low_conf+FMR; vernacular no longer heal_pin owner. |
| Soft-heal / thrash re-admit loops | **no** | — | Unchanged. |
| Co-producer / unpaid land | **no** | — | Unchanged. |
| Brittle predicates vs simple rules | **no** | — | Unchanged. |
| Disproportionate shard/memo/resume | **no** | — | Unchanged. |
| “Fix everything downstream” behavior | **no** | — | Unchanged. |

**Over-engineered?** `no`  
**Scorecard verdict:** `PASS`

Note: paths remain `write_mode=operational` (any stage may persist); S1 fixes catalog producers / `heal_pin` / contract outputs — not a fail-closed producer gate flip.

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P3 | decided: build | **done** | islands→FMR; boosts→low_conf+FMR (auth FMR); FMR/low_conf contracts + 00-INDEX; `test_vss_s1_*` | ownership hygiene | producers/heal_pin assert; vernacular absent |

Open rows: none (scorecard PASS — leave / monitor).

Backlog (not opened): contract soft-vs-hard inputs drift (`boundaries` DOC_ONLY); peel fail_open=false path — clinic already decided **keep fail_open=true** (VSS-B5 / 7A); optional flip stt_lexicon `operational`→`staged` for hard producer DENY (needs_you).

Operator decisions: S1 build (2026-09-25).

---

## 7. Root-cause verdict

**Not the root of the high-risk heat.** Predicates are almost entirely **seed-order pile-up** when earlier analysis (`content_context` and peers) is incomplete; stage body is a thin deterministic resplit + HS-5 honesty layer. Historical AuthorityDenied on manifest / golden-facts mutate is **healed** (i4 ALLOW + must_keep sidecar). S1 cleared ghost stt_lexicon catalog / heal_pin mis-pin.

---

## 8. Recommended next action

`leave` (PASS after S1; no open cuts)

---

## 9. Scope fence

Upstream poison owner (if any): earlier seed-order analysis (`content_context` / probes / classification) when incomplete — not this stage’s logic  
Downstream victims (names only): `low_conf_island_scan`, `connector_fuse_pass`, `full_master_ranking`, selection auto_pack / shape gates (must_keep consumers)  
Did **not** redesign other stages.
