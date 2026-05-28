# Sound design — guardrails and edge cases (BUILD-060+)

**When to use:** Wave 5 sound design (prompt files shipped). Spec: [sound-design.md](../../cross-cutting/sound-design.md), [elevenlabs-integration-guide.md](../../cross-cutting/elevenlabs-integration-guide.md). Examples: [sound-design.examples.md](../_shared/examples/sound-design.examples.md). This doc is **settings + rails + breadth**, not a large example library.

---

## Global settings (config / SDP)

| Knob | Risk if wrong | Guard |
|------|----------------|-------|
| `sound_design.enabled` | Spend on SFX when operator wants dry review | Default off or explicit opt-in; respect assembly-preview-first flow when BUILD-069 exists |
| `max_assets_flow1` / `max_assets_flow2` | API cost + timbral soup | Cap enforced in code; plans that exceed cap → validation failure, not silent trim |
| `g1_5_require_prompt_approval` (G1.5, shipped) | Surprise spend | When true, block ElevenLabs until operator approves crafted prompts in GUI |
| `allow_diegetic_ambient` | Music mistaken for “room” | If false, reject beds that imply performance; document in SDP `avoid` |

---

## Palette stage (`sound_design_palettes`) — edge cases

| Situation | Bad outcome | Rail |
|-----------|-------------|------|
| No `topic_tags` on segments | Palettes float free of timeline | Require ≥1 `segment_id` per palette from manifest evidence; empty palette list → `needs_input` or merge from brief only with low confidence |
| Single-topic interview | Forced fake diversity | Allow 1 palette; do not invent secondary “themes” |
| Dense jargon block | Bed under unintelligible STT | Prefer no `under_segment` until G0 clean; flag in investigations |
| Operator `style.sound_design_notes` | Model ignores bans | Treat as hard `avoid` + density override in volley |

**Minimal good pattern:** 1–2 palettes, each tied to real `segment_ids`, `avoid` lists clichés for *this* interview’s tone (one line each).

---

## Flow 1 plan — edge cases

| Situation | Bad outcome | Rail |
|-----------|-------------|------|
| Chapter with zero segments | Stinger into void | Validator: every `after_segment_id` / chapter hook resolves in `selection` |
| Same `asset_id` not reused | One WAV per cue (v1 regression) | Schema or lint: N cues → ≤ `max_assets_flow1` unique `asset_id`s |
| VO placement without `vo_pickup` duration | Wrong duck timing | BUILD-066: optional `sound_design_vo_finalize` after ingest of pickups |
| `duck_under_speech_db` too small | Speech buried | Clamp in mix engine; warn in plan QA if below product minimum |

---

## Flow 2 plan — edge cases

| Situation | Bad outcome | Rail |
|-----------|-------------|------|
| `<2` highlights | `between_clips` undefined | Plan must tolerate 1 clip: no between cues; cold open / outro only |
| Rank gaps in selection | Wrong transition pair | Cues must use `from_clip_rank` / `to_clip_rank` present in `selection`; reject orphan ranks |
| Identical montage energy every cut | Listener fatigue | Single shared transition `asset_id` is intentional; vary **level_db** only within spec limits |

---

## ElevenLabs prompt craft — edge cases

| Situation | Bad outcome | Rail |
|-----------|-------------|------|
| Prompt contains lyrics / voice | Policy / brand risk | `negative_prompt` + schema reject strings matching speech patterns; blocked retry |
| Duration mismatch | Truncate or pad audible glitch | `duration_seconds` required; mix uses craft output, not fixed 2s |
| Regeneration churn | Cost explosion | Hash plan → skip regen unless plan changes (per [sound-design.md](../../cross-cutting/sound-design.md)) |

**Minimal bad pattern to reject:** “crowd cheering words yeah yeah” (diegetic speech). **Minimal good pattern:** “soft non-vocal room tone, no rhythm, 6s loop”.

---

## Mix phase (BUILD-065) — edge cases

| Situation | Bad outcome | Rail |
|-----------|-------------|------|
| Missing WAV for `asset_id` | Silent hole or crash | Placeholder silence of declared length; log + GUI warning |
| Peak stack-up | Clipped master | True-peak limiter stage + verify_master (BUILD-070) |
| Bed + VO + speech overlap | Mud | Bus ducking order documented in code; assert speech bus always wins |

---

## Post-generation — edge cases

| Situation | Bad outcome | Rail |
|-----------|-------------|------|
| Plan fixes crossfade ms before listen | Wrong for spectral clash between clips | Adapt in post-analysis only — [sound-design.md](../../cross-cutting/sound-design.md) |
| Regen without plan hash change | Cost loop | Max 2 regens per `asset_id`; log in `gui_log.jsonl` |
| Operator theme/scripture notes ignored | Off-brand beds | Merge `style.sound_design_notes` into craft + post-gen theme fit |

## Related

- [README.md](./README.md) — stage → prompt file map
- [elevenlabs-integration-guide.md](../../cross-cutting/elevenlabs-integration-guide.md) — API + post-analysis playbook
- [sound-design.md](../../cross-cutting/sound-design.md) — SDP shape and waves
- [operator-stage-checklists.md](../../workflows/operator-stage-checklists.md) — ElevenLabs pre/post spend
- [prompts README — Example packs](../README.md#example-packs) — index of pattern packs + this doc
