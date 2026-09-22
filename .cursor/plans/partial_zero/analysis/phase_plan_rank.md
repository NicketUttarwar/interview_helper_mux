# Phase analysis — plan_rank

brain: 0.2.0 | mode: partially_accelerated | code_is_king: true  
stages SSOT: `src/interview_mux/v2/phases.py` (`plan_rank`)  
clinic maps: hints only (verified against HEAD where cited)

## Level 1 — Stage solo

| Stage | Open routes (HEAD) | Thrash? | Notes |
|-------|--------------------|---------|-------|
| `topic_coverage_audit` | LLM audit; soft holes | Low | Feeds narrative. |
| `narrative_arc_plan` | LLM arc; freeze cousins elsewhere | Medium | Selection meaning; not VO mint. |
| `chapter_close_hitch` | Hitch QC / incompleteness specialize | Medium | Can remutate seats; feeds ranking. |
| `connector_fuse_pass_pre_ranking` | Fuse before rank | Low | |
| `full_master_ranking` | Rank + selection pressure | Medium | Upstream of sanitize. |
| `selection_order_sanitize` | Unsanitary → refuse done; consumers pin sanitize | Yes | MUST_PRECEDE producer for air_script. |
| `air_script_compose` | Pass-A/B hollow seats incompleteness | Yes | Dual with seams. |
| `nugget_corpus_mine` | Soft-empty corpus | Medium | Layup input. |
| `information_package_plan` | IP plan | Low | MUST_PRECEDE for layup. |
| `nugget_layup_compose` | QC floors / shards (`auto_complete=False` then heal); CTA commit; selection_unsanitary → sanitize; escalation JSON blocks VO | **Hot** | Publishes authoritative `gap_report` when framing on; ADG invalidates recompose/transitions/VO/EDL. G8 / premature_cap pin VO→layup when incomplete. |
| `gap_report_sanitize` | After layup | Medium | MUST_PRECEDE for recompose. |
| `refinement_agenda` | Agenda seed | Low | |
| `gap_framing_recompose` | Pass-2 vs compose; skip-copy paths | Yes | HEAL_ONLY_PRODUCER; can churn gap text before adjudicate. |
| `selection_framing_apply` | Apply framing to selection | Medium | |
| `air_script_seams` | Hollow seats / contract drift | Yes | |
| `air_contract_sanitize` | Contract seats | Medium | Soft freeze window before hard freeze. |
| `transitions` | LLM transitions + pair freeze; may mint nested spoken later via EDL resync | Yes | MUST_PRECEDE: air_contract + layup. Invalidates SDP / adjudicate / synth / EDL. End stamps pair_freeze when G1 skipped/green. |

## Level 2 — Group

- Internal order / done agreement: HEAD `MUST_PRECEDE` encodes layup → gap_report_sanitize → recompose → framing_apply → seams → air_contract → transitions. Ranking/sanitize precede air_script/layup. `vo_synthesize_stability_block` (G8) additionally requires seed-complete layup + transitions (+ not stale-from-layup) before Chatterbox batch.
- **Cross-phase:** `vo_line_adjudicate` lives in **sound** (`phases.py`), not plan_rank, but MUST_PRECEDE ties it after `sound_design_plan` ← transitions. Partial thrash often reads as “plan_rank vs sound” ping-pong (HINT: layup / transitions / adjudicate / synth).
- Candidate SIMPLIFY: merge sanitize+recompose adjacency if dual gap_report writers shrink; CUT only if Partial native-only skip framing (operator DP). Keep layup if framing Yes — coverage floors are product.

## Level 3 — Handoffs

| Edge | Ready meaning | Cousin risk |
|------|---------------|-------------|
| fill_gaps compose → `nugget_layup_compose` | gap_report may exist; layup may rewrite | Dual SSOT; invalidation storm |
| `nugget_layup_compose` → `transitions` | Layup seed-complete + air_contract | Stale `invalidated_by:nugget_layup_compose` on transitions/gap |
| `transitions` → sound `sound_design_plan` | transitions.json + seed-complete | Premature SDP / cue_slots (other family) |
| plan_rank → sound `vo_line_adjudicate` | SDP then adjudicate per MUST_PRECEDE | Synth-before-adjudicate identical storms (HINT exec_13163) |
| layup/transitions → `vo_synthesize` | G8 stability block tokens | premature_cap VO_G1 → layup; PIN cousins |

## Level 4 — Junctions

| Junction id | Fact | Callers | Linked DP |
|-------------|------|---------|-----------|
| `J-must-precede-vo-chain` | Consumer may not run ahead of incomplete producers | `delivery_guardrails.MUST_PRECEDE`, `defer_until_producers_ready`, agenda reinject, `filter_delivery_candidates` | DP-LAYUP-ADJ |
| `J-vo-synth-stability-g8` | Chatterbox waits layup/transitions stability | `vo_synthesize_stability_block`, runtime/agenda/thrash | DP-LAYUP-ADJ, DP-VO1 |
| `J-layup-invalidate-cascade` | Layup ADG marks transitions/gap/VO stale | artifact ownership / invalidate_downstream; G8 stale reason parsers | DP-LAYUP-ADJ |
| `J-nested-synth-mint` | Transitions/EDL nested mint vs ladder | `transition_vo`, `assembly.resync_*` | DP-NESTED-SYNTH |

## Decision Packets drafted

- DP-LAYUP-ADJ — Enforce / move / cut adjudicate relative to layup seal
- DP-VO1 — Ladder-complete vs advance (feeds G8 / G1 pins from this phase)
- DP-NESTED-SYNTH — Transitions-era nested mint policy

## Partial impact

plan_rank is the densest Partial thrash surface before expensive VO/MusicGen: layup QC + invalidation + transitions freeze + cross-phase adjudicate order. Without DP-LAYUP-ADJ (and VO1), Partial cannot stay unattended through ranking→sound→synth.
