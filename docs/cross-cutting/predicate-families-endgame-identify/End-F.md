# End-F identify (sidecar)

- **Family:** Ship score honesty
- **Status suggestion:** partial
- **Plain-language failure:**
  Ship PMQ can still fail or greenwash on clarity / omit inputs that do not match live unresolved autopsy + air-contract state. Hint exec_11630 surface: `post-master quality failed: scorecard_dimension_floors, omit_ledger_air_contract` at `master_finalize`. i25 fixed two concrete lies (omit order-lock rebuild under seat freeze; applied leftover repairs no longer tank `_pack_conflicts` / clarity), but HEAD still (a) classifies `scorecard_dimension_floors` as aspirational/rubric and e2e-soft-waivable, (b) lets `require_publishable` re-evaluate without rebuilding live autopsy, and (c) lacks an end-to-end `MUX_FORENSICS=0` fixture through finalize → PMQ for those predicates.
- **Example predicates:**
  - `scorecard_dimension_floors` (often `clarity` via autopsy `information_clarity`)
  - `scorecard_overall_floor`
  - `omit_ledger_air_contract` (incl. `omit_ledger_order_lock_stale`)
  - `post-master quality failed: scorecard_dimension_floors, omit_ledger_air_contract` (hint exec_11630 / `LoudStageFailure` at `master_finalize`)
  - Cousins (not End-F core): `pmq_not_publishable` / `ship_path_ready` (HPUB-1); `seam_autopsy_blocking` (HX-3)
- **Producer stage(s):**
  `master_finalize` (heal omit → master wav → `run_post_master_quality`), `post_master_quality`, upstream clarity writer `junction_snip_qa` / `seam_autopsy.build_autopsy`, omit authority via `omit_ledger` heal/rebuild
- **HEAD proof (file:function):**
  - `post_master_quality.py:evaluate_post_master_quality` — emits `scorecard_dimension_floors` / `omit_ledger_air_contract`; e2e soft can force-pass scorecard floors when `master/master.wav` exists (`e2e_softened`).
  - `post_master_quality.py:build_listener_scorecard` — maps on-disk autopsy `information_clarity` → scorecard `clarity`; does **not** recompute `_pack_conflicts`.
  - `post_master_quality.py:run_post_master_quality` — rebuilds `build_autopsy(phase="post_master")` then evaluates (honest path).
  - `post_master_quality.py:require_publishable` — may call `evaluate_post_master_quality` **without** `build_autopsy`, so stale clarity / pack_conflicts can greenwash or falsely fail.
  - `aspirational_quality.py:STRUCTURAL_PMQ_CHECKS` / `RUBRIC_GATE_IDS` / `RUBRIC_PMQ_CHECKS` — `omit_ledger_air_contract` is structural; `scorecard_dimension_floors` / `scorecard_overall_floor` are **rubric** → aspirational ship can set `publish_allowed: true` with failed clarity floors.
  - `omit_ledger.py:air_contract_errors` — missing ledger → `[]` (tolerate pre-ledger runs); stale lock still emits `omit_ledger_order_lock_stale` until heal/rebuild.
  - `omit_ledger.py:heal_omit_ledger_air_contract` — order-lock rebuild runs **before** freeze gate (i25); other healables under freeze return `seat_freeze_blocked_heal*` and leave PMQ failing (stuck-fail cousin).
  - `seam_autopsy.py:_pack_conflicts` — unresolved-only filter in place (applied leftovers skipped); constitutional Q still open whether applied leftovers should be soft advisory.
  - `seam_autopsy.py:build_autopsy` — `information_clarity` uses `pack_n = len(_pack_conflicts(...))` (conflict **row** count, not unresolved-id weight) → severity under-count possible.
  - `stages/mastering.py:run_master_finalize` — calls `heal_omit_ledger_air_contract` then later PMQ block path; no fixture proves freeze + live pack conflicts through this chain.
- **Likely code:**
  `post_master_quality.py`, `omit_ledger.py`, `seam_autopsy.py`, `stages/mastering.py` (`run_master_finalize`), `aspirational_quality.py`, `quality_status.py` (ship envelope coerce — F6 reuse only)
- **Reuse / gap vs F*/H*:**
  - **F6 (closed):** ship envelope vocab — allowed ships write disk `pass` (never `advisory_fail`); finalize does not loud-fail allowed rubric; non-aspirational omits rubric misses. Fixture: `tests/test_f6_pmq_ship_schema.py`. **Does not** prove clarity floors or omit air-contract honesty.
  - **HPUB-1 (closed):** `ship_path_ready` under e2e_soft when `publish_allowed` false; unreadable PMQ fail-closed; remote still needs `publish_allowed`. Fixture: `tests/test_hpub1_ship_path_pmq.py`. Local walk ≠ score honesty; no scorecard/omit input asserts.
  - **HX-3 (closed):** pre_mix reads live `blocking_reasons` from master autopsy. Fixture: `tests/test_hx3_premix_autopsy.py`. Different gate; no `_pack_conflicts` / clarity-floor coverage.
  - **HX / End-D:** mix/junction seating — adjacent delivery seal, not PMQ score honesty.
  - **i25 partial:** `tests/test_i25_pmq_omit_clarity.py` — unit: unresolved-only `_pack_conflicts`; omit order-lock rebuild under hard freeze. **Gap:** no PMQ evaluate/finalize integration; no aspirational/e2e soft clarity assertion; no `require_publishable` stale-autopsy case.
  - **Do not mark superseded** — End-F remains the ship-score honesty layer above closed F6 / HPUB-1 / HX-3.
- **Policy questions (1–3, unanswered):**
  1. Clarity / pack conflicts: unresolved-only forever, or also count applied leftovers as soft advisory (score nudge / advisory check, not hard fail)?
  2. Should `scorecard_dimension_floors` (esp. `clarity`) stay aspirational/rubric, or become structural like `omit_ledger_air_contract` for production ships (fail closed without forensics / e2e waiver)?
  3. Must every PMQ evaluate path that reads clarity rebuild autopsy first (`require_publishable` / recovery), or is finalize-only refresh enough?
- **Fixture gap (what MUX_FORENSICS=0 test is missing):**
  i25 covers only unit `_pack_conflicts` + omit order-lock rebuild under freeze. Still missing under `MUX_FORENSICS=0`: (a) `evaluate_post_master_quality` / `run_post_master_quality` asserting `scorecard_dimension_floors` from **live** unresolved pack conflicts; (b) applied leftovers do **not** fail clarity floors at PMQ; (c) `run_master_finalize` (or equivalent) under seat freeze with stale omit lock → omit check passes after heal; (d) `require_publishable` / evaluate-without-rebuild stale-autopsy case; (e) aspirational-on clarity floor fail → advisory vs hard publish; (f) explicit non-soft production path: floors fail closed (no e2e waiver).
- **One-line summary:** i25 fixed freeze omit-lock + live pack conflicts; End-F stays partial until PMQ clarity/omit honesty is fixture-proven through finalize without soft greenwash.
