# Full-auto forensics — error & root-cause analysis

**Run:** `exec_13177_d19c15b58ab4_20260923T001031Z`  
**Input:** `mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3`  
**Outcome:** Ship complete (local). Master, delight, and post-master quality all passed. S3 upload waited for operator G-Publish consent.

This note explains **what went wrong**, **where it showed up**, and — most importantly — **which stages were the real root causes** versus which stages only echoed someone else’s failure.

Stage numbers use the normal 72-stage pipeline order (analysis stages 1–35, delivery stages 36–72).

Related artifacts:
- Campaign state: `.cursor/plans/full_auto_forensics_state.md`
- End report: `.cursor/plans/full_auto_forensics_end_report_exec_13177.md`
- Raw ledger: `ASSETS/executions/exec_13177_…/operator/forensics_errors.md` (476 entries, 97 unique predicates)

---

## How to read this document

There are two different questions people mix up:

1. **Where did the error message appear?**  
   Example: EDL says “opening orientation inaudible.” That message is printed at stage **#58 `edl`**.

2. **Where did the defect actually start?**  
   Example: the orientation line was already wrongly treated as “waived” in air-script / omit logic much earlier. Fixing EDL alone would not have cured it.

This document answers question 2 first, then lists the noisy symptom stages so they are not mistaken for roots.

---

## Exact counts

| Kind | Count |
|------|------:|
| Distinct **root-cause stages** in this run | **4** |
| High-noise **symptom stages** (not roots) | **5** |
| Interventions that patched product code (late campaign i9–i15) | **7** major patches (+ i12b reload) |

The four root-cause stages are:

1. **#45 `nugget_layup_compose`**
2. **#55 `vo_synthesize`**
3. **#42 `air_script_compose`** (bug lived in air-script / omit / waive logic; failed loudly at EDL)
4. **#53 `sound_design_plan`**

Everything else was mostly follow-on thrash, seed-order waiting, or recovered noise.

---

## The four root-cause stages (detailed)

### 1. Stage #45 — `nugget_layup_compose` (biggest root)

**Ledger hits at this stage:** 97 (highest of any stage in the run)

#### What went wrong

Two related failures started here:

1. **CTA segments were dropped** (`selection_cta_omit`).  
   The layup compose path omitted CTA-related segments (for example `seg_003ga`, and later a cluster around `seg_070*`). That removed material the rest of the pipeline still expected for opening / host obligations.

2. **Hosted VO floor was unmet** (`hosted_vo_floor_unmet`).  
   With G-Framing set to Yes, the product requires a minimum number of synthetic host lines (at least 3). After CTA omit and layup churn, that floor was not met. Hard freeze then blocked the “easy” reseat path that would have restored active hosted copy for WAV rendering.

There was also shard incompleteness (`layup_compose_shards_pending`) and selection-commit refusals under freeze, but those sat on top of the same incomplete layup.

#### Why this is a root cause (not a symptom)

Later stages did not invent this problem. They only noticed that:

- there were not enough hosted VO lines, or
- required opening / CTA-related material was gone or waived, or
- refinement could not run because layup was not seed-complete.

If #45 had produced a complete layup with the hosted floor satisfied, most of the early delivery thrash would not have happened.

#### What cascaded from #45

| Symptom stage | What it looked like |
|---|---|
| **#47 `refinement_agenda`** (84 hits) | Endless “complete nugget_layup_compose before running refinement_agenda.” This stage was stuck waiting; it was not the author of the defect. |
| **#51 `air_contract_sanitize` / #52 `transitions`** | Identical execute failures ×5–×6: `air_contract_unsanitary: hosted_vo_floor_unmet`. Driver sat on transitions while the real pin pointed back at layup / VO. Escalated to `suppress_budget_exhausted`. |
| **#55 `vo_synthesize` (early)** | Missing WAVs / G1 still open for floor lines that should already have been seated and renderable. |
| **#58 `edl` (early)** | `g1_open` refuse mark_done for lines such as `vo_layup_seg_003b`, `003c`, `010`, `018`. |

