# Operator sound and mix

How your interview’s pacing drives cohesive SFX — without reading the full SDP schema.

## Chain

1. **Source acoustic profile (SAP)** — pacing, energy, mix contract from source audio ([source-derived-sonic-mix-profile.md](../cross-cutting/source-derived-sonic-mix-profile.md)).
2. **Palettes** — theme-level sound vocabulary.
3. **Sound design plan (SDP)** — reusable `asset_id` + cues per flow ([sound-design.md](../cross-cutting/sound-design.md)).
4. **Assembly preview** — speech + VO only — **listen before MMAudio SFX generation**.
5. **Craft + generate** — one WAV per `asset_id` via local MMAudio (`mmaudio_sfx_flow*`).
6. **Optional QA loop** — post-listen pass/fail, `POST …/sfx-prompts/refine`, per-asset `regenerate`, `GET …/sfx-qa` ([mmaudio-prompt-tuning.md](../cross-cutting/mmaudio-prompt-tuning.md)).
7. **Mix + master** — `mix` / `REMOVED_mix_flow2` → LUFS target.

## Operator rules

- Never skip **assembly preview** listen for Flow 1 unless you accept SFX spend risk.
- Optional **G1.5:** approve prompts before generation (`g1_5_require_prompt_approval`).
- SAP strip in GUI shows `pace_class`, `bed_density`, `stinger_policy` on sound stages.
- **Bed coverage (0.40–0.88) and hinge stinger coverage (0.3–1.0) are soft bands, not targets to hit.** A run reporting near the low or high edge is not automatically broken — check `sound_design/soundscape_report.json` for the actual failures list, not just the verdict.
- Ducking is **speech-wins** for any voice on the timeline (native or recorded VO) — beds should never fight either one; if a bed feels loud under a VO bridge, that is a mix bug worth flagging, not expected behavior.
- If `soundscape_report.json` shows `fail_closed_softened: true`, mix chose to ship with a warning rather than force another remux to invent more beds — the run likely just doesn't have many legitimate bed opportunities (thin palette / short selection), which is a content signal, not a defect.

See [mix-house-chain.md](../cross-cutting/mix-house-chain.md) for the full speech-wins / contiguous-beds / gaming-guard detail.
