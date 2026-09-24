# Possibility Map — wrong_pin

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: hint_only_if_named

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## Plain-language summary

- In one sentence, what is broken: **Several heal navigators still decide “which stage to run next,” so even after PIN_PREMATURE B1–B3 fixes, a run can still land on the wrong producer when a different navigator wins.**
- In one sentence, what “fixed” looks like: **One ordered pin pipeline every caller uses; wrong-target tokens cannot invent stages; Partial and Full-auto share the same honesty.**

---

## 1. Mechanism census (HEAD)

| Surface / function | Role in this class | Tag | Path |
|--------------------|--------------------|-----|------|
| `producer_pin_for_token` | Declared PIN_PREMATURE SSOT (B1 compound length, B2 no bare substring, B3 unknown→transitions) | `IN_CODE` | `stage_completion.py` ~2547 |
| `premature_class_pin` | Parses `premature_complete:<class>` → pin; unknown → transitions | `IN_CODE` | `stage_completion.py` ~2463 |
| `incompleteness_resume_stage(ctx, consumer)` | Sole incompleteness resume API (B6) | `IN_CODE` | `stage_completion.py` ~2018 |
| `heal_navigate` | Master navigator: specialty pins (voice-ref, high-gap, fuse…) then premature_class → producer_pin_for_token → intent/`path_to_master` | `IN_CODE` | `thrash_hardening.py` ~1657 |
| `canonical_resume_pin` | Intent→producer for music/mix/finalize/vo_g1 epochs | `IN_CODE` | `thrash_hardening.py` ~619 |
| `path_to_master_pin` | Post–Phase-A ladder toward master (can disagree with token pin) | `IN_CODE` | `thrash_hardening.py` ~3031 |
| `premature_cap_hard_pin` / `resolve_premature_cap_pin` | Cap “don’t advance to consumer”; leases + heal_navigate inside | `IN_CODE` | `delivery_guardrails.py` ~1734 / ~2032 |
| `apply_premature_cap_for_execute` | JobRunner + driver rewrite contract | `IN_CODE` | `delivery_guardrails.py` ~2054 |
| `clamp_resume_through_order` | MUST_PRECEDE / VO-chain clamp (mostly **leapfrog** cousin) | `IN_CODE` | `delivery_guardrails.py` ~278 |
| `classify_heal_error` | Parallel fingerprint→`HealRoute` table (does not always go through `producer_pin_for_token`) | `IN_CODE` | `heal_routing.py` ~222 |
| Specialty: `voice_ref_heal_resume_stage`, `high_gap_heal_resume_stage`, `fuse_oscillation_heal_resume_stage`, `edl_heal_resume_stage`, `g0_heal_resume_stage` | Named family pins before table | `IN_CODE` | `heal_navigate` prefix + `stage_completion` |
| Driver / JobRunner execute | Call `resolve_premature_cap_pin` / `apply_premature_cap_for_execute` | `IN_CODE` | `delivery_guardrails` + callers |
| Agenda / unstick | May call `heal_navigate` / resume helpers | `IN_CODE` | `homunculus/agenda.py`, `delivery_unstick.py` |

**Declared vs actual:** Docs/Partial Zero say `producer_pin_for_token` is the family SSOT. **Actual:** token mapping is centralized there, but **navigation** still has multiple winners (`heal_navigate` specialty paths, `canonical_resume_pin`, `path_to_master_pin`, `classify_heal_error`). Tag: `CODE_DOC_CONFLICT` (SSOT claim narrower than runtime graph).

---

## 2. Failure permutations

| Case | What happens now | Honest outcome should be | Tag | Pointer |
|------|------------------|--------------------------|-----|---------|
| clean recover | Structured token → correct producer via `producer_pin_for_token` + tests | Same | `IN_CODE` | `test_pin_premature_family.py` |
| wrong target (compound mix + vo_g1) | B1: longer / non-mix wins → VO landings | VO/G1 producer, never mix-first | `IN_CODE` | `producer_pin_for_token` scored needles |
| wrong target (prose “remix”) | B2: no bare `"mix" in …` | Not mix | `IN_CODE` | B2 tests |
| wrong target (unknown class) | B3 → `transitions`, not fake stage id | Safe default | `IN_CODE` | `premature_class_pin` |
| leapfrog | Separate class; clamp on VO chain after pin | Earliest MUST_PRECEDE hole | `IN_CODE` | `clamp_resume_through_order` → clinic `leapfrog_resume` |
| hollow success | Done Authority / mark_done (other class) | Refuse hollow done | `IN_CODE` | heal-clinic `hollow_pass` |
| validate≠stage | Other class | Agree validate vs incompleteness | — | `heal_validate_stage_fail` |
| post-success budget | Other class | Reclaim / refuse≠Finished | — | `post_heal_budget_thrash` |
| Partial must-act open | Pin must not auto-accept G0/G1; may still wrong-pin away from gate work | Stay on producer that owns the gate hole | `IN_CODE` | g0 / vo_g1 specialty + Partial guards |
| Full-auto defaults | Same pin stack; automation=True rewrites execute onto pinned producer | Same honesty; no soft pin | `IN_CODE` | `apply_premature_cap_for_execute` |
| Exception fail-open in premature vo_g1 | Nested try/except → may fall to `"vo_synthesize"` | Prefer explicit fail / canonical only | `IN_CODE` | `premature_class_pin` vo_g1 branches |
| path_to_master vs token pin | After Phase A seal, music/mix intents take `path_to_master_pin` even when error blob named another producer | Single ordered pipeline | `IN_CODE` | `heal_navigate` ~2148+ |
| classify_heal_error bypass | Fingerprint table returns `from_stage` without B1 scoring | Route through shared pin helper | `IN_CODE` | `heal_routing.classify_heal_error` |