#### Patch link

Intervene **i10** fixed the hard-freeze floor reseat path so already-active hosted copy could be reseated for WAV under End-A, then pinned to `vo_synthesize`. The *shortage itself* still originated at #45.

---

### 2. Stage #55 — `vo_synthesize` (second independent root cluster)

**Ledger hits at this stage:** 69

#### Important distinction

After the floor / CTA mess from #45 was being worked, a **second** class of bugs appeared:

> WAV files often **did** exist, but the pipeline still treated synthesis as failed, omitted seated lines, or dropped pickup files on flush.

That is not “layup still incomplete.” That is VO authority / contract / StageInfo misbehavior during and after synthesize.

#### Root defects patched here

| Intervene | What was wrong in simple terms | Immediate fallout |
|---|---|---|
| **i11** | Omitted lines that already had WAVs lost their omit flags in the gap report (clamp / repair drift). Contract ladder kept failing. | Gates at `vo_synthesize`: “omitted X lacks skip/omit flags”; ladder exhausted → `active_remediation_plan_conflict`. |
| **i12** | Omit-ledger reconcile purged **seated** hosted takes (and deleted their WAVs). Also, StageInfo only declared `vo_pickup/synthesized/`, so top-level `vo_pickup/*.wav` copies were dropped on flush. | EDL / assembly said coverage missing for `vo_layup_seg_003c` even after synthesize looked done. Required serve reload (**i12b**) because the running server still had the old StageInfo. |
| **i13** | Chatterbox wrote the WAV, then exited with a false failure (`invalid_json_stdout` from a package warning). Bind-heal treated that as omit-wins (`seated_bind_synth_failed`) and omitted a seated line that already had audio on disk. | `flush_refuse:vo_fail_open_not_success`; assembly_preview coverage thrash again. |

#### Why this is its own root

#45 explains “we never got enough / the right hosted lines.”  
#55 explains “we got lines and WAVs, then the system threw them away or refused to count them.”

Those needed different patches (`vo_contract`, `omit_ledger`, StageInfo, `vo_bind_authority`).

#### What cascaded from #55

| Symptom stage | What it looked like |
|---|---|
| **#57 `edl_narrative_audit`** | Gate: VO unsanitary / seated bind stale / synthesize not seed-complete. |
| **#58 `edl`** | Refuse mark_done because `vo_synthesize` incomplete; later publishability / coverage fights. |
| **#59 `assembly_preview`** | Gate: `VO coverage not rendered: ['vo_layup_seg_003c']` (repeated until i12/i13 stuck). |

Console `ERROR at` lines also recorded **3×**  
`Post-flush heal success refused: flush_refuse:vo_fail_open_not_success` at `vo_synthesize`.

---

### 3. Stage #42 — `air_script_compose` (orientation root; failed at EDL)

**Where people saw it:** stage **#58 `edl`** — `opening_orientation_inaudible` (expected 1, heard 0), repeated about four times as hard `ERROR at edl`.

**Where the defect lived:** air-script / omit / waive handling around a **required** CTA-orientation scrap.

#### What went wrong (simple)

A required opening-orientation line carried stale “we already waived this” stamps (`tier_d_logged_waive` / execution-contract waive) even though it was still required and should still be on air. Seat-building treated that as a durable waive. Heal playbooks sometimes skipped revive unless resume was exactly `edl`. Soft-freeze also made omit persist a no-op, so seats stayed wrong after a gap revive.

Result: EDL’s publishability check correctly said “I cannot hear the required opening orientation.”

#### Why not call #58 the root

EDL was doing its job. The orientation had already been removed from the audible plan upstream. Patching only EDL would not restore the line.

#### Relatedness to #45

