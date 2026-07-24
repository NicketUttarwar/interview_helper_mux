# Mastering feasibility compiler

Deterministic gate proving a candidate plan **can actually be built** before it costs auditions, critics, or a master. Canon: [mastering-quality-hardening.md](./mastering-quality-hardening.md).

**Principle:** no LLM judgement here. Every check is mechanical and reproducible.

Module: `src/interview_mux/mastering_feasibility.py` · Artifact: `mastering/shape/feasibility.json`

---

## Checks

| Check id | Severity | Rule |
|----------|----------|------|
| `segment_exists` | blocking | Every referenced `segment_id` exists in the segment manifest |
| `segment_bounds` | blocking | Referenced start/end lie inside the source timeline |
| `vo_line_exists` | blocking | Referenced VO line ids exist in the gap report |
| `vo_audio_or_synth` | blocking | Each planned VO has a recorded WAV or an available synthesis path |
| `sfx_cue_exists` | blocking | Referenced SFX cue refs exist in SDP / asset catalog |
| `pickup_voice_authorized` | blocking | VO speaker is the pickup-eligible speaker and clone policy passes |
| `speaker_volley_integrity` | blocking | No locked speaker volley is split by the plan |
| `duration_fits` | blocking | Sum of included durations lands inside the plan's target band |
| `timeline_collision` | blocking | No two elements claim the same timeline slot |
| `edl_representable` | blocking | Cold open + body + close map onto the EDL clip model |
| `cold_open_source` | blocking | `segment_hook` cites a real segment; `vo_clone_*` cites a real line |
| `duplicate_segment` | warn | Segment used twice without `reprise_later` |
| `asset_duration_slack` | warn | Bed/stinger shorter than the region it must cover |
| `thin_evidence` | warn | Decision cites no evidence refs |

`blocking` failures make the candidate ineligible for auditions, L4, and synthesize. `warn` findings travel with the candidate as context for critics.

---

## Output

```json
{
  "version": 1,
  "candidates": [
    {
      "candidate_id": "cand_1",
      "verdict": "pass",
      "checks": [
        { "check_id": "segment_exists", "severity": "blocking", "passed": true }
      ],
      "blocking_reasons": [],
      "warnings": ["duplicate_segment: seg_14 appears twice"]
    }
  ],
  "eligible_candidate_ids": ["cand_1"],
  "generated_at": "..."
}
```

---

## Reuse

Feasibility deliberately mirrors existing deterministic validators rather than reinventing them:

| Source | Reused idea |
|--------|-------------|
| [`artifact_completeness.py`](../../src/interview_mux/artifact_completeness.py) | Gap detection over artifact shapes |
| [`edl_narrative_qc.py`](../../src/interview_mux/edl_narrative_qc.py) | Selection parity, speaker-volley integrity |
| [`gap_vo_gates.py`](../../src/interview_mux/gap_vo_gates.py) | Pickup speaker / voice reference authorization |
| [`source_topology.py`](../../src/interview_mux/source_topology.py) | `pickup_eligible_speaker_id` |

---

## Failure handling

1. All candidates blocked → emit `no_eligible_candidates`; Shape Engine must remint L2 with the blocking reasons attached (bounded by agenda budget).
2. Still none → fall back to the safest representable plan (body-only, `cold_open=none`) and record why.
3. Advisory mode → write the artifact, log warnings, do not block.

---

## Config

```
mastering.quality_hardening.feasibility.mode           off|advisory|authoritative
mastering.quality_hardening.feasibility.duration_slack_pct  0.15
```
