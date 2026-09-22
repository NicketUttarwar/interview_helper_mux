# Cut economics ledger

| Unit (phase/stage/path) | Bug recurrence | Thrash tax | Cousin surface | Benefit Partial | Replaceability | Tentative | Linked DP |
|-------------------------|----------------|------------|----------------|-----------------|----------------|-----------|-----------|
| `sound_design_vo_finalize` (standalone seed) | Low–med (ESR vo_wavs HINT) | Medium pin/wait surface | VO / ESR cousins | Low unique vs synth+EDL fold | High — fold into synth exit or EDL prep | **CUT_CANDIDATE** | (open with build analysis; no DP yet — fold into future DP-BUILD-VO-FINALIZE if operator wants) |
| Dual `assembly_preview` + full `mix` renders | High (seating storms HINT) | High wall-clock / GPU | J-assembly-freshness | High if unified | Medium–hard refactor | **SIMPLIFY / CUT_CANDIDATE** (dual path) | DP-BUILD-ASSEMBLY-FRESHNESS (Option C) |
| Pre-mix `listen_delight_audit` + ship authoritative dual | Med | Medium seal complexity | J-phase-a-seal | Med | Medium | **SIMPLIFY** | (defer ship/phase-a DP) |
| `junction_recut_precedes_mix` A1-1 unmarked-mix heuristic | High MIX_JUNCTION | High mix⇄junction | J-mix-junction-precede | High if narrowed | Keep stage; SIMPLIFY predicate | **SIMPLIFY** (predicate) | DP-BUILD-MIX-JUNCTION |
| mix “refuse log” then `mark_done` | High HOLLOW HINT i11 | Remaster inherit | J-hollow-done | High | KEEP mix; SIMPLIFY stamp | **SIMPLIFY** | DP-BUILD-HOLLOW-MIX |