CTA omit at layup made the orientation story messier, but the **bug that kept the required line dead** was the waive/seat logic on the air-script side (**i9**). That is why this is listed as its own root: different producer, different patch, different continue-from (`edl` after revive).

#### Cascade

| Symptom stage | What it looked like |
|---|---|
| **#58 `edl`** | `publishability blocked at post_edl: opening_orientation_inaudible` |
| Recovery / agenda notes | “complete nugget_layup_compose before running edl” as a recovery hint — often misleading if the real stuck state was waived orientation seats |

---

### 4. Stage #53 — `sound_design_plan` (late music / SDP root)

This cluster hit after VO/EDL/mix were largely past the early VO crisis. It is independent of the hosted-VO story.

#### Defect A — stale off-selection bed seeds (**i14**)

**Simple version:** Selection had shrunk. An old bed-coverage seed still pointed at `seg_028`, which was no longer in selection. Repair code dropped off-selection cues too late (after coverage seeding / validate), so `music_palette_compose` refused density/slots after one repair.

**Failed loudly at:** **#61 `music_palette_compose`** (only 2 ledger hits, but each was a hard stop).

**Root lived at:** SDP repair / seed logic owned by **#53** / `repair_sound_design_plan`.

Live follow-on (**i14b**): palette `segment_ids` still needed pruning; one validated write path reverted, so a direct SDP write was needed to keep the fix.

#### Defect B — invent refused under mix-seated freeze (**i15**)

**Simple version:** Mix had already seated assembly audio. Later, sound-design tried to invent / reconcile narrative under a freeze that denied writing `master/narrative_plan.json` from `edl_narrative_audit` (`mix_seated` + `narrative_arc_plan`). The stage fail-closed and rewound even though `master/assembly.wav` and an SDP already existed. Missing `_meta.producer_stage` also made “SDP present” checks fail after a raw write.

**Error text (nested):**
- Outer: `sound_design_plan: order_reconcile failed — refuse invent on drifted selection/narrative`
- Inner: `authority_denied:persist:master/narrative_plan.json:edl_narrative_audit:mix_seated:narrative_arc_plan`
- Freeze blocks noted: `edl_narrative_audit:narrative_metadata_align:mix_seated`

Patch: if assembly + SDP already exist, do not fail-closed invent; stamp producer_stage; mark SDP done.

#### Cascade from #53

| Symptom stage | What it looked like |
|---|---|
| **#61 `music_palette_compose`** | Density refuse on `bed_coverage_seed_11` / `seg_028` |
| **#57 `edl_narrative_audit`** | ERROR log attributed here while the failing producer path was sound_design invent |
| Later walk | Incomplete-after-conductor handoffs into sfx / mmaudio / junction once music path cleared |

---

## High-noise symptom stages (not roots)

These stages generated many failure entries or scary messages, but they were not where the defect was introduced.

### #47 `refinement_agenda` — 84 hits

Almost entirely seed-order waiting on incomplete **#45**. Not a product root for this campaign.

### #58 `edl` — 48 hits

Mixture of:
- orientation publishability from **#42**
- G1 / VO incomplete from **#45** / **#55**
- hard-freeze persist denials while sealed

EDL is a common **detector**, not the author of those defects.

### #52 `transitions` — 18 hits

Most of the painful identical-halt storm was **hosted_vo_floor_unmet** leaking through while the pin belonged to layup/VO.  
Separately, `spoken_copy_guard` blocked some pair copy (`Performance` / mid-sentence fallback). That recovered and was not a ship blocker.

### #59 `assembly_preview` — 4 hits

Repeated “VO coverage not rendered for `003c`” — direct echo of omit purge / bind false-fail from **#55**.

### #40 `full_master_ranking` — 19 hits

Hard-freeze persist denials and a pre-flush commit barrier (`seg_003g` / `seg_070c` missing from ordered ∪ excluded). Recovered; not one of the late i9–i15 root patches that defined the campaign’s long thrash.

---

## Major errors by stage (including nested causes)

