# Test evidence map (existing HEAD tests only)

Identify-only. **Do not author new fix tests in this campaign.**

## Well-covered junctions (existing tests)

| Finding cluster | Example tests |
|-----------------|---------------|
| premature-cap / music epoch / filter | `tests/test_delivery_guardrails.py`, `tests/test_thrash_edge_cases.py`, `tests/test_delivery_thrash_hardening.py` |
| sticky heal / force-done / path-to-master | `tests/test_thrash_edge_cases.py`, `tests/test_major_thrash_hardening.py` |
| identical failures / forensics suppress | `tests/test_unattended_reliability.py` |
| heal routing | `tests/test_heal_routing.py`, `tests/test_heal_playbook_shape.py` |
| recovery / seed-order | `tests/test_recovery_controller.py`, `tests/test_delivery_recovery.py` |
| mark-done / incompleteness | `tests/test_stage_completion.py`, `tests/test_stage_completion_heal.py` |
| Partial mode | `tests/test_partial_auto_mode.py`, `tests/test_partial_auto_prepare_order.py`, `tests/test_partial_auto_golden_path.py`, `tests/test_partial_auto_driver_recovery.py`, `frontend/.../partialAcceleratedGuard.test.ts` |
| junction / HDT | `tests/test_junction_snip_qa.py`, `tests/test_hdt_remaster_research.py` |
| authority undo | `tests/test_sanitize_authority_thrash.py` |
| execution flow | `tests/test_execution_flow_hardening.py`, `tests/test_llm_flow_hardening.py` |

## TEST_GAP — high value

| Gap | Related findings |
|-----|------------------|
| Most ANALYSIS stages lack incompleteness/heal tests | XC-HOLLOW-01, mastering_* stages |
| `artifact_exists("master/master.wav")` call-site audit vs `committed_master_wav` | XC-SHIP-01 |
| `may_rewind` fail-open on G1 exception | XC-SEED-01 |
| ALL_LLM stages missing STAGE_PRIMARY_IDS (`episode_meta_build`, `episode_cover_prompt_craft`, `synthetic_framing_plan`) | PSM-LLM-NO-PRIMARY |
| GUI gate panel double-submit / overlay exception matrix | GUI-OVERLAY-01, GUI-GATES-01 |
| Driver remutate_protect covering all restamp sites | XC-REMUTATE-01 |
| Config soft residual flags without quality waivers | CFG-01 |
| Prompt `.tbiy` vs current loader selection | PSM-TBIY-DUAL |

## Optional diagnostic pytest (observation only)

Ran on HEAD during catalog build:

```bash
pytest tests/test_partial_auto_mode.py tests/test_stage_completion.py \
  tests/test_delivery_guardrails.py -q --tb=no
```

**Result:** 61 passed, **3 failed** in combined session; isolated re-run → only  
`test_ship_path_ready_pins_finalize` fails (`ready is True` expected; commitment match keeps False).  
Catalogued as **XC-SHIP-02** — product/test skew; **no patch** in this campaign.

```bash
pytest tests/test_delivery_guardrails.py tests/test_delivery_thrash_hardening.py \
  tests/test_partial_auto_mode.py tests/test_stage_completion.py \
  tests/test_heal_routing.py -q --tb=no
```
