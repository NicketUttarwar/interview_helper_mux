# High-risk stage audit — podcast_publish

tier: T2 | seed: #72 | runs_hit: 9/9  
status: `complete`  
mode: rescore  
updated: 2026-09-25T18:17:08Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

### What this stage does

Happy path: after `master/master.wav` + encode/cover/meta exist, **admit** only when Tier-0 PMQ `publish_allowed` (refuse-only — no soft re-eval) → require cover already present (legacy png→jpg materialize only) → build timed chapters → copy packagable master VTT (refuse if missing) → ensure `publish/master.wav` → Apple cover floor → materialize episode file set → write `episode.json` / `description.txt` / `package_ready.json` (`ready:true`) / `publish_result.json` (`uploaded:false`) → `mark_done`. **S3/RSS upload is not this stage.**

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `master/master.wav`, `publish/audio.mp3`, `publish/cover.jpg`, `master/transcript.vtt` | Contract hard; encode/cover/transcript upstream |
| Reads (soft) | EDL, selection, narrative, `publish/episode_meta.json`, `publish/cover_meta.json` | Chapters + episode draft |
| Writes (SSOT) | `publish/package_ready.json` | Primary completion stamp |
| Writes (ops package) | `publish/{chapters,episode,description,transcript,publish_result}` (+ may materialize audio/master/cover) | Ownership ALLOW rows |
| Soft / side | G-Publish gate meta; skip path `ready:false`+`skipped:true` | Outside S3 sync |

### Rules that govern it

- **Admit** — `require_publishable` (PMQ present + `publish_allowed`); package inputs present
- **Refuse** — missing/empty package files; unpackagable VTT; cover missing (resume cover_generate) or <1400px; PMQ missing / not publish_allowed (loud)
- **Incomplete** — HPUB-2: hollow unless `package_ready.ready:true` **or** honest skip (`skipped:true`)
- **Heal** — none on unpaid SSOTs (post S1–S3); legacy cover.png→jpg materialize only
- **Wait_for_gate** — Partial G-Publish must-act (Prepare / Sync / Skip); Full-auto DONE-local / refuse-remote (no auto-consent)
- **Done / hollow honesty** — skip writes `ready:false`+`skipped`; bare `ready:false` stays incomplete
- **Hard floors** — Tier-0 PMQ for local package; Apple cover 1400; packagable VTT; non-empty episode files
- **Freeze / ownership** — owns package_ready + episode package files; PMQ / autopsy / master VTT / cover_meta stay upstream

### Considerations & load-bearing policy

- Publishability: advisory PMQ does **not** block local package; S3 sync requires operator consent when advisories fire.
- Clinic target applied: DONE-local / refuse-remote; `require_g_publish_clear` **KEEP DEAD** (S5 documented).
- Module co-locates sibling publish stages (meta/cover/encode); this audit is **only** `podcast_publish`.

### LLM / external calls

N/A for this stage (no OpenAI). Cover/meta LLM live in sibling stages. S3 is post-stage sync (boto3).

### What it deliberately does *not* do

- Upload to S3 / rewrite RSS (separate sync)
- Soft-heal / re-persist PMQ or seam autopsy
- Nested `master_transcript_build` or show-fallback cover invent
- Auto-consent quality advisories on Full-auto
- Call `require_g_publish_clear`

### Operator-visible effects

- G-Publish: Prepare local package, Sync (consent if advisories), or Skip
- Full-auto: local `package_ready` + remote refuse; `s3_sync` / `stack_shutdown` decisions no longer land as forensics stage errors (S4)

---

## 1. Job statement

Assemble a local RSS-ready episode package under `publish/` and stamp honest `package_ready` — refusing when Tier-0 PMQ or upstream package inputs are missing — without uploading.

---

## 2. Error-hint intake

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `HARD: post_master_quality unrecovered` | `downstream_of_master_finalize` | Still pins here when remaining=publish; S1 no longer soft-heals PMQ at admit |
| `forensics_escalate` / `forensics_stall` | `seed_order_noise` | Driver stall when PMQ unrecovered |
| `s3_sync` / `stack_shutdown` | `healed` (S4) | Still logged as decisions; excluded from forensics error ledger |
| Nested transcript / cover fallback unpaid writes | `healed` (S2/S3) | Refuse upstream |

Report why-high-risk: post_master_quality / S3 / escalate (after master exists)

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `stages/podcast_publish.py` → `run_podcast_publish`, `run_podcast_publish_skip` |
| Key helpers | `post_master_quality.require_publishable` (refuse-only); `build_timed_chapters`; `require_cover_min_size`; `require_packagable_master_transcript`; `gates.clear_g_publish` |
| Primary writes | `publish/package_ready.json`, episode package files, `publish/publish_result.json` |
| Freeze / ownership | Package rows owned here; PMQ=`master_finalize`; VTT=`master_transcript_build`; cover=`episode_cover_generate` |
| Tests | `tests/test_podcast_publish_clinic.py` (B1–B6 + S2–S5); `tests/test_endf_pmq_score_honesty.py` (S1 refuse-only) |

---

## 4. Business-logic walk