This section is the “what failed” inventory. Nesting means: outer message people saw, then the inner reason underneath.

### Blocking / thrash cluster

| # | Stage | Major error | Nested / cascade |
|---|-------|-------------|------------------|
| **45** | `nugget_layup_compose` | Layup incomplete / CTA omit / floor unmet | `selection_cta_omit` dropped CTA segs; `hosted_vo_floor_unmet` (need ≥3); hard freeze blocked floor reseat; shards pending; selection commit `authority_denied` under pre_soft_freeze |
| **51** / **45** | sanitize → pin to layup | `air_contract_unsanitary: hosted_vo_floor_unmet` | Surfaced as ×5–6 identical `500` while driver sat on **#52**; escalate `suppress_budget_exhausted` |
| **55** | `vo_synthesize` | `flush_refuse:vo_fail_open_not_success` (×3 ERROR) | omit+WAV flag drift; chatterbox `invalid_json_stdout` after writing WAV; bind heal omit-wins; undeclared `vo_pickup/*.wav` drop; VO contract ladder exhausted |
| **57** | `edl_narrative_audit` | Gate: VO unsanitary / coverage | `seated_bind_stale`; synthesize not seed-complete; coverage not rendered |
| **58** | `edl` | `opening_orientation_inaudible` (×4 ERROR) | required CTA-orientation treated as waived; early `g1_open` refuse; later synthesize-incomplete refuse |
| **59** | `assembly_preview` | VO coverage not rendered (`003c`) | omit-ledger purge of seated take + false bind-fail omit |
| **61** | `music_palette_compose` | Post-compose density refuse (×2 ERROR) | `bed_coverage_seed_11` → `seg_028` not in selection; palette prune / write revert |
| **53** / **57** | `sound_design_plan` (often logged under narrative audit) | `order_reconcile` refuse invent | `authority_denied` on narrative_plan under `mix_seated`; missing producer_stage meta |

### Secondary / escalate

| # | Stage | Error | Nested |
|---|-------|-------|--------|
| **40** | `full_master_ranking` | Pre-flush commit barrier / hard_freeze persist | Segments missing from ordered∪excluded; manifest persist denied |
| **52** | `transitions` | `spoken_copy_guard` on a pair | Unsupported entity / mid-sentence fallback (recovered) |
| **47** | `refinement_agenda` | Seed-order thrash | Waiting on incomplete **#45** |
| **32** | `gap_framing_compose` | `gap_report.json is pending_only` | Transient; recovered |
| **72** | `podcast_publish` | S3 sync blocked | Quality-advisory G-Publish consent gate (local ship still OK; PMQ `publish_allowed=True`) |

### Early / recovered noise

| # | Stage | Pattern |
|---|-------|---------|
| **1–3** | `audio_preclean` / `ingest` / `transcribe` | Transient `authority_denied:mark_done:pending_writes` |
| **17 / 19 / 27 / …** | framing / vernacular / mastering / fuse / air_script | Seed-order “complete X before Y” while the walk caught up |

### Incomplete-after-conductor (handoffs, not product bugs)

These were logged as delivery errors but meant “this stage finished; conductor needs the next ones”:

- #58 → #59 `assembly_preview`
- #64 → #61 `music_palette_compose`
- #61 → #62 `sfx_prompt_craft`
- #62 → #63 `mmaudio_sfx`
- #63 → #65 `junction_snip_qa`

---

## Interventions mapped to root stages

| Intervene | Root stage | One-sentence fix |
|---|---|---|
| **i9** | #42 air_script (surfaced #58) | Required orientation is not durably waived; revive and reseat before EDL persists |
| **i10** | #45 condition / sanitize path → #55 | Reseat already-active hosted VO for WAV under hard freeze; pin coverage to synthesize |
| **i11** | #55 | Reseat omitted+WAV; keep gap omit flags coherent under freeze |
| **i12 / i12b** | #55 (+ StageInfo) | Protect seated lines from omit purge; declare `vo_pickup/`; reload serve |
| **i13** | #55 | Treat on-disk stem WAV as bind success; never omit when WAV present |
| **i14 / i14b** | #53 (surfaced #61) | Drop off-selection bed seeds early; prune palette segment ids |
| **i15** | #53 | If assembly+SDP exist, do not invent-fail under mix-seated reconcile deny |

