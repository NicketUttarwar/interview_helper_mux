# App-wide vulnerable-junction catalog — INDEX

**Doctrine:** Identify-only. HEAD codebase only. Brain **0.1.0**. Modes: Manual / Full-auto / Partially accelerated.  
**Forbidden:** prior `exec_*` as evidence, forensic logs as evidence, product patches, fix-oriented new tests.

**Delivered:** 2026-09-09 (catalog build). Zero intentional product code changes from this campaign.

## Provenance (Wave-A freeze)

- **campaign_id:** `FAILURE_CATALOG-2026-09-09`
- **executed_on:** 2026-09-09
- **product_patches:** false
- **status:** closed — see [CAMPAIGN_META.md](CAMPAIGN_META.md)
- **merges_into:** Wave-B RSTM (`RSTM-2026-09-09`)


## Scoring

- Likelihood: **L3** high / **L2** med / **L1** low (code-based)
- Severity: **S4** loop/wipe · **S3** stuck needs_operator · **S2** wrong/hollow master · **S1** footgun/UX
- Status: `OPEN_RISK` | `LIKELY_MITIGATED_ON_HEAD` | `UNKNOWN_NEEDS_READ`

## Family files

| File | Contents |
|------|----------|
| [stages-analysis.md](stages-analysis.md) | All 35 ANALYSIS stage cards + mastering/boundary depth |
| [stages-delivery.md](stages-delivery.md) | All 37 DELIVERY/SHIP cards + VO/mix/junction depth |
| [gates-offers.md](gates-offers.md) | Gates, offers, escalations |
| [gui-api.md](gui-api.md) | GUI + API + Partial overlay |
| [homunculus-010.md](homunculus-010.md) | Conductor, tools, dispatch, budget |
| [prompt-schema-mismatch.md](prompt-schema-mismatch.md) | Registry / prompt / schema |
| [model-tool-calls.md](model-tool-calls.md) | OpenAI + local ML call sites |
| [crosscuts.md](crosscuts.md) | Heal/thrash/staging/ship/VO |
| [mode-matrix.md](mode-matrix.md) | Manual / Full-auto / Partial |
| [config-flags.md](config-flags.md) | Env/config keys (no secrets) |
| [test-evidence.md](test-evidence.md) | Existing tests + TEST_GAP + diagnostic |
| [swarm-merge-appendix.md](swarm-merge-appendix.md) | Extra OPEN_RISK cards from parallel research agents |
| [swarm-wave2-synthesis.md](swarm-wave2-synthesis.md) | Elevated P0–P1 from late swarm (shape stub, schema hollow, mode lie, …) |
| [swarm-wave3-deep-synthesis.md](swarm-wave3-deep-synthesis.md) | DEEP stage elevates (resplit/fuse S4, STT fake diarization, junction thrash, …) |

## Ranked index

### P0 — S4/S3 × L3 (fix first later)

| ID | One-liner | Cluster |
|----|-----------|---------|
| XC-IDENT-01 | `MUX_FORENSICS` / signature rotation disables or misses identical×3 halt | `identical-halt-honesty` |
| XC-HOLLOW-01 | Most ANALYSIS stages lack `stage_artifact_incompleteness` branches | `hollow-done-coverage` |
| DEEP-RESPLIT-01 | `boundary_topic_resplit` nested class/reanchor + `clear_from` (L3/S4) | `SEG-RESPLIT-INVALIDATION` |
| DEEP-FUSE-01 | `connector_fuse_pass` unlimited rounds + economy/fallback overfuse (L3/S4) | `CONNECTOR-FUSE-THRASH` |
| DEEP-JUNCTION-01 | `junction_snip_qa` remaster budget / oscillation (L3/S4) | `junction-remaster-thrash` |
| DEEP-VO-01 | `vo_synthesize` Chatterbox/seat/G1 circular (L3/S4) | `vo-seat-authority` |
| SYN-SHAPE-01 | Research/Shape soft-gate stub; mastering prompts unwired | `research-shape-llm-cutover` |
| SYN-SCHEMA-01 / 02 | Empty `{}` skips schema; hollow `[]` arrays validate | `schema-hollow-gate` |
| SYN-DELIGHT-01 | Full-auto listen_delight auto-waiver soft-seals | `delight-authoritative` |
| DEEP-STT-01 | Single-speaker STT invents alternating `spk_0`/`spk_1` | `stt-fake-diarization` |
| DEEP-SPINE-01 | Post-G0 spine diarization rewrites `transcript/full.json` | `spine-post-g0-relabel` |
| DEEP-PROBE-01 | Audio-probe fail-open + shadow hollow goldens | `audio-probe-failopen-shadow` |
| DEEP-PRECLEAN-01 | Preclean defaults auto-run vs “never auto-run” offer rule | `preclean-auto-vs-offer` |
| DEEP-MIX-01 / MM-01 | Mix EDL overlay authority; MusicGen/MMAudio spend thrash | `mix-edl-overlay-authority` / `musicgen-mmaudio-spend-thrash` |
| STG-mastering_research-DEPTH | Research **fail-open** thin/skipped fields still progress | `hollow-done-coverage` |
| STG-vo_synthesize-DEPTH | VO script↔WAV / pending / G1 circular risk | `vo-seat-authority` |
| STG-nugget_layup-DEPTH | Layup incomplete-after-conductor | `layup-completeness` |
| GUI-START-01 | Wrong mode/brain at Start; dual driver | `start-mode-lock` |
| GUI-PIPE-01 | Manual Run-from-stage on consumer | `heal-navigate-pins` |
| GUI-OVERLAY-02 / SYN-MODE-01 | Partial overlay drift + “only G0+S3” copy lie | `partial-overlay` / `mode-gate-honesty` |
| XC-SHIP-02 | `ship_path_ready` commitment vs HEAD test failure | `junction-remaster` |
| MTL-CHATTERBOX-01 | Chatterbox + voice-ref + bind thrash | `vo-seat-authority` |