---

## 3. Already closed vs residual

| Prior DP / cousin_matrix row | Claimed closed? | Verified on HEAD? | Residual? |
|------------------------------|-----------------|-------------------|-----------|
| DP-B1 compound mix vs premature | closed | **Yes** — scored needles + matrix tests | No for that law |
| DP-B2 substring mix | closed | **Yes** — no bare stage-id substring in table walk | No for that law |
| DP-B3 unknown class as fake stage | closed | **Yes** — → `transitions` | No for that law |
| DP-B6 sole incompleteness_resume | closed | **Yes** — single `(ctx, consumer)` API | No for that law |
| DP-LAYUP-ADJ clamp (leapfrog) | closed | **Yes** — separate class | Hand off to `leapfrog_resume` |
| premature_cap ranking↔TCA / selection-missing | residual in cousin_matrix | **Partial** — `resolve_premature_cap_pin` + F7 sealed fallthrough exist; ranking↔TCA not proven closed as one matrix | **Yes — residual** |
| path_to_master / mix_seat loop | residual in cousin_matrix | **Partial** — path + seating SSOT exist; multi-navigator still possible | **Yes — residual** |
| Multi-navigator SSOT (token vs canonical vs path vs classify_heal_error) | not a closed DP | **Open on HEAD** | **Yes — primary residual for this clinic class** |

HINT only (not proof): mohan_hint_digest PIN_PREMATURE high counts on older execs; do not treat as HEAD evidence.

---

## 4. Complexity traps

- **Duplicate SSOT:** `producer_pin_for_token` vs `canonical_resume_pin` vs `path_to_master_pin` vs `classify_heal_error` — four “truths.”
- **Mode-special branches:** `apply_premature_cap_for_execute(automation=…)` changes rewrite vs hard-fail UI — pin target should stay mode-shared.
- **Heal that hides quality failure:** Landing on a wrong producer can look like “progress” while the real hole never heals → identical thrash / budget burn (feeds cousin classes).
- **Exception swallow:** `premature_class_pin` / heal paths `except: pass` then static fallback — can mask routing bugs.

---

## 5. TEST_GAP

| Behavior | Covered? | Suggested matrix test |
|----------|----------|------------------------|
| B1/B2/B3/B6 token laws | **Yes** | `tests/test_pin_premature_family.py`, `test_r4_premature.py` |
| premature_cap F7 sealed pin | Partial | `test_follow_through_hau_ssot.py` resolve_premature_cap |
| path_to_master Phase-A vs music | Partial | `test_must_precede_order`, `test_i7_hau_*`, `test_category_b_ws5_*` |
| heal_navigate + producer_pin agree on compound tokens | **Thin** | Parametrize blob → `heal_navigate.from_stage` == `producer_pin_for_token` |
| classify_heal_error vs producer_pin_for_token parity | **Gap** | Shared fixtures both APIs |
| ranking↔TCA / selection-missing premature_cap | **Gap** | Named fixture if residual confirmed |
| Partial vs Full-auto same pin for same blob | **Gap** | automation True/False only changes rewrite policy, not pin id |

---

## 6. Cousin hints (suggestions only)

- Related heal-clinic classes: **`leapfrog_resume`** (clamp after pin), **`post_heal_budget_thrash`** (wrong pin → thrash), **`hollow_pass`** (done lie after wrong land), **`heal_validate_stage_fail`** (heal “ok” on wrong producer).
- Possible bigger deterministic shared rule: **One `resolve_heal_from_stage(ctx, error, stage, intent)`** that every driver/agenda/ESR path must call — internal order: specialty allowlist → `producer_pin_for_token` → `clamp_resume_through_order` → (only then) path_to_master when intent is delivery-blocked/music/mix/finalize.

---

## 7. Ready for options?

- [x] Census complete enough for A/B/C
- [x] Surgical (narrow parity tests / one bypass) and SSOT (single navigator) both imaginable

See [options.md](options.md).