---

## Bottom-line ranking

If you only remember four numbers from this run:

1. **`#45 nugget_layup_compose`** — CTA omit + hosted VO floor shortfall → largest cascade (roughly half the thrash).  
2. **`#55 vo_synthesize`** — bind / omit / StageInfo false-fails after WAVs existed → long mid/late VO–EDL thrash.  
3. **`#42 air_script_compose`** — stale required-orientation waive → EDL publishability loop.  
4. **`#53 sound_design_plan`** — stale off-selection beds + mix-seated invent refuse → late music/SDP block.

**Exact answer:** **4 stages** were the top of the problems / true roots.  
The other high-count stages (`#47`, much of `#58`, `#52`, `#59`, `#40`) were follow-on or recovered noise.

---

## Ship quality (for context)

Despite the thrash above, the same run eventually shipped:

| Gate | Result |
|------|--------|
| `master/master.wav` | Present (~226 MiB, ~2465 s) |
| `verify_master` | OK (−16.00 LUFS, −1.00 TP, 48 kHz) |
| Listen delight | Passed, overall **0.9725** |
| Post-master quality | `pass`, `publish_allowed=True` |
| Local publish package | `publish/audio.mp3` + `cover.jpg` |
| S3 | Deferred on operator G-Publish consent |

That does not erase the roots above — it means the continue-on-bug loop (patch producer → cascade pytest → resume same `run_id`) eventually cleared them without starting a second execution.

---

## Post-fix review — are the roots actually fixed? (2026-09-23)

This section was added after a full codebase review against the four root-cause stages above. Goal: say what is **safe for the next fresh run**, what is **only partly fixed**, and what is **still missing** and can recreate errors.

**How the review was done**
- Read product paths for i9–i15 and related layup / ownership / SDP work.
- Ran cascade tests with `MUX_FORENSICS=0`:
  - `test_i9` … `test_i15` → **15 passed**
  - Related: `test_i14b_sdp_compose_write`, End-A floor reseat, pending_only heal → **passed** where selected
  - Found one **failing stale test**: `test_cta_commit_skipped_under_soft_freeze` (expects soft freeze to skip CTA commit; product now correctly **commits** under soft freeze)

---

### Scorecard (next-run risk)

| Root / cluster | Status | Will the **same** exec_13177 thrash recur? |
|---|---|---|
| **#45** CTA omit identical-halt / commit refuse | **FIXED** | Unlikely |
| **#45** hosted floor unmet when active≥need but WAV short (i10) | **FIXED** | Unlikely |
| **#45** CTA omit dropping natives that floor VO still needs | **PARTIAL** | Possible as `hosted_vo_floor_unmet` / unsatisfiable |
| **#45** true floor shortage (active &lt; need) under hard freeze | **BY DESIGN** | Same *symptom string* can still appear until layup can write |
| **#55** i11 omit+WAV flag drift | **FIXED** | Unlikely |
| **#55** i12 seated omit purge + undeclared `vo_pickup/` | **FIXED** | Unlikely |
| **#55** i13 false-fail bind omit-wins | **FIXED** | Unlikely |
| **#42** i9 orientation stale waive | **FIXED** | Unlikely |
| **#53** i14 / i14b off-selection beds + write revert | **FIXED** | Unlikely |
| **#53** i15 mix-seated invent refuse | **FIXED** | Unlikely |
| **#32** gap `pending_only` thrash | **FIXED** | Unlikely |
| **#40** FMR commit barrier / hard freeze | **MISSING** | Possible (recovered in-run last time; no dedicated patch) |
| **#52** transitions `spoken_copy_guard` | **MISSING** | Possible non-blocking pair refuse (recovered last time) |

