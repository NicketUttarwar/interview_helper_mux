# Possibility Map — hollow_pass

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: hint_only_if_named

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## Plain-language summary (fill last, write for the operator)

- In one sentence, what is broken: **Done markers and “ready” predicates can still diverge from honest primaries** — stamp gates are strong for many producers, but restamp / raw heal / thin incompleteness / non–VO-chain ready, and bare `is_done` consumers, leave hollow-pass residuals.
- In one sentence, what “fixed” looks like: **Every path that touches `.stage_done` or admits a consumer uses the same seed-complete / primary-artifact honesty** (Done Authority + incompleteness), including restamp and schedule — not only VO-chain `producer_ready`.

---

## 1. Mechanism census (HEAD)

| Surface / function | Role in this class | Tag | Path:line |
|--------------------|--------------------|-----|-----------|
| `RunContext.mark_done` | Sole normal stamp writer; ownership + disk status + FORCE_DONE_GUARDED incompleteness; touches `.stage_done/{stage}` | `IN_CODE` | `src/interview_mux/run_context.py:534–665` |
| `RunContext.is_done` | Bare marker presence (file exists) — **not** honest complete | `IN_CODE` | `src/interview_mux/run_context.py:720–721` |
| `_mark_done_raw` / fixture `mark_done_raw` | Bypass ownership + incompleteness (tests + heal flush path) | `IN_CODE` | `run_context.py:541–582`; `tests/run_fixtures.py:19–31` |
| `assert_may_mark_done` | Ownership hollow DENY unless `stage_outputs_present` (gate stages allow marker-only) | `IN_CODE` | `src/interview_mux/artifact_ownership.py:2084–2138` |
| `done_authority.try_mark_done` | Recommended stamp API; False on AuthorityDenied (no silent success) | `IN_CODE` | `src/interview_mux/done_authority.py:156–181` |
| `done_authority.is_seed_complete` / `may_clear_wait` | ESR / wait clear only on seed-complete — never bare `is_done` | `IN_CODE` | `done_authority.py:61–82` |
| `stamp_finalize_on_success` / `finalize_incompleteness` | Finalize = integrity + well-formed PMQ; ship-gate open = hollow | `IN_CODE` | `done_authority.py:111–204` |
| `require_seated_before_mix_mark` | Refuse mix stamp when unseated | `IN_CODE` | `done_authority.py:231–248` |
| `seed_stage_complete` | G1 honesty: `is_done ∧ outputs ∧ incompleteness is None` (+ mix seat demote) | `IN_CODE` | `src/interview_mux/delivery_guardrails.py:125–152` |
| `producer_ready` | MUST_PRECEDE readiness = seed-complete; **Leapfrog B+** VO-chain extra primary/disk refuse | `IN_CODE` | `delivery_guardrails.py:155–195` |
| `earliest_incomplete_producer` | Walks MUST_PRECEDE via `producer_ready` | `IN_CODE` | `delivery_guardrails.py:270–287` |
| `stage_outputs_present` | Agenda / ownership presence predicate (stage-specific) | `IN_CODE` | `src/interview_mux/homunculus/agenda.py:810–1029` |
| `stage_artifact_incompleteness` | Semantic hollow reason; specialized branches + generic `stage_required_artifact_paths` loop | `IN_CODE` | `src/interview_mux/stage_completion.py:873–…` / paths helper `:30–37` |
| `heal_or_refuse_mark` | Heal mark/unmark authority; on ok path sets `_mark_done_raw` then `mark_done` | `IN_CODE` | `stage_completion.py:2682–2795` |
| `reconcile_stage_done_marker` | Unlinks `.stage_done` when incompleteness non-empty | `IN_CODE` | `stage_completion.py:1886–1905` |
| `unmark_hollow_delivery_producers` / `unmark_hollow_prepare_stages` | Clear hollow markers (delivery / G0 prepare) | `IN_CODE` | `agenda.py:90–97`, `:1032–1086` |
| `reconcile_delivery_batch` (G3) | Snapshot hollow → unmark → reconcile → XOR orphan promote | `IN_CODE` | `delivery_guardrails.py:1361–1410` |
| `promote_complete_orphan_stage_done` | Inverse hollow: stamp when outputs+completeness OK (via heal_or_refuse) | `IN_CODE` | `delivery_guardrails.py:1414–1495` |
| `apply_seed_order_heal` **restamp** | **`marker.touch()` without `mark_done` / Done Authority** when `live_producer_authority` | `IN_CODE` | `src/interview_mux/delivery_invariants.py:590–634` |
| `seed_order_heal_action` | Chooses restamp vs unmark; finalize without integrity → unmark only | `IN_CODE` | `delivery_invariants.py:197–210` |
| `playbook_seed_order_prereq` | Recovery wires restamp/unmark + admit_resume | `IN_CODE` | `src/interview_mux/recovery_controller.py:956–…` |
| `demote_hollow_mix_done` / `mix_is_seed_complete` | Mix marker demoted when not seated | `IN_CODE` | `src/interview_mux/mix_junction_seat.py:635–674` |
| `FORCE_DONE_GUARDED` + `assert_may_force_done` | Force hollow gate for large producer set | `IN_CODE` | `thrash_hardening.py:25–80+`, `:996+` |
| LLM `_auto_complete_or_raise` / llm_flow `try_mark_done` | auto_complete refused → StageError (not hollow success) | `IN_CODE` | `llm_simple.py:32–41`; `llm_flow_hardening.py:304–339` |
| `e2e_soft_enabled` / quality waivers | Gate auto-progress only; quality waivers separate opt-in | `IN_CODE` | `src/interview_mux/e2e_soft.py:17–37` |
| `soft_pass_pre_edl_delivery` | Refuses stubs unless `E2E_SOFT` + `LAST_RESORT_SOFT`; else brief + `[]` | `IN_CODE` | `tools/full_auto_driver.py:7577–7602` |
| Agenda post-master hole backfill | After master exists: `_mark_done_raw` + `mark_done(force=True)` on unmarked pre-master holes | `IN_CODE` | `agenda.py:1341–1354` |
| `HOLLOW_DONE` | Claims **closed** via Done Authority | `CODE_DOC_CONFLICT` vs this class residual | `src/interview_mux/done_authority.py` |
| XC-HOLLOW-01 | Analysis incompleteness coverage gap still OPEN_RISK | `IN_CODE` (catalog) | `.cursor/plans/failure_catalog/crosscuts.md:155–165` |

