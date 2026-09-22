# DP-A3 writer census — HEAD 2026-09-21

**Mode:** research only (no product patches).  
**Scope:** `FROZEN_SEAT_DOCS` = gap_report · transitions · sound_design_plan.  
**Seat fingerprint:** seated + omitted + orientation line ids (from air_script + gap) — **not** SDP cue numbers.

## Already gated (End-A or skip-write)

| Path | Gate | Notes |
|------|------|-------|
| `commit_gap_report_doc` | `frozen_seat_write_allowed` | Skip-write when frozen + reason not End-A |
| `persist_frozen_seat_doc` | same | Used by optimizer (all 3 docs), adjudicate, hitch reattach, omit revive path, soundscape bed trim, vo_bind catastrophe |
| Optimizer promote gap/transitions/SDP | `persist_frozen_seat_doc` | Reasons `optimizer_promote_*` **not** on End-A allowlist → **skip under freeze** (A behavior already) |

## Commit helpers missing freeze gate

| Path | Issue |
|------|--------|
| `commit_sound_design_plan_doc` | No `frozen_seat_write_allowed` — SDP can rewrite under freeze via one_writer |
| `commit_transitions_doc` | Same — transitions can rewrite under freeze |

## Raw bypasses (write_json / write_committed_json — no End-A)

### gap_report (high Partial relevance if after soft freeze)
| Caller | Likely when freeze active? | Fingerprint risk |
|--------|----------------------------|------------------|
| `omit_ledger.stamp_gap_report_omit_skips` | **Yes** (post air_contract) | **High** — omit stamps; End-A name `stamp_gap_omit_flags` exists but path **bypasses** gate |
| `air_script` filtered gap write (~1325) | Soft freeze possible | **High** — omit/seat flags |
| `vo_line_adjudicate._persist` `except:` → raw write | Soft/hard | **High** — **fail-open footgun** |
| `opening_orientation` retarget | Ownership only | Medium — line target ids |
| `web/server` GUI gap write | Operator | Medium — intentional GUI |
| `junction_snip_qa` rebase after exclude | Mid-delivery | High if exclude after freeze |
| `recovery_controller` / `artifact_repairs` / `synthesis_fallback` / `refinement_passes` / `artifact_cross_validate` / `vo_contract` / `execution_contract` / `stages/assembly` | Mixed (many pre-freeze) | Medium–high if invoked post-freeze |

### transitions
| Caller | Notes |
|--------|-------|
| `transition_vo` (also has commit_transitions_doc path) | One raw retain write |
| `edl_overlap_repair` | Raw write |
| `artifact_repairs` / `recovery_controller` | Raw write |

### sound_design_plan
| Caller | Notes |
|--------|-------|
| Primary mint via `commit_sound_design_plan_doc` / one_writer | **Ungated** under freeze |
| `persist_frozen_seat_doc` callers only for verify/optimizer | Gated; non-End-A → skip |

## End-A allowlist vs real post-freeze reasons

**On allowlist (examples):** `stamp_gap_omit_flags`, `omit_ledger_revive_orientation`, packaging soft-only CTA rows, ship-omit junction/edl rows.

**Used in code but NOT allowlisted → skip under freeze today:**  
`optimizer_promote_*`, `hitch_reattach_vo`, `soundscape_bed_trim`, `catastrophe_seated_bind_synth_failed`, adjudicate `stage_key` / stage id.

## Mechanism doc BP-A3 is stale

BP-A3 table claimed optimizer transitions/SDP and `commit_gap_report` ungated — **HEAD already gates optimizer + gap commit**. Remaining honesty debt is **bypass raw writes** + **ungated SDP/transitions commit** + **fail-open adjudicate** + **allowlist ↔ reason mismatch**.

## Implication for options

- Pure **A** (every persist End-A or skip): still correct spine, but must close bypasses or A is theater.
- Pure **B** (fingerprint-only): matches fingerprint definition (SDP cues ≠ seat hash) — good for cue trim; does **not** fix raw bypasses alone.
- Pure **C**: leave ownership — freeze remains paper for bypass paths.
- **Defer** census: **done** — no longer needed as a pause.

## Recommended custom (A′)

1. **Choke-point:** all FROZEN_SEAT_DOCS disk writes → `persist_frozen_seat_doc` or `commit_*` that call `frozen_seat_write_allowed` (kill raw bypasses; add gate to SDP + transitions commit).  
2. **Fingerprint rule:** under freeze, if write would change `seat_fingerprint` → End-A or skip-write.  
3. **Metadata slice (B):** cue-level / dens / non-seat SDP fields may persist with ownership when fingerprint unchanged.  
4. **Fix fail-open:** adjudicate `except` must not raw-write under freeze.  
5. **Allowlist pass:** either add named End-A rows for must-land paperwork (`hitch_reattach_vo`, catastrophe unseat, …) or keep skip and document.
