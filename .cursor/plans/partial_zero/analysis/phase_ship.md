# Phase analysis — ship

brain: 0.2.0 | mode: partially_accelerated | code_is_king: true  
phases.py: `ship` → finalize + SHIP_AFTER_MASTER + G-Publish  
hints only: clinic maps `master_finalize` / `podcast_publish`; Mohan HINT i11h; BP-B4/B5/C1–C5

## Level 1 — Stage solo

| Stage | Open routes (HEAD) | Thrash? | Notes |
|-------|--------------------|---------|-------|
| `master_finalize` | assert_consumer; optimizer take-best → nested junction; loudnorm assembly→master; `run_post_master_quality` (autopsy → delight → evaluate → persist → re-raise delight); g_listen / optimizer gates; PMQ structural loud-fail | **Yes — HOLLOW_DONE / PMQ** | Required outputs (agenda): `master/master.wav` **and** `master/post_master_quality.json`. Incompleteness helper checks **master integrity only** — split vs mark_done. |
| `master_transcript_build` | STT/master transcript; incompleteness if missing | Low | Local package spine |
| `episode_meta_build` | meta JSON | Low | |
| `episode_cover_prompt_craft` | empty prompt incompleteness | Low | OpenAI cover cascade upstream of generate |
| `podcast_encode_mp3` | encode incompleteness | Low | Local ML N/A (ffmpeg) |
| `episode_cover_generate` | cover.jpg hollow incompleteness | Medium | Vision/LLM cascade; long_stage in driver |
| `podcast_publish` | local `package_ready.ready:true`; skip path mark_done without ready (HPUB-2); PMQ `require_publishable`; S3 advisory ≠ local bar | **Yes — SHIP_BAR_VOCAB** | G-Publish MUST_ACT on Partial; stage body does not call `require_g_publish_clear` (dead rail — intentional for Full-auto). |

### HEAD honesty splits (SSOT)

1. **`assert_may_mark_done` / `stage_outputs_present`:** finalize needs master **+** PMQ.
2. **`stage_artifact_incompleteness("master_finalize")`:** only `committed_master_integrity_ok` — **no PMQ**.
3. **`heal_or_refuse_mark(..., force=True)` → `_mark_done_raw`:** bypasses `assert_may_mark_done`; `assert_may_force_done` uses incompleteness only → **can hollow-stamp finalize with master.wav and no PMQ**.
4. **i11h surface:** `run_post_master_quality` persists PMQ before re-raising delight; `run_wrapped_stage` flushes pending on exception. Test: `test_i11_pmq_persists_when_delight_fails`. Surface reduced; root incompleteness / force-raw / five-meanings-of-done remain.
5. **ESR / driver:** BP-C1–C5 / B5 — wrong pin wait, keep-join on `is_done`, five done predicates (HINT + HEAD). Local package can be ready while ESR/driver disagree.

## Level 2 — Group

- **Internal order / done agreement:** MUST_PRECEDE `edl` → `master_finalize`; filter also needs `committed_master_wav` for SHIP_AFTER_MASTER. Agenda `ship_after_master_remaining` = missing **outputs**, not mere markers. Driver `pipeline_complete` ≈ master + podcast_publish done + cover + mp3 (C5).
- **Candidate SIMPLIFY / CUT:**
  - SIMPLIFY: one finalize-complete predicate (master + PMQ + integrity) shared by incompleteness, force-done, ESR clear, agenda.
  - Do not CUT PMQ or authoritative delight at ship — NORTH_STAR listen-delight gate.
  - G-Publish stays human on Partial (MUST_ACT_OK) — not a CUT; separate from local ship bar.

## Level 3 — Handoffs

| Edge | Ready meaning | Cousin risk |
|------|---------------|-------------|
| P11 build → ship | seated mix/junction honesty + edl; then finalize | MIX_JUNCTION_SEAT · HOLLOW_DONE junction |
| M34 edl → finalize | seed_complete edl + consumer asserts | hollow junction → false ship |
| finalize → SHIP_AFTER_MASTER | `committed_master_wav` + PMQ publish envelope | hollow finalize / missing PMQ |
| ship → G-Publish / done | local package_ready vs S3 advisory consent | SHIP_BAR_VOCAB · ESR_POST_MASTER |

## Level 4 — Junctions

| Junction id | Fact | Callers | Linked DP |
|-------------|------|---------|-----------|
| J-hollow-done | `.stage_done` without required outputs is not seed-complete | `assert_may_mark_done`, agenda, heal force-raw | **DP-SHIP-HOLLOW-FINALIZE** (+ DP-B4 family) |
| J-post-master-wait | After master, wait vs halt / driver join / ship remaining disagree | ESR, pipeline, agenda, runner, driver | DP-C1–C5 (cousin); hollow finalize feeds this |
| J-assembly-freshness | Finalize refuses stale assembly vs edl | `assert_consumer`, agenda master freshness | build DPs |

## Decision Packets drafted

- **DP-SHIP-HOLLOW-FINALIZE** — hollow mark_done / PMQ / incompleteness vs force-raw — `awaiting_operator`
- Related open families (not re-packeted here): SHIP_BAR_VOCAB (DP-C5), ESR_POST_MASTER (DP-C1–C4), HOLLOW_DONE B4/B5

## Partial impact

Partial cannot ironclad-finish ship while finalize can refuse stamp (thrash) **or** force-raw hollow-stamp (false advance), and while ESR/driver five-meanings-of-done still disagree after audible master. G-Publish human wait is **expected** on Partial (PARTIAL_MUST_ACT_OK) once local package is honest.

## Verdict (phase)

**PARTIAL_BLOCKED** on **HOLLOW_DONE @ finalize/PMQ** until DP-SHIP-HOLLOW-FINALIZE (+ cousin B4/B5 as needed). Packaging stages: **PARTIAL_OK_IF_FINALIZE_HONEST** with G-Publish as must-act gate. Downstream **SHIP_BAR_VOCAB** still open for unattended “campaign done” clarity.