**Bottom line:** The four campaign roots that ate the most wall-clock are **product-fixed and cascade-tested**. What remains is mostly **#45 coupling / true shortage**, plus two **secondary** stages that never got a dedicated 13177 patch.

---

### What is fixed (safe enough for next run)

#### #42 / i9 — required opening orientation no longer “waived to death”

- Required orientation scrap is **not** treated as waived by stale `tier_d_logged_waive` stamps (`air_script._orientation_line_waived`).
- Tier-D ladder refuses to re-waive required orientation (`execution_contract`).
- Revive clears stamps, supersedes omit, reseats `vo_seats`; playbook always revives; `run_edl` revives before persist.
- Tests: `tests/test_i9_required_orientation_stale_waive.py` (3 cases) — **pass**.

**Next run:** The exact `opening_orientation_inaudible` ×4 identical loop from stale waive should **not** come back.

#### #45 / i10 + layup thrash paths

- When hard freeze blocks *inventing* new floor lines but **active copy already ≥ need** and seats lack WAV → End-A `reseated_active_hosted_vo_for_wav`, then pin `hosted_vo_wav_coverage` → `vo_synthesize`.
- CTA omit no longer raises into `selection_cta_omit` budget exhaust: needs are demoted non-blocking and get **one in-invoke LLM retry** (`llm_simple.py`, comments cite exec_13177).
- Layup selection commit is on the ownership bus; hard freeze **skips** CTA rewrite; soft freeze still commits via End-A packaging.
- Final-shard `layup_compose_shards_pending` thrash under hard freeze is fixed (`stage_completion`).
- Tests: `test_i10_hosted_vo_wav_coverage.py`, End-A constitution reseat, HR-2 / layup ownership — **pass**.

**Next run:** The exact i10 fingerprint (active≥3, wav_backed=1, hard-freeze thrash) and the CTA identical-halt storm should **not** recur.

#### #55 / i11 + i12 + i13 — VO synth false-fails

- Omitted+WAV lines reseat; gap omit flags stay coherent (`vo_contract`).
- Omit-ledger protects seated line ids, supersedes active omit for them, does not purge their EDL clips/WAVs (`omit_ledger`).
- StageInfo declares `vo_pickup/` **and** flush always promotes `vo_pickup/**` for VO owner stages (`web/stages.py`, `write_staging.py`) — so even a stale serve is less likely to drop pickup WAVs the way i12b did.
- Landed stem WAV is accepted despite bad chatterbox JSON; bind heal never omit-wins when WAV exists (`local_runtime`, `vo_bind_authority`).
- Heal success no longer chicken-eggs `vo_fail_open_not_success` via seed completeness alone (`heal_success`).
- Tests: `test_i11_*`, `test_i12_*`, `test_i13_*` (+ vo55 authority extras) — **pass**.

**Next run:** The long mid-campaign VO → EDL → assembly `003c` coverage ladder should **not** recur for those mechanisms.

#### #53 / i14 + i14b + i15 — SDP / music

- Off-selection bed cues dropped **before** coverage seeding; bed-anchor pool filtered to selection; palette `segment_ids` pruned (`artifact_repairs.repair_sound_design_plan`).
- Music palette compose detects reverted prune and force-commits / restamps `producer_stage` (`music_palette_compose`, `test_i14b_sdp_compose_write`).
- If mix already seated and assembly + SDP exist, sound_design skips fail-closed invent on order_reconcile deny and finalizes/meta-stamps (`sound_design_stages`).
- Tests: `test_i14_*`, `test_i14b_*`, `test_i15_*` — **pass**.

**Next run:** `bed_coverage_seed_11` / `seg_028` density refuse and mix-seated invent rewind should **not** recur.

