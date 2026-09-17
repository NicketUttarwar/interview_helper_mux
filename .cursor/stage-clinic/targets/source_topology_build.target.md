# Target Spec — source_topology_build

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| hard `understanding/speakers.json` + readable `transcript/full.json` | write topology + flow_adaptation → mark_done (HU-4 both files) | Completes seed stage unattended |
| prior adaptation has confirmed pickup | preserve pickup id + operator_overrides across rebuild | No re-prompt; keeps prior confirm |
| speaker samples missing | still done (samples skip-only per HU-4) | Continues |
| hollow / weak speakers | classify still writes topology (may be weak pickup) | Completes; quality risk downstream, not stall |
| missing speakers or transcript | hard fail on `read_json` — no done | Honest halt |
| post-write `maybe_auto_confirm_pickup_speaker` | **today:** almost always no-op mid-seed (`check_pickup_speaker_pending` needs all stages before `missing_framing` done) | Real auto-confirm lives in `maybe_auto_accept_gap_gate_defaults` at framing |
| Partial: pickup unconfirmed | stage done OK; later `require_pickup_speaker_clear` / GUI before gap eval | Partial may wait — OK |
| Full-auto + defaults (`auto_accept_defaults=false`) | topology done; pickup confirmed later via **homunculus** auto_resolve path (not topology-local) | Must not add new topology-time human stall |
| Full-auto driver (`INTERVIEW_MUX_AUTO_ACCEPT_GATES=1`) | same + gap auto-accept path confirms host pickup | Completes gap path |

## Rules set (prefer deterministic)

- admit / when speakers.json + transcript/full.json readable
- refuse / missing those inputs
- wait_for_gate / never **inside** this stage body for seed completion
- incomplete / missing topology **or** flow_adaptation (HU-4); samples never required for done
- precise invalidate / prefer ownership/ADG rails over stale long YAML list (verify clear_from on rewrite)
- auto_resolve_default / pickup confirm belongs to gap-gate helper under Full-auto/homunculus — do not invent a second topology-only confirm that breaks Partial G-Framing UX

## Complexity subtraction list

- Dead call: `maybe_auto_confirm_pickup_speaker` at end of `run_source_topology_build` (pending predicate cannot be true mid-seed) — keep single SSOT in `gap_vo_gates.maybe_auto_accept_gap_gate_defaults`
- Contract `volley_retry` on non-LLM classify stage
- Contract lifecycle `llm_execute` noise
- Contract soft `transcript/full.json` while body hard-reads it
- Contract `invalidates_stages` includes retired/alias `optimal_questions`
- Dual pickup fields on topology vs flow_adaptation — keep sync via `_apply_pickup_speaker`; do not add a third confirm flag

## Contract / dependency deltas (proposed; not applied)

- Mark transcript hard (or keep soft only if fail-open path added — prefer hard to match code)
- Drop `volley_retry`; keep host rerun
- Refresh invalidates list to live stages only (drop `optimal_questions` alias unless still a clear_from target)
- Soft `ingest/normalized.wav` only if sample extraction needs it — document optional samples

## Non-goals

- Topology class / TBIY conformance scoring quality
- GUI speaker-sample listening UX
- Changing G-Framing Yes/No authority (operator-gates)
- Local heavy ML

## Acceptance checks

- Both `source_topology.json` and `flow_adaptation.json` present after done; HU-4 incompleteness if either missing
- Samples absent → incompleteness None
- Rebuild preserves `pickup_speaker_confirmed` overrides when prior adaptation had them
- Mid-seed: topology stage completes without requiring pickup confirm
- Pickup confirm under Full-auto happens via gap auto-accept / homunculus, not fake topology-time success
- After STB-B1: no `volley_retry` in contract

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| STB-B1 | P1 | unambiguous | Drop contract `volley_retry`; host rerun only | dependency data + verify | 2 | no |
| STB-B2 | P2 | unambiguous | Drop `llm_execute` lifecycle noise | contract generator | 2 | no |
| STB-B3 | P1 | unambiguous | Remove or relocate dead `maybe_auto_confirm_pickup_speaker` call from topology body (SSOT = gap_vo_gates) | pytest: topology done without pending; gap path still auto-confirms | 2,3,7 | **yes** if pickup auto stops firing entirely |
| STB-B4 | P1 | unambiguous | Contract: treat `transcript/full.json` as hard input (matches `build_topology_artifacts`) | dependency data + stage_input_checks | 2 | no |
| STB-B5 | P2 | unambiguous | Prune stale `optimal_questions` from invalidates list (or map to live alias) | contract + ADG verify | 2,7 | no |
| STB-B6 | P1 | needs_you | Under shipped defaults (`auto_accept_defaults=false`), is homunculus-only pickup confirm at framing enough for campaign DoD, or must topology/env path change? | defaults inventory + Full-auto driver vs GUI Start | 3,5 | **yes** if flipping `auto_accept_defaults` default true |

## Defaults inventory impact

- Rows touched: Stage-local landmine — topology-time pickup auto-confirm is a no-op; unattended pickup depends on `INTERVIEW_MUX_AUTO_ACCEPT_GATES` **or** 0.2.0 homunculus auto_resolve at missing_framing (`gap_vo_gates`)

## target_status

`draft`
