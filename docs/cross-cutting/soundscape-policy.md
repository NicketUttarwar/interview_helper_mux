# Soundscape policy (closed-loop soundscape)

**Status:** BUILD-SS-01…SS-06 — unified per-run policy for music/SFX density, placement, and verify→remediate.

**Related:** [sound-design.md](./sound-design.md) · [source-derived-sonic-mix-profile.md](./source-derived-sonic-mix-profile.md) · [sonic-context.md](./sonic-context.md) · [post-generation-placement.md](./post-generation-placement.md) · [delivery-quality-preservation-matrix.md](./delivery-quality-preservation-matrix.md)

## Goal

Make music/SFX **dynamically decided and measurably enforced** for each recording: speech-first, content-aware density, segment-aware cue slots, capped remediation when standards are missed. No music library; generative MMAudio remains the asset source.

## Artifact

| Path | Stage | Role |
|------|-------|------|
| `understanding/soundscape_policy.json` | `soundscape_policy_build` | Single resolve surface for sonic stages |
| `sound_design/soundscape_report.json` | post-`mix` verify | Pass / remediated / warning audit |

`delivery_brief.json` stays **editorial** (`sfx_density` caps). Mix knobs live on soundscape policy.

## Document shape

```json
{
  "version": 1,
  "derived_from": {},
  "policy_hash": "…",
  "underscore_policy": "normal",
  "pace_class": "conversational",
  "sfx_density": { "max_beds": 2, "max_punctuators": 2, "max_foley": 1 },
  "mix_contract": {
    "bed_level_db_range": [-30, -26],
    "duck_under_speech_db": 16,
    "stinger_max_per_minute": 2,
    "midrange_policy": "carve_speech",
    "max_bed_coverage_ratio": 0.4
  },
  "standards": {
    "min_speech_relative_db": 12,
    "max_midrange_overlap_score": 0.35,
    "require_intelligibility_pass": true
  },
  "cue_slots": [],
  "operator_overrides": {},
  "rationale": []
}
```

Schema: [json-schemas/soundscape_policy.schema.json](./json-schemas/soundscape_policy.schema.json).

## Merge precedence (locked)

1. Operator overrides on the policy (or SAP underscore / pace overrides mirrored in)
2. SAP `source_music_risk=high` or SAP `underscore_policy=skip` → force skip/sparse beds
3. Sonic scenario posture hard bans (`bed_density: none`, trauma/noisy)
4. `delivery_brief.sfx_density` ∩ sonic `adaptive_max_assets_*` ∩ production profile
5. Defaults from SAP `mix_contract`

## Cue slots

Deterministic opportunities scored per segment/boundary:

| Rule | Effect |
|------|--------|
| Underscore `skip` / music risk high | No `ambient_bed` slots |
| Dense pace / high overlap | Beds sparse or none; stronger duck |
| Segment duration below threshold | No bed under that segment |
| Theme/palette match | Boost bed priority |
| Chapter / pause-tail | Stinger slots only when pause ≥ placement hint |
| Ranked selection refresh | At `sound_design_plan` input, slots re-scored for selected segments |

When `soundscape.strict_slots` is true (default), SDP cues must map to allowed slots/roles.

## Standards (measurable)

| Standard | Typical source |
|----------|----------------|
| `bed_level_db_range` | SAP / policy |
| `duck_under_speech_db` | SAP / policy |
| `stinger_max_per_minute` | SAP ∩ sonic posture |
| `max_bed_coverage_ratio` | Policy (sparse → lower) |
| `min_speech_relative_db` | Policy standards |
| Intelligibility | Existing mix QC when required |

## Remediation ladder (capped)

| Phase | Max | Actions |
|-------|-----|---------|
| Asset fitness (post-MMAudio) | 1 regen / `asset_id` | `adjust_level` → `regenerate` → `skip_cue` |
| Post-mix verify | 1 remux | Lower beds, strengthen duck, drop lowest-priority cues |
| Second verify fail | — | Warning ship if first-try / `fail_closed=false`; hard-fail if `soundscape.fail_closed` |

## Consumers (must honor)

| Stage | How |
|-------|-----|
| `sound_design_plan` | Compact policy + refreshed cue_slots in payload; lint per-role caps |
| `sfx_prompt_craft` | `mix_contract` + prompt tokens via policy resolve |
| `mmaudio_sfx` | Fitness actions; execute regenerate once |
| `mix` | `resolve_mix_contract`; apply placement skips; run verify→remux |
| GUI | Policy summary + overrides; G1.5 shows density/underscore |

## Config

See [config-keys.md](./config-keys.md) `soundscape.*`.

## API helpers

`src/interview_mux/soundscape_policy.py`:

- `build_policy(ctx)` / `run_soundscape_policy_build(ctx)`
- `load_policy(ctx)` / `resolve_mix_contract(ctx)`
- `refresh_cue_slots(ctx)` — delivery-time rescoring
- `compact_for_volley(policy)` — LLM payload

Verify: `src/interview_mux/soundscape_verify.py` + `tools/validate_soundscape.py`.