---

## 2. Failure permutations

| Case | What happens now | Honest outcome should be | Tag | Pointer |
|------|------------------|--------------------------|-----|---------|
| clean recover | Incomplete → heal_or_refuse unmarks / refuses; G3 clears hollow; seed-complete false | Same | `IN_CODE` | `heal_or_refuse_mark`, `reconcile_delivery_batch` |
| wrong target | Hollow on wrong stage; wrong_pin lands elsewhere | Separate class — pin authority | `IN_CODE` | heal-clinic `wrong_pin` |
| leapfrog | Hollow done on VO producer → MUST_PRECEDE used to look legal; B+ `producer_ready` refuses VO-chain without primary | Consumer deferred / clamp to hole | `IN_CODE` | `producer_ready` VO block; `test_admit_constitution.py:68–77` |
| hollow success (stamp) | Production `mark_done` refuses missing primary / incompleteness for guarded stages; `try_mark_done` → False | Refuse / StageError | `IN_CODE` | `run_context.mark_done`, Done Authority |
| hollow success (restamp) | `apply_seed_order_heal` can **touch** `.stage_done` without re-running `mark_done` gates | Restamp only if live authority + seed-complete-equivalent | `IN_CODE` | `delivery_invariants.py:599–605` |
| hollow success (raw heal) | `heal_or_refuse_mark` stamps via `_mark_done_raw` when incompleteness returns None | Incompleteness must catch thin/refuse docs | `IN_CODE` | `stage_completion.py:2775–2782` |
| hollow success (post-master backfill) | Unmarked pre-master holes force-stamped once master exists | Explicit allowlist + outputs present | `IN_CODE` | `agenda.py:1341–1354` |
| validate≠stage | Heal “ok” / seed-complete while stage body still fails | heal_validate class | — | cousin |
| post-success budget burn | Hollow cleared then thrash re-burns budget | post_heal_budget_thrash | — | cousin |
| Partial must-act open | Gate stages may marker-only (`transcript_review`); ownership allows | Intentional for G0 — not hollow lie if gate signed | `IN_CODE` | `assert_may_mark_done` gate set |
| Full-auto defaults | Same Done Authority; e2e_soft does **not** waive quality; soft_pass needs last-resort | No hollow via e2e_soft alone | `IN_CODE` | `e2e_soft.py`, `soft_pass_pre_edl_delivery` |
| Bare `is_done` skip | Pipeline / journey still branches on `ctx.is_done` → can skip re-invoke despite hollow marker until G3/heal | Prefer seed_stage_complete for advance | `IN_CODE` | `pipeline.py` / `journey_state.py` uses of `is_done` |
| Analysis thin complete | Generic path loop only if `STAGE_ARTIFACT_DISK_PATHS` / secondaries listed; XC-HOLLOW-01 residual | Every producer has incompleteness or disk primary | `IN_CODE` | `stage_required_artifact_paths`; XC-HOLLOW-01 |

