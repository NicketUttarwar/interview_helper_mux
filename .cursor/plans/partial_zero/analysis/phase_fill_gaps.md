# Phase analysis — fill_gaps

brain: 0.2.0 | mode: partially_accelerated | code_is_king: true  
stages SSOT: `src/interview_mux/v2/phases.py` (`fill_gaps`)  
clinic maps: hints only (verified against HEAD where cited)

## Level 1 — Stage solo

| Stage | Open routes (HEAD) | Thrash? | Notes |
|-------|--------------------|---------|-------|
| `missing_framing` | G-Framing pending → `maybe_auto_accept_gap_gate_defaults` **or** `require_gap_framing_decision_clear` SystemExit; Yes + ineligible → loud fail unless auto_skip; batch_fill leftovers refuse done; coverage CAP seal | Yes | Arms pickup / voice-ref / delivery via auto-accept when `analysis.gap_fill.auto_accept_defaults` (default true). Partial shares this stack (docs: same as Full-auto except G0/S3). Ladder SSOT: `vo_path_ready`. |
| `mastering_plan_confirm` | Soft confirm / provisional plan; skip when gap-fill skipped | Low | Bridge into compose; not VO mint. |
| `gap_framing_compose` | Skip stub if gap-fill skipped; layup-authority / seat freeze → no-op heal; OpenAI compose + high_gap fill; hollow report incompleteness | Yes | Dual SSOT with later layup `gap_report` writers (plan_rank). Does **not** wait G1. |
| `delivery_brief_build` | Soft inputs; LLM brief | Low | Downstream of compose. |
| `soundscape_policy_build` | Policy JSON; soft | Low | Feeds sound later; not Partial VO gate. |
| `episode_structure_compose` | Structure LLM | Low | Journey packing. |
| Gate `g1_vo_pickup` | Optional journey gate; Chatterbox + Partial driver → `automation_pending` / `operator_must_act=False` (HV-5); record delivery still hard_block; `vo_path_ready` hard 409 on synthesize-all | Medium | Phase lists G1 here, but **authoritative gap_report + WAVs land after layup/recompose** (plan_rank / build). Gate can show before lines exist. |

## Level 2 — Group

- Internal order / done agreement: ANALYSIS_ORDER keeps missing_framing → plan_confirm → gap_framing_compose → brief/policy/structure. Done requires framing decision clear when path enabled; compose may heal with empty-ish lines then layup (plan_rank) rewrites `gap_report`.
- Candidate SIMPLIFY / CUT: collapse brief+policy+structure if Partial never needs them before ranking (cut economics later). Do **not** CUT missing_framing / compose — they are the VO ladder entry.
- Partial posture: framing/pickup/voice-ref often **auto-stamped**; G1 itself is non-blocking for Chatterbox under Partial (automation_pending). Honesty risk: stages advance while `vo_path_ready` false or wavs=0.

## Level 3 — Handoffs

| Edge | Ready meaning | Cousin risk |
|------|---------------|-------------|
| understand-c → `missing_framing` | Topology + mastering plan present; G-Framing decidable | Auto-accept vs operator No sticky (docs Layer 1) |
| `gap_framing_compose` → plan_rank layup | `understanding/gap_report.json` exists (may be thin) | Dual-writer gap_report; layup invalidates compose-era lines |
| fill_gaps gate G1 → build `vo_synthesize` | Journey “optional”; real WAV close is synth + G1 helpers | VO_LADDER_PARTIAL — gate clear ≠ ladder complete |
| nested EDL/transition resync → fill_gaps ladder | `nested_synth_may_mint` consults `vo_path_ready`; Partial never nested auto-accept | Skip leaves missing WAVs for G1/synth (intended) |

## Level 4 — Junctions

| Junction id | Fact | Callers | Linked DP |
|-------------|------|---------|-----------|
| `J-vo-path-ready` | Single readiness predicate for compose / G1 synth / Chatterbox / nested mint | `gap_vo_gates.vo_path_ready`, `require_vo_path_ready`, `nested_synth_may_mint`, `operator_gate_view`, runners | DP-VO1 |
| `J-nested-synth-mint` | Nested Chatterbox from EDL/transitions must not stamp Partial gates | `stages/assembly.resync_required_synthesize_wavs`, `transition_vo.resync_spoken_transitions` (+ synth path) | DP-NESTED-SYNTH |
| `J-gap-report-writers` | Compose + layup + adjudicate + recompose share gap_report authority | fill_gaps compose; plan_rank layup/recompose; sound adjudicate | DP-LAYUP-ADJ (order); DP-VO1 (seal) |

## Decision Packets drafted

- DP-VO1 — VO ladder honesty under Partial (auto-accept vs must-act vs degrade)
- DP-NESTED-SYNTH — Nested mint skip-not-stamp vs block vs Partial auto-accept
- DP-LAYUP-ADJ — primarily plan_rank→sound; listed because compose/G1 handoff feeds it

## Partial impact

Without DP-VO1 / DP-NESTED-SYNTH verdicts, Partial can auto-stamp framing yet still hit wavs=0 / identical VO storms (HINT VO_LADDER_PARTIAL), or skip nested mint and never reclaim WAVs if synth/G1 pins disagree. fill_gaps alone cannot prove ironclad Partial.
