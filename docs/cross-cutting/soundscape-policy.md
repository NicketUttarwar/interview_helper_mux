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
    "bed_level_db_range": [-16, -12],
    "duck_under_speech_db": 12,
    "stinger_max_per_minute": 2,
    "midrange_policy": "carve_speech",
    "max_bed_coverage_ratio": 0.85
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

**Bed coverage `0.40–0.85` and hinge-stinger coverage `0.3–1.0` are Shape-owned
soft bands (Plan 4), not a remux-theater target.** They live in
`listenability_guards._DEFAULTS` (`bed_coverage_min_ratio`/`max_ratio`,
`hinge_stinger_coverage_min_ratio`/`max_ratio`) and describe the range a
well-produced, Shape-driven master already falls into — see
[config-keys.md](./config-keys.md#creative_deliverylistenability_guards) and
[mix-house-chain.md](./mix-house-chain.md#bed-coverage--hinge-stinger--shape-owned-soft-bands-plan-4).
`soundscape_verify._estimate_bed_coverage` measures the *actual* planned bed
duration over actual selection duration — it never seeds or inflates cues
itself; seeding only happens in the remediation ladder below, and only on
real palette/quartile-mapped segments.

## Remediation ladder (capped)

| Phase | Max | Actions |
|-------|-----|---------|
| Asset fitness (post-MMAudio) | `soundscape.remediation.max_regen_per_asset` (default `2`) | `adjust_level` → `regenerate` → `skip_cue` |
| Post-mix verify | `soundscape.remediation.max_remux_cycles` (default `2`) | Lower beds / strengthen duck / drop lowest-priority cue (over-coverage); or seed palette/quartile-anchored, contiguous-preferring beds via `artifact_repairs.repair_sound_design_plan` (under-coverage) |
| Final verify fail | — | Warning ship if first-try / `fail_closed=false`, **or** if the only residual failure is a *minimum* bed/hinge coverage shortfall (never a max overshoot or intelligibility miss) — see "gaming guard" below; hard-fail (`fail_closed`) otherwise |

**Gaming guard (Plan 4):** under-coverage remediation must not invent
disconnected per-clip beds just to move the ratio. `repair_sound_design_plan`
only anchors new beds on segments already reachable from the selected
palettes/selection (never fabricated silence), and — when
`mastering.music_continuity.prefer_contiguous_beds` is set (default) —
prefers extending an already-bedded neighbor segment over starting a fresh
island, so mix-time merging folds the result into one honest scene bed. If
that honest ladder still can't clear the floor after `max_remux_cycles`,
`soundscape_verify.run_soundscape_verify` reports a loud warning
(`fail_closed_softened: true`) instead of `fail_closed` — the shortfall is
real editorial signal (not enough legitimate bed opportunities), not
something another remux pass should paper over by inventing more cues.

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
