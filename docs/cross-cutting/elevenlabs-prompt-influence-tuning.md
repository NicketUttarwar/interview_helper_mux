# ElevenLabs `prompt_influence` tuning guide

**API field:** `prompt_influence` on `POST https://api.elevenlabs.io/v1/sound-generation` (0.0–1.0 typical range; higher = stricter adherence to prompt text).

**REST-only:** Implement via [elevenlabs_rest.py](../../src/interview_mux/elevenlabs_rest.py) — not the ElevenLabs Python SDK.

**Defaults by role:** [elevenlabs-integration-guide.md](./elevenlabs-integration-guide.md) § Service A.

---

## Decision table

| Symptom (what you hear) | Likely cause | `prompt_influence` | Next action |
|-------------------------|--------------|-------------------|-------------|
| Output ignores key exclusions (vocals, beat, trailer whoosh) | Model drifting off prompt | **Raise** +0.05–0.10 (cap ~0.50) | Regen same prompt; if still fails → **rewrite** prompt with stronger exclusions in prose + `negative_prompt` |
| Output is thin, noisy, or “generic room tone” only | Over-constrained | **Lower** −0.05–0.10 (floor ~0.20) | Regen; if still dull → **rewrite** with richer spectral/space detail (not shorter prompt) |
| Metallic / harsh highs on stinger | Prompt too bright or influence too high on noise words | **Lower** −0.05 | **Rewrite** — soften “bright”, “shimmer”, add “warm, no harsh sibilance” |
| Bed masks speech (even when ducked) | Too much midrange energy in generation | **Lower** −0.03 | **Rewrite** bed — “energy below 6 kHz”; post-gen lower `level_db` |
| Muddy / boomy bed | Too much low end in output | **Lower** −0.05 | **Rewrite** — “no rumble below 80 Hz”; regen once |
| Stinger too long / riser keeps going | Duration drift | Keep influence | **Regen** with `duration_seconds` −0.2; tighten temporal shape in prompt |
| Stinger too short / clipped | Duration drift | Keep influence | **Regen** with `duration_seconds` +0.2 |
| Voice-like formants in bed | Policy failure | **Raise** +0.10 | **Rewrite** + discard take; block if repeats |
| Cartoon / comedy color | Wrong adjectives | Keep influence | **Rewrite** prompt + palette `avoid`; regen |
| Same prompt, different runs wildly different | Normal variance | Keep influence | Regen up to **2** times; then **rewrite** one section (space or exclusions) |
| Loop seam click on bed | Loop language ignored | **Raise** +0.05 | **Rewrite** “seamless loop, no click at wrap”; regen |
| Montage transition feels like new song each cut | Melodic hook | **Raise** +0.05 | **Rewrite** — “no melody hook, non-tonal spectral glide” |
| Cold open fights clip 1 | Level + spectral clash | **Lower** −0.05 on open | Post-gen overlap −8 dB / 400 ms; optional regen |

---

## Regen vs rewrite prompt

| Action | When | Cost |
|--------|------|------|
| **Regen** | Prompt is correct; random variance or duration slightly off | 1 API call |
| **Rewrite prompt** | Systematic wrong color, policy risk, or repeated regen failures | 1 craft LLM call + 1 API call |
| **Change plan** | Wrong role or asset boundaries (bed on wrong segments) | Edit SDP cues, not influence |

**Cap:** Max **2** regens per `asset_id` per plan hash, then mandatory rewrite or operator sign-off.

---

## Starting points (prescriptive)

| Role | Start `prompt_influence` | Adjust first |
|------|-------------------------|--------------|
| `ambient_bed` | 0.30 | Lower if dull; raise if exclusions ignored |
| `chapter_stinger` | 0.38 | Lower if harsh; raise if whoosh appears |
| `transition_stinger` | 0.40 | Lower if metallic; raise if melodic hook |
| `cold_open` | 0.42 | Lower if fights speech overlap |
| `vo_bridge` | 0.32 | Raise if any voice-like content |
| `accent_foley` | 0.35 | Raise if gesture splits into multiple events |

---

## Related

- [elevenlabs-prompt-regression.md](../prompts/_shared/examples/elevenlabs-prompt-regression.md) — golden fixtures
- [sound-design.examples.md](../prompts/_shared/examples/sound-design.examples.md) — craft prose patterns
- [troubleshooting.md](../workflows/troubleshooting.md) — HTTP / quota failures
