# Chatterbox interviewer VO — gap framing path

Gap framing adds interviewer audio (questions, summaries, prefaces, story bridges) to build a **succinct master**: extracted context in host VO plus curated impact clips from source audio.

## Operator gate ladder (default: offer gap framing — Yes recommended)

| Gate | When | Default | Persisted |
|------|------|---------|-----------|
| **G-Framing** | After `source_topology_build` | **Yes** (Homunculus 0.1.0 auto-Yes on hosted 1:1; operator **No** is the off-ramp) | `run_meta.gap_framing_enabled` |
| **G-Speaker** | G-Framing = Yes | Frame-role / question-density host (never guest talk-time) | `pickup_speaker_confirmed` |
| **G-VoiceRef** | G-Framing = Yes | Auto-extracted clips | `voice_reference_approved_at` |
| **G-Delivery** | G-Framing = Yes | **Chatterbox** | `run_meta.gap_vo_delivery` |
| **G1** | After `gap_framing_recompose` (or skip-copy) | Synthesize all / record / edit | `vo_pickup/` |

Operator GUI always requires an explicit choice at each gate. Unattended / E2E runs may apply the same defaults without human input when `analysis.gap_fill.auto_accept_defaults` is true or `INTERVIEW_MUX_AUTO_ACCEPT_GATES=1`.

API: `POST /api/runs/{id}/gap-framing/enable`, `…/gap-framing/delivery`, `…/voice-reference/approve`, `…/g1/synthesize-all`.

## Succinct master artifacts

- `understanding/gap_report.json` — `interviewer_lines[]` with `line_category`, `supports_segment_ids`, `replaces_source_segments`; authoritative only after [Refinement Pass](./refinement-passes.md) `gap_framing_recompose` accepts a candidate or skip-copies the draft (flow integrity)
- `understanding/gap_framing_plan.json` — act / impact block map
- `master/selection.json` — `selection_framing_apply` (Pass 2, runs after `gap_framing_recompose`) may exclude segments with reason `covered_by_framing_vo`, coverage-guarded so no topic loses every surviving segment

## Refinement Pass (Pass 2)

`gap_framing_compose` above only produces the **draft** `gap_report`. After `full_master_ranking`, [Refinement Pass](./refinement-passes.md) confirms the L0 agenda and either recomposes the draft against the kept segment order (`gap_framing_recompose`) or skip-copies it verbatim (`refinement_flow_integrity.skip_copy_draft_to_final`) — either way `understanding/gap_report.json` is authoritative before G1, so G1 is always reachable.

## Synthesis routing

When `gap_vo_delivery=chatterbox`, G1 calls `chatterbox_runner` (`ASSETS/local_chatterbox/venv`, `tools/chatterbox_generate.py`).

**Default posture: hard-stop.** Irreparable synthesis failures (and gap-fill ineligibility while framing is Yes) abort the run with an error in `gui_log.jsonl` (Activity panel), terminal mirror (`MUX_MIRROR_OPERATOR_ERRORS`), and a `[HARD STOP]` stderr line.

Optional degradation (opt-in only):

1. **Chatterbox** zero-shot clone
2. **mlx-audio** S2S (`s2s_runner`) when Chatterbox fails — only if `gap_vo.fail_open=true`
3. **Manual record/upload** at G1 when both fail — only if `gap_vo.fallback_to_manual_on_failure=true`

With those knobs off (shipped defaults), the run stops so the operator knows what broke. Audit: `vo_pickup/synthesis_report.json`.

Gap-fill ineligibility while framing is enabled also hard-stops unless `analysis.gap_fill.auto_skip_when_ineligible=true` (legacy silent skip). Explicit operator **No** at G-Framing / Skip gap-fill remains intentional and continues without VO.

Voice reference: collated `understanding/speaker_samples/{speaker_id}.wav` from approved `understanding/voice_reference/` candidates.

See [operator-gates.md](../workflows/operator-gates.md) and [interviewer-gap/README.md](../pipeline/interviewer-gap/README.md).