### P1 — S3/S2 × L2–L3

| ID | One-liner | Cluster |
|----|-----------|---------|
| DEEP-CUTS-01 | Ideal-cuts quality-eval fail-open writes coarse boundaries | `cuts-bind-quality-failopen` |
| DEEP-VERNACULAR-01 | Vernacular shadow + unstaged `manifest.json` write | `VERNACULAR-SHADOW-ENFORCE` |
| DEEP-SONIC-01 | Keyword sonic atlas → deferred empty palettes → heuristic policy | `SONIC-ATLAS-HEURISTIC` |
| DEEP-HITCH-01 | `chapter_close_hitch` nuclear `clear_from` mid-delivery | `invalidation-blast` |
| DEEP-AIR-01 | Air compose/seams fail-open hollow seats | `air-order-policy` |
| DEEP-VO-FIN-01 | `sound_design_vo_finalize` before synth often no-op mark_done | `vo-seat-authority` |
| DEEP-REFINE-GHOST | `*_refine` handlers are `_noop_refine` ghosts (not in DELIVERY_ORDER) | `legacy-refine-noop-ghosts` |
| SYN-PACK-01 | Conductor pack injects `stage_done` / `artifact_exists` | `llm-packet-denylist` |
| SYN-GUI-01 / 02 | Dual-advance gate POSTs; unguarded Partial mutators | `gui-dual-advance` / `partial-overlay` |
| SYN-MIX-01 | `mix_epoch_block` no-op when Phase A unsealed | `music-epoch` |
| SYN-GFR-01 | Framing posture advisory ≠ sticky Yes/No | `g-framing-authority` |
| SYN-PREPARE-01 | Partial post-G0 preclean vs G0-locked STT WAV mismatch | `partial-prepare-order` |
| SYN-SHARED-01 | Shared brief/boundaries/SDP multi-writer self-stale | `invalidation-blast` |
| XC-SEED-01 | `may_rewind` fail-open on G1 exception | `monotonic-vo` |
| XC-SHIP-01 | bare `artifact_exists(master.wav)` vs `committed_master_wav` | `committed-master-honesty` |
| XC-STAGING-01 | pending_writes shadow consumers | `pending-flush-honesty` |
| XC-INV-01 | heal-only vs structural invalidation / BD self-stale | `invalidation-blast` |
| XC-PREMATURE-02 | premature_cap exception swallow | `heal-navigate-pins` |
| XC-REMUTATE-02 | delight remutate mix-only noop risk | `remutate-chain` |
| XC-LLM-01 / SYN-RETRY-01 | llm hard-stop routing; junction/seam retries >2 | `llm-hard-stop-routing` |
| H010-DISPATCH-01 | conductor vs seed prereq | `homunculus-dispatch-prereq` |
| GATE-G0-01 / GATE-GPUB-01 | Full-auto auto-G0; Partial S3 consent honesty | `mode-gate-honesty` |
| GATE-G1-01 | skip vs seat floor | `g1-vo-seed-cycle` |
| PSM-LLM-NO-PRIMARY | LLM stages missing STAGE_PRIMARY_IDS | `prompt-schema-registry` |
| CFG-01 | soft residual meta without quality waivers | `e2e-soft-split-honesty` |

### P2 — analysis glue / mastering shape / probes

| ID | Cluster |
|----|---------|
| STG-mastering_shape-DEPTH | `research-shape-llm-cutover` |
| MTL-PROBE-01 | `audio-probe-fallback` |
| MTL-MLX-STT-01 / MTL-DFN-01 | `local-ml-venvs` |
| PSM-TBIY-DUAL / PSM-DENYLIST | `prompt-heritage-drift` / `llm-packet-denylist` |
| GATE-AIR-01 | `air-order-policy` |
| XC-AUTH-01 | `authority-undo` |

### P3 — S1 footguns / UX

