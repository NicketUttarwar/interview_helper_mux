# ElevenLabs prompt influence tuning (Music v2)

**Craft field:** `prompt_influence` on each row in `sound_design/elevenlabs_prompts.json` (0.0–1.0 typical range; higher = stricter adherence to prompt text).

**API:** ElevenLabs **Music v2** (`POST https://api.elevenlabs.io/v1/music`, `model_id`: `music_v2`) does **not** expose `prompt_influence`. The repo maps craft values to prompt prose in `interview_mux.elevenlabs_rest.apply_prompt_influence_to_text` before the REST call.

Path anchor: [anchored-toolchain.md](./anchored-toolchain.md#external-http-apis-version-surfaces).

---

## Mapping (shipped)

| Craft `prompt_influence` | Prompt suffix behavior |
|--------------------------|------------------------|
| ≥ 0.40 | Adds “follow precisely / minimal improvisation” guidance |
| ≤ 0.25 | Adds “allow subtle variation” guidance |
| 0.26–0.39 | No suffix (prompt text only) |

Role defaults in `sfx_elevenlabs._ROLE_INFLUENCE` still apply when craft rows omit `prompt_influence`.

---

## Symptom → action

| Symptom | Try first | Then |
|---------|-----------|------|
| Output ignores prompt details | Raise craft `prompt_influence` to 0.40+ | Rewrite `elevenlabs_prompt`; tighten `negative_prompt` |
| Output feels stiff / repetitive | Lower to 0.25 or below | Shorten prompt; reduce conflicting adjectives |
| Timbral wrong but follows words | Rewrite prompt (influence won’t fix timbre) | Regen asset; adjust SDP role/duration |
| Vocals in bed | Ensure `force_instrumental: true` in config; strengthen “no vocals” in prompt | Regen |

See [elevenlabs-prompt-regression.md](../prompts/_shared/examples/elevenlabs-prompt-regression.md) and [elevenlabs-integration-guide.md](./elevenlabs-integration-guide.md).