---

## 3. Already closed vs residual

| Prior DP / cousin_matrix row | Claimed closed? | Verified on HEAD? | Residual? |
|------------------------------|-----------------|-------------------|-----------|
| DP-DONE-AUTHORITY / cousin `HOLLOW_DONE` | closed | **Yes** — `done_authority.py` + `test_done_authority.py` | **Partial** — stamp API closed; class residual remains |
| Mix seated before mark (`require_seated_before_mix_mark` / demote) | closed | **Yes** | Thin if callers skip helper |
| Finalize PMQ + integrity | closed | **Yes** | — |
| LLM auto_complete → `try_mark_done` | closed | **Yes** | — |
| soft_pass / e2e stub without last-resort | closed (refuse) | **Yes** — returns `[]` + brief | Last-resort path still stubs if env set (`FULL_AUTO_REGRESSION_RISK` if mis-set) |
| HV3/HV4/HF1/HU*/HP* stage hollow tests | many closed | **Yes** — large hollow test suite | Stage-by-stage, not one SSOT |
| Leapfrog B+ VO-chain `producer_ready` honesty | implemented (cousin hook) | **Yes** — 5 stages + `test_hollow_adjudicate_not_producer_ready` | **Yes** — honesty **not** generalized past VO chain; largely redundant when seed-complete already false |
| `apply_seed_order_heal` restamp honesty | not claimed closed under HOLLOW_DONE | **Touches marker directly** | **Yes — primary residual** |
| XC-HOLLOW-01 analysis incompleteness coverage | OPEN_RISK | Catalog accurate vs specialized branches | **Yes** |
| Non–FORCE_DONE_GUARDED producers | not closed | mark_done incompleteness check only if in FORCE_DONE_GUARDED | **Yes** for unguarded stages |
| Agenda post-master hollow backfill | intentional anti-rewind | **Yes** on HEAD | **Residual risk** if master exists but hole never produced |
| Heal validate uses same ready | not this class | — | Opens **heal_validate_stage_fail** |

---

## 4. Complexity traps