| ID | Cluster |
|----|---------|
| GUI-BANNER-01 / GUI-QC-01 | `gate-banner-honesty` |
| OFFER-PRECLEAN-01 / OFFER-OPT-01 | `partial-prepare-order` / `timeline-optimizer` |
| H010-GATE-01 | `gate-banner-honesty` |

## Fix-cluster labels (for later major reviews — no implementation here)

1. `hollow-done-coverage` — incompleteness for analysis/mastering fail-open  
2. `vo-seat-authority` — seats, clamp, Chatterbox, script↔WAV, G1  
3. `identical-halt-honesty` — non-forensics halt, signature collapse  
4. `committed-master-honesty` — pending vs committed master.wav call sites  
5. `heal-navigate-pins` — premature_cap / from-stage consumer footguns  
6. `partial-overlay` — checkpoint list vs real gates  
7. `mode-gate-honesty` — Manual/Full-auto/Partial gate matrix  
8. `music-epoch` — MusicGen/MMAudio/mix deferral  
9. `junction-remaster` — remaster budget + ship_path commitment  
10. `remutate-chain` — delight/edl remutate → seams→EDL  
11. `invalidation-blast` — heal-only vs structural / unlock  
12. `homunculus-dispatch-prereq` / `homunculus-budget-ledger`  
13. `prompt-schema-registry` / `llm-packet-denylist` / `prompt-heritage-drift`  
14. `layup-completeness` / `transitions-freeze` / `monotonic-vo`  
15. `g-publish-consent` / `start-mode-lock` / `dual-driver`  
16. `research-shape-llm-cutover` — wire research router + Shape L0–L5 / critics (today soft-gate stubs)  
17. `schema-hollow-gate` — refuse empty `{}` / hollow required arrays at validate  
18. `gui-dual-advance` — gate POST must not also fire advanceFromCheckpoint race  
19. `delight-authoritative` — unattended waiver honesty vs ship floors  
20. `g-framing-authority` — posture advisory vs sticky Yes/No semantics  
21. `SEG-RESPLIT-INVALIDATION` — boundary_topic_resplit nested invalidation wipe  
22. `CONNECTOR-FUSE-THRASH` — unlimited fuse rounds + economy/fallback overfuse  
23. `junction-remaster-thrash` — junction_snip remaster budget / oscillation  
24. `stt-fake-diarization` — single-speaker invents alternating speakers  
25. `spine-post-g0-relabel` — post-G0 diarization rewrite of signed transcript  
26. `audio-probe-failopen-shadow` / `preclean-auto-vs-offer` / `cuts-bind-quality-failopen`  
27. `VERNACULAR-SHADOW-ENFORCE` / `SONIC-ATLAS-HEURISTIC` / `PALETTES-DEFERRED-EMPTY`  
28. `musicgen-mmaudio-spend-thrash` / `mix-edl-overlay-authority` / `finalize-ledger-seam-pmq`  
29. `legacy-refine-noop-ghosts` — `*_refine` handlers noop outside DELIVERY_ORDER  


## Diagnostic pytest observation (no patches)

```
pytest tests/test_partial_auto_mode.py tests/test_stage_completion.py tests/test_delivery_guardrails.py
→ 61 passed, 3 failed in combined run; isolated: test_ship_path_ready_pins_finalize FAIL
  (assert ready is True — commitment match path). Catalogued as XC-SHIP-02.
```

## Completeness checklist

- [x] Every ANALYSIS stage card (real `pipeline._*_stage_fns` call graphs; not templates)
- [x] Every ANALYSIS/DELIVERY card enriched with incompleteness hit + OPEN overlays
- [x] Every DELIVERY + SHIP stage card
- [x] Every gate/offer with mode notes
- [x] Homunculus 0.1.0 dispatch + tools
- [x] LLM prompt↔schema register
- [x] Model/local-ML call-site register
- [x] GUI/API user-action walk + Partial overlay
- [x] Cross-cuts
- [x] Ranked index + clusters
- [x] Zero product code changes (catalog markdown only)
- [x] Zero `exec_*` folders used as evidence (HEAD code/tests/docs only)



## DEEP enrichment waves

Appended after regenerating call-graph stage cards:
- Early ANALYSIS DEEP (preclean→ideal cuts)
- Mid ANALYSIS DEEP (boundaries→episode structure)
- Delivery DEEP (coverage→EDL)
- Mix/Ship DEEP (preview→publish)

All plan `stage-*` todos completed (125/125). Identify-only.

## Completion note (2026-09-09)

Per-stage plan todos were still `pending` while aggregate conversation todos showed done — because stage cards were template stubs. Regenerated all ANALYSIS + DELIVERY/SHIP cards from AST-resolved `pipeline._analysis_stage_fns` / `_delivery_stage_fns` with incompleteness hits and known OPEN_RISK overlays. Parallel DEEP enrichment agents append depth sections. Plan frontmatter stage-* todos marked completed. Identify-only; zero product patches.