#### #32 — gap `pending_only` (secondary, but fixed)

- Rationale defaulting + heal preferring real flush failures over `pending_only` mask (`test_stage_completion_heal`).

---

### What is still missing or only partial (will / can cause errors next run)

#### 1. #45 — CTA omit can still orphan the hosted VO floor (**PARTIAL — highest remaining #45 risk**)

**What is still broken conceptually**

CTA omit is allowed to drop native segments even when those segments are the **only live targets** of the hosted lines that count toward the G-Framing floor. Floor topup (`_framing_floor_topup`) skips targets that are no longer in the live selection. There is **no** “floor unmet → refuse this CTA omit” guard.

**What that means on the next run**

You may **not** see the old `selection_cta_omit` × budget_exhausted thrash (that path is fixed). You **can** still see:

- `hosted_vo_floor_unmet`
- or escalate to `hosted_vo_floor_unsatisfiable`

…after a successful CTA prune that removed the natives the floor VO pointed at.

**Why this matters**

This is the closest remaining cousin of the original #45 root: omit is intentional, but omit ↔ floor coupling is still weak.

**Suggested product gap (not present today)**

- Before committing CTA prune, check that remaining selection still supports `min_synthetic_vo_lines` / live targets of floor-counting host lines; otherwise refuse omit or retarget first.
- Cascade test: “CTA need + floor unmet / only-target → do not drop floor targets.”

---

#### 2. #45 — true hosted-floor shortage under hard freeze (**BY DESIGN — same symptom string**)

If **active host lines &lt; need** while hard freeze is on, sanitize still **refuses invent**, stamps `protect_hosted_vo_floor_reseat_refused_hard_freeze`, and pins back to layup. That is constitutionally correct (End-A forbids inventing floor under hard freeze).

**Next run:** You can still hit `hosted_vo_floor_unmet` with that meaning. It is **not** the i10 bug (active≥need, WAV short). It means layup truly did not leave enough host copy before freeze.

Mitigations exist (hollow preserve, floor topup when targets live, unsatisfiable escalate), but they do not invent copy under hard freeze.

---

#### 3. #55 — omit purge seat-lag (**narrow residual**)

Seated protection joins `seated_vo_line_ids(plan)`. If omit reconcile runs **before** seating is written into the plan, a stale omit row can still strip clips/WAVs. Protect load is also behind `except: pass` — import/load failure silently falls back to old purge.

**Next run:** Unlikely if seating always precedes reconcile (normal path). Possible under unusual heal ordering.

---

#### 4. #40 `full_master_ranking` — commit barrier / hard freeze (**MISSING dedicated fix**)

Last run recovered without a campaign intervene. There is still no exec_13177-tagged product fix that guarantees:

- manifest segments like `seg_003g` / `seg_070c` stay in ordered ∪ excluded before flush, or
- hard-freeze manifest persist denials do not thrash FMR.

Nearby hardening exists (`test_fmr_hardening.py`, lint wording), but this exact failure mode is **not** closed the way i9–i15 are.

**Next run:** Same errors can appear again; usually recoverable, but they cost time and pollute the ledger.

---

#### 5. #52 `transitions` — `spoken_copy_guard` (**MISSING dedicated fix**)

Guard still blocks pairs for `spoken_unsupported_entity` / mid-sentence fallback (e.g. “Performance”). Prior mid-sentence repair from an older exec is not a full 13177 “entity vocabulary” fix.

**Next run:** Possible non-blocking / recover-able pair refuse. Not the main ship risk, but not eliminated.

---

#### 6. Test debt — soft-freeze CTA skip test is **wrong / failing**

- `tests/test_layup_compose_hardening.py::test_cta_commit_skipped_under_soft_freeze` expects `commit_layup_cta_selection(...) is None` under soft freeze.
- Current product **commits** under soft freeze (End-A packaging) — confirmed by `test_soft_freeze_still_commits_cta` **passing** and the skip test **failing**.

