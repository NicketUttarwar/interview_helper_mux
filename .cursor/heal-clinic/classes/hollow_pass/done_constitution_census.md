# Done Constitution + Land Honesty v2 censuses — hollow_pass

status: shipped_land_honesty_v2  
updated: 2026-09-24  
code_is_king: true

## Exception tables (Done Authority)

| Table | Location | Purpose |
|-------|----------|---------|
| `GATE_MARKER_ONLY` | `done_authority.py` | Operator gates may stamp without primary |
| `RAW_STAMP_ALLOW` | `done_authority.py` | Reasons allowed for `_mark_done_raw` session |
| `POST_MASTER_BACKFILL_ALLOW_ALL_PRE_MASTER` | `done_authority.py` | Pre-master delivery backfill iff `stage_outputs_present` |
| `SHARED_PATH_PRODUCER_STAGES` | `done_authority.py` | Promote/seed need matching `_meta.producer_stage` (empty/missing also unpaid) |
| `LAYUP_AUTHORITY_STAGES` | `done_authority.py` | Authority-without-plan unpaid land |

## Land Honesty APIs

| API | Role |
|-----|------|
| `unpaid_land_reason(ctx, stage)` | Sole unpaid-obligation reason (remaster, remutate, stamp-alone, shared-path) |
| `unpaid_land_blocks_promote` | Promote choke before `heal_or_refuse_mark` |
| `land_honest` | unpaid clear ∧ seed-complete |
| `may_skip_as_complete` / `may_clear_wait` | Advance / ESR → `land_honest` |

## Writer census (`.stage_done` touches)

| Family | Site | Must use Done Constitution | B+ / v2 wiring |
|--------|------|----------------------------|----------------|
| Normal stamp | `RunContext.mark_done` | yes | IN_CODE — ownership + incompleteness |
| Recommended API | `done_authority.try_mark_done` | yes | IN_CODE |
| Heal mark | `heal_or_refuse_mark` | yes | IN_CODE — `raw_stamp_session` + outputs gate |
| Seed-order restamp | `apply_seed_order_heal` | yes | IN_CODE — `honest_restamp` |
| Post-master backfill | `backfill_delivery_holes_after_master` | yes | IN_CODE — `may_post_master_backfill` |
| Orphan promote | `promote_complete_orphan_stage_done` | yes | via heal + **`unpaid_land_blocks_promote`** |
| Hollow escalate | `hollow_done_guard.escalate_hollow_done` | detect only | IN_CODE — G3 batch + forensics artifact (no stamp) |
| Test fixture | `tests/run_fixtures.mark_done_raw` | test-only | RAW allow `test_fixture` |

Permanence lint: `tests/test_land_honesty_census_permanence.py` (+ `tools/land_honesty_census_lint.py`).

## Advance census (skip / wait / schedule)

| Family | Site | Was | Land Honesty v2 |
|--------|------|-----|-----------------|
| Analysis / delivery plan skip | `pipeline` | `may_skip_as_complete` | → `land_honest` |
| Shared analysis chain | `shared_analysis_chain_complete` | bare `is_done` | `may_skip_as_complete` |
| Gap spine freeze | `run_analysis` gap path | bare `is_done` | `may_skip_as_complete` |
| ESR wait clear / land | `may_clear_wait` / ESR walk | seed or outputs | **seed-complete / land_honest only** |
| MUST_PRECEDE | `producer_ready` | seed + primary | + unpaid via incompleteness |
| Mix live authority | `live_producer_authority("mix")` | any assembly.wav | seated ∧ not remaster unpaid |
| Hollow escalate | `hollow_done_guard` | — | **DETECTION** — `done ∧ ¬land_honest` |

Bare `is_done` remaining for **DETECTION** (hollow unmark, promote inverse, GUI, `hollow_done_guard`, homunculus remaining) is intentional — lint `DETECTION_ONLY`.

## Thin incompleteness (XC-HOLLOW-01)

| Gate | Location |
|------|----------|
| Empty / zero-byte / empty-object primary | `stage_completion._primary_artifact_thin_incompleteness` |
| Unpaid land first | `stage_artifact_incompleteness` → `unpaid_land_reason` |
| FORCE_DONE_GUARDED | `thrash_hardening.py` — force must pass incompleteness |

## Semantic stamp registry (non–Cluster-C)

| Stamp | Clear / incompleteness |
|-------|------------------------|
| `nugget_layup_authority` without plan | compose clear + `artifact_repairs` clear + unpaid_land |
| Empty/thin plan as ownership | compose requires contentful plan |
| Flap / freeze force-mark | refuse when unpaid / incompleteness open |

## R residuals checklist

| ID | Status |
|----|--------|
| R1 restamp | done — `honest_restamp` |
| R2 raw stamp | done — `raw_stamp_session` |
| R3 backfill | done — outputs required |
| R4 producer_ready | done |
| R5 advance | done — land_honest |
| R6 stage matrix | `test_land_honesty_disk_mapped_hollow` + census permanence cardinality |
| R7 FORCE_DONE | extended |
| R8 mode parity | done |
| Land Honesty remaster | done — ownership until `clear_remaster` |
| Thin incompleteness | done — `_primary_artifact_thin_incompleteness` |