1. **Admit / refuse PMQ** — `require_publishable`: missing PMQ → loud `post_master_quality_missing`; not `publish_allowed` → loud `publish_blocked_bad_master` (**no** autopsy refresh / persist).
2. **Cover** — staging/final cover missing → legacy png→jpg **or** copy prior cover **or** `FileNotFoundError` resume `episode_cover_generate`.
3. **Chapters** — `build_timed_chapters` → `publish/chapters.json`.
4. **Transcript** — require existing packagable `master/transcript.vtt`; copy to `publish/` (no nested build).
5. **Master archive** — copy encode’s `publish/master.wav` or `master/master.wav`.
6. **QC + materialize** — cover ≥1400; every layout key non-empty; copy into staging.
7. **Stamp** — episode draft + description + `package_ready.ready:true` + `publish_result` → `mark_done`.
8. **Skip** — `ready:false`+`skipped:true`; honest seed-complete (HPUB-2).

---

## 5. Over-engineering scorecard

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **3** | Baseline pre-fix: gate+soft PMQ, assemble, upstream backfill |
| Dual / competing SSOTs | **partial** | Soft PMQ re-persist path |
| Soft-heal / thrash re-admit loops | **partial** | One-shot PMQ refresh |
| Co-producer / unpaid land | **yes** | Nested transcript; PMQ/autopsy; show-fallback cover_meta |
| Brittle predicates vs simple rules | **no** | |
| Disproportionate shard/memo/resume | **no** | |
| “Fix everything downstream” behavior | **no** | |

**Over-engineered?** `yes` — baseline.

**Scorecard verdict:** `FAIL` (baseline)

### 5b — Re-score after changes (MODE=rescore 2026-09-25T18:17:08Z)

HEAD verify: `require_publishable` refuse-only (~1111–1141); `run_podcast_publish` refuse missing cover/VTT (~593–639) + assemble/stamp; `log_decision` skips `s3_sync`/`stack_shutdown` for error ledger; `require_g_publish_clear` KEEP DEAD. Focused suite **13 passed**.

| Check | Answer | Delta vs 5a | Evidence now |
|-------|--------|-------------|--------------|
| Responsibilities count | **2** | 3→2 | (1) refuse PMQ / missing cover·VTT·inputs (2) assemble + stamp `package_ready` |
| Dual / competing SSOTs | **no** | cleared | `require_publishable` reads PMQ only — no persist/autopsy |
| Soft-heal / thrash re-admit loops | **no** | cleared | No soft re-eval on admit |
| Co-producer / unpaid land | **no** | cleared | No nested transcript / show-fallback / PMQ write in this stage |
| Brittle predicates vs simple rules | **no** | — | Simple missing-file / `publish_allowed` refuses |
| Disproportionate shard/memo/resume | **no** | — | Single-pass package |
| “Fix everything downstream” behavior | **no** | — | Upload stays separate; S4 peels ship-bar forensics noise |

**Over-engineered?** `no` — ≤2 responsibilities; no hard fail-if rows.

**Scorecard verdict:** `PASS`

Open §6 rows: none. S1–S5 remain **done** (no new fail-if → no new cuts).

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P0 | unambiguous | done | done: peel soft PMQ re-eval/persist from `require_publishable` — refuse-only | co-producer; dual SSOT; soft-heal; responsibilities | `test_endf_require_publishable_refuses_without_soft_reeval` |
| S2 | P0 | unambiguous | done | done: drop nested `run_master_transcript_build` — missing VTT raises resume hint | co-producer; responsibilities | clinic S2 source + refuse tests |
| S3 | P1 | needs_you | done | done: **refuse** missing cover (safest) — no `_copy_show_fallback` / `cover_meta`; legacy png→jpg kept | co-producer; responsibilities | clinic S3 refuse test |
| S4 | P2 | needs_you | done | done: exclude `s3_sync`/`stack_shutdown` from `record_from_driver_event` (keep decisions) | forensics noise | clinic S4 source pin |
| S5 | P2 | unambiguous | done | done: KEEP DEAD docstring on `require_g_publish_clear` + existing AST pin; not wired | leave | clinic S5 + B4 |

Operator decisions: S3=refuse (recommended/safest); S4=exclude from error ledger (safest — ship behavior unchanged).

Open rows: none — **PASS** confirmed on rescore (leave/monitor only).

---

## 7. Root-cause verdict

Was ship-completion attribution plus unpaid soft-heals on admit. After S1–S5: stage is refuse→assemble→stamp; PMQ/transcript/cover ownership stays upstream; Full-auto S3 refuse-remote + stack teardown no longer inflate forensics stage-error counts.

---

## 8. Recommended next action

`leave` — monitor Full-auto for honest PMQ/cover/VTT refuses; do not revive soft heals or `require_g_publish_clear`.

---

## 9. Scope fence

Upstream poison owner (if any): `master_finalize` / `junction_snip_qa` (PMQ / autopsy); `master_transcript_build`; `episode_cover_generate`  
Downstream victims (names only): G-Publish sync (`sync_assets`), Full-auto ship bar  
Did **not** redesign other stages.