This will not by itself break a forensics run, but it will confuse the next agent/human who “fixes” product to match the stale test and reintroduce soft-freeze CTA skip thrash.

**Action:** Delete or rewrite the stale skip test to match ownership SSOT.

---

### What will *not* break the next run (noise only)

- Incomplete-after-conductor “errors” while walking sfx → mmaudio → junction → master (handoffs).
- Early seed-order “complete X before Y” while the walk catches up.
- Transient `authority_denied:mark_done:pending_writes` on very early stages (if it recurs, it clears).
- S3 blocked on G-Publish quality-advisory consent when local ship is already OK.

---

### Recommended pre-next-run checklist

1. **Must-have already in tree:** i9–i15 (+ i14b) — verified present and green under `MUX_FORENSICS=0`.
2. **Should fix before trusting a quiet #45:** CTA↔floor coupling (item 1 above) + cascade test.
3. **Should clean:** rewrite failing `test_cta_commit_skipped_under_soft_freeze`.
4. **Nice-to-have:** dedicated #40 FMR ordered∪excluded / hard-freeze persist regression; #52 entity-guard softer recovery if pair thrash returns.
5. **Ops:** still reload serve after StageInfo / ownership patches if you change them again (i12b lesson); owner-flush for `vo_pickup/**` reduces but does not erase that class of footgun.

---

### One-paragraph verdict for operators

The errors that **defined** exec_13177 — orientation waive, hosted-floor WAV deadlock, VO omit/bind/StageInfo false-fails, off-selection SDP beds, and mix-seated invent rewind — are **resolved in code and covered by cascade tests**. The main thing still able to recreate a **#45-shaped** failure on the next fresh run is **CTA prune orphaning the hosted VO floor** (and, separately, a **true** floor shortage under hard freeze, which is intentional). Secondaries **#40** and **#52** were never given dedicated 13177 patches and can still noise the ledger. Fix the CTA↔floor gap and the stale soft-freeze test before treating #45 as fully closed.

---

## Residuals closed (items 1–6)

All six gaps from “What is still missing or only partial” are closed. Cascade under `MUX_FORENSICS=0` (91 passed): `test_i16_cta_floor_anchor_keep`, `test_i12_seated_omit_purge_protect`, `test_enda_hard_freeze_constitution`, `test_layup_compose_hardening`, `test_layup_selection_commit_ownership`, `test_fmr_hardening`, `test_i9_required_orientation_stale_waive`, `test_i10_hosted_vo_wav_coverage`, `test_spoken_copy_guard`.

| # | Item | Status | Tests |
|---|------|--------|-------|
| 1 | CTA ↔ hosted VO floor coupling | FIXED | `tests/test_i16_cta_floor_anchor_keep.py` |
| 2 | Hard-freeze true shortage → unsatisfiable (empty heal pin) | FIXED | `tests/test_enda_hard_freeze_constitution.py` (incl. `test_enda_auto_commit_skips_refuse_notes`); i10 WAV path unchanged |
| 3 | Omit-ledger seat-lag + WAV protect fail-closed | FIXED | `tests/test_i12_seated_omit_purge_protect.py` |
| 4 | FMR ordered ∪ excluded cover + hard-freeze skip invent | FIXED | `tests/test_fmr_hardening.py::test_cover_ranking_manifest_membership_excludes_orphans`, `::test_hard_freeze_skips_cta_child_invent` |
| 5 | `spoken_copy_guard` Performance + mid-sentence soften | FIXED | `tests/test_spoken_copy_guard.py::test_performance_title_case_common_noun_allowed_for_transition`, `::test_mid_sentence_fallback_softened_not_blocked` |
| 6 | Stale soft-freeze CTA skip test | FIXED | Deleted `test_cta_commit_skipped_under_soft_freeze`; SSOT remains `test_soft_freeze_still_commits_cta` / `test_hard_freeze_skips_cta_commit` |