- Duplicate SSOT / dead defs: `stage_completion.seed_stage_complete` re-exports guardrails (`stage_completion.py:2813–2817`); Done Authority wraps same. OK — but bare `is_done` still everywhere.
- Mode-special branches: G1 optional skip allow-stub in `heal_or_refuse_mark` / mark_done; Partial gate marker-only; HAU speech-first skips beds in MUST_PRECEDE walk (not hollow, but readiness shape differs).
- Heal that hides quality failure: restamp-as-ready when `live_producer_authority` true but consumer still needs regeneration; orphan promote XOR with hollow unmark (TH6) — promote after wrong incompleteness None.
- OpenAI: CSP-05 hollow LLM docs (TCA / shape agenda / research routing) refuse incompleteness — deterministic host, not model tuning.
- Leapfrog B+ VO honesty: runs **only after** `seed_stage_complete` is True — so it catches cases where outputs_present/incompleteness disagree with `STAGE_ARTIFACT_DISK_PATHS` primary, or monkeypatched seed-complete fixtures. Not a full hollow_pass fix.

---

## 5. TEST_GAP

| Behavior | Covered? | Suggested matrix test (`MUX_FORENSICS=0`) |
|----------|----------|-------------------------------------------|
| Done Authority hollow finalize / wait | **Yes** | `tests/test_done_authority.py` |
| Leapfrog B+ hollow adjudicate not ready | **Yes** | `tests/test_admit_constitution.py::test_hollow_adjudicate_not_producer_ready` |
| Stage-specific hollow (HV3, HV6, HF1, HU1, HP2, HPUB*, residual wave5) | **Yes** (many) | Keep; do not replace with one mega-test |
| soft_pass refuses without last-resort | **Yes** | `tests/test_r4_premature.py`, `test_category_b_footguns.py` |
| `apply_seed_order_heal` restamp with **missing** primary still touches marker | **Gap** | Fixture: hollow pin → `live_producer_authority` false → unmark; if true with thin auth → assert seed_complete after restamp |
| `producer_ready` honesty for **non-VO** MUST_PRECEDE producers (sanitize, edl, mix) | **Gap** | Parametrize MUST_PRECEDE producers: done marker only → `producer_ready` False |
| Restamp path uses Done Authority / `try_mark_done` not `Path.touch` | **Gap** | Lint or unit: `apply_seed_order_heal` must not leave hollow seed-complete |
| Analysis stages lacking specialized incompleteness still refuse hollow mark | **Thin** (wave5 scan) | Extend XC-HOLLOW-01 matrix: every ANALYSIS_ORDER id with disk path |
| Post-master agenda backfill without outputs | **Gap** | Master present + empty hole stage → backfill must not seed_complete |
| Partial vs Full-auto same seed-complete for schedule | **Thin** | Shared fixture: hollow marker → filter/admit_schedule both block |

---

## 6. Cousin hints (suggestions only)

- Related heal-clinic classes:
  - **leapfrog_resume** — B+ already added VO-chain hollow-honest `producer_ready`; hollow_pass owns generalizing / restamp honesty.
  - **wrong_pin** — checklist must not treat hollow done as prereq green (options already say so).
  - **heal_validate_stage_fail** — heal “validate ok” must call same seed-complete / admit as stage body (no soft-pass).
  - **post_heal_budget_thrash** — hollow clear → re-enter → budget burn.
- Possible bigger deterministic shared rule: **Done Constitution** = every `.stage_done` writer goes through `try_mark_done` / `heal_or_refuse_mark`; restamp = re-assert seed-complete; `producer_ready` = seed-complete for **all** MUST_PRECEDE (not only VO five). Merge with HC-LEAP-ADMIT / HC-PIN-NAV rather than a third SSOT name.

---

## 7. Ready for options?

- [x] Census complete enough for A/B/C
- [x] Surgical imaginable: harden restamp + widen `producer_ready` primary check
- [x] SSOT imaginable: Done Constitution (all writers + ready predicates)
- Next paste: `/heal-clinic-options CLASS=hollow_pass`
