# stt-lexicon-island-verify examples

Specialist pre-pass on `full_master_ranking`. Scores candidate STT-weak groups for soft prefer-include only — never excludes other segments.

## Good — domain lexicon mid-run, boost

```json
{
  "group_verdicts": [
    {
      "group_id": "grp_014",
      "segment_ids": ["seg_042"],
      "fits_case": true,
      "importance_score": 0.84,
      "boost_recommended": true,
      "failure_mode": "domain_lexicon",
      "rationale": "Pads explain a clinical dosage decision; mid-span STT garble should not drop the answer."
    }
  ]
}
```

## Good — Spanglish / code-switch, boost

```json
{
  "group_verdicts": [
    {
      "group_id": "grp_022",
      "segment_ids": ["seg_050a", "seg_050b"],
      "fits_case": true,
      "importance_score": 0.78,
      "boost_recommended": true,
      "failure_mode": "code_switch",
      "rationale": "English pads frame a Spanish punchline that carries the guest's main claim."
    }
  ]
}
```

## Good — noise / filler, no boost (neutral)

```json
{
  "group_verdicts": [
    {
      "group_id": "grp_009",
      "segment_ids": ["seg_018"],
      "fits_case": false,
      "importance_score": 0.2,
      "boost_recommended": false,
      "failure_mode": "noise",
      "rationale": "Pads are backchannel filler around crosstalk; leave ranking unchanged."
    }
  ]
}
```

## Bad — invents exclusions

```json
{
  "group_verdicts": [
    {
      "group_id": "grp_014",
      "segment_ids": ["seg_042"],
      "fits_case": true,
      "importance_score": 0.9,
      "boost_recommended": true,
      "failure_mode": "domain_lexicon",
      "rationale": "Boost seg_042 and drop seg_041–seg_045 as low quality STT."
    }
  ]
}
```

Never demote or exclude non-candidate segments from this specialist.
