# Sound design & MMAudio examples (reference)

Worked patterns for Wave 5 stages and prompt craft. Pair with:

- [sfx-prompt-craft.system.txt](../../sound_design/sfx-prompt-craft.system.txt)
- [local-audio-stack.md](../../../cross-cutting/local-audio-stack.md)
- **[sfx-prompt-regression.md](./sfx-prompt-regression.md)** — golden prompts + must-not-hear checklists per role
- **[local-audio-stack.md](../../../cross-cutting/local-audio-stack.md)** — symptom → `prompt_influence` → regen vs rewrite

---

## Palette stage

### Good — grounded ambient_description

**Context:** Family farm interview; segments `seg_018`–`seg_022` tagged `farming`.

> Early-morning pasture heard from twenty meters: soft wind through dry grass, one distant bird call every eight to twelve seconds, very faint wooden fence creak, no animals close to mic, no human activity, no music, no rhythmic pulse, loopable eight-second bed with imperceptible seam, spectral energy mostly below 8 kHz except occasional bird, no broadband hiss, documentary realism not pastoral postcard.

**Why:** Space, distance, density, loop, exclusions, speech-safe spectrum.

### Weak — too thin

> Farm sounds outside.

**Why:** No space, duration, exclusions, or loop guidance — MMAudio may hallucinate vocals or cartoon animals.

### Bad — invented theme

Palette `fintech_disruption` with zero segment tags and no brief topic support.

**Why:** Violates transcript grounding.

---

## Flow 1 plan

### Good — reuse pattern

- Asset `chapter_stinger_warm` → cues at `after_segment` for `seg_012`, `seg_025`, `seg_040` (same `asset_id`).
- Asset `ambient_farm_morning` → `under_segment` only on `seg_018`, `seg_019`, `seg_022`.
- `duck_under_speech_db`: 16 on all bed cues.

### Weak — v1 regression

Six assets `stinger_ch01` … `stinger_ch06` with identical descriptions.

**Why:** Six API calls, timbral drift, higher cost.

---

## Flow 2 plan

### Good — single transition asset

```json
{
  "asset_id": "montage_whoosh_soft",
  "role": "transition_stinger",
  "reuse_note": "All between_clips cues"
}
```

Cues: `(1→2)`, `(2→3)`, `(3→4)` share `montage_whoosh_soft`; `level_db` −10, −12, −11 respectively.

### Weak — per-cut assets

Different `asset_id` per `between_clips` with different descriptions.

**Why:** Violates montage cohesion; contradicts target spec (v1 montage brief allowed this — target does not).

---

## MMAudio craft — ambient_bed

### Good — `sfx_prompt` (excerpt pattern)

> This sound supports a warm documentary interview about family farming, sitting far under clear dialogue. Imagine an outdoor pasture at dawn twenty meters from the listener: a gentle dry-grass wind layer, very subtle, with one distant bird call appearing roughly every ten seconds, and an occasional faint wooden creak like a distant gate, never close or sharp. The texture is organic and dry, no reverb tail longer than one second, no low-end rumble below eighty hertz, energy concentrated below six kilohertz so spoken words stay forward in the mix. The eight-second texture must loop seamlessly with no click at the wrap point, no rhythmic pulse, no beat, no melody, no human presence, designed to be ducked eighteen to twenty-four decibels under speech. Emotional color is hopeful and calm, not sentimental or cinematic trailer.

**negative_prompt:** no vocals, no lyrics, no speech, no humming, no melody hook, no drum loop, no pulse, no crowd, no cartoon animals

**duration_seconds:** 7.0

### Weak

> Farm ambience loop.

### Bad — policy risk

> Crowd saying “yeah” softly in background.

---

## MMAudio craft — chapter_stinger

### Good

> Warm documentary chapter punctuation for an interview podcast: a single soft tonal rise over one point five seconds, starting from silence with a gentle mid-frequency swell, no percussion, no cymbal, no trailer whoosh, no vocal formants, harmonic content sparse like a muted synthesizer pad fading in and out, peak at minus twelve dBFS conceptual loudness then decay fully to silence by two seconds, emotional closure not excitement, matches hopeful primary mood.

**musical_intent:** register mid, motion rise_then_fall, harmonic_density sparse, rhythmic_presence none

**duration_seconds:** 1.5

### Weak

> Short sting.

---

## MMAudio craft — transition_stinger (Flow 2)

### Good

> Montage transition glue for highlight reel: a one point two second forward spectral glide, soft noise and warm mid band moving upward then cutting cleanly, no vocals, no beat, not a riser longer than one second of motion, energy controlled so it can sit ten to fourteen decibels under clip edges, works between disparate interview topics without implying a new song, documentary not TikTok.

**duration_seconds:** 1.2

---

## MMAudio craft — vo_bridge

### Good

> Soft non-vocal air texture to precede recorded interviewer voice: one second gentle room tone with high-passed hiss above two hundred hertz, no words, no melody, fades in over three hundred milliseconds and yields to human speech, does not mask consonants.

**duration_seconds:** 1.0

---

## Post-generation adaptation (examples)

| Situation | Adaptation |
|-----------|------------|
| Bed masks speech in seg_020 | Lower `level_db` from −26 to −30; increase duck to 18 dB |
| Stinger overlaps last word | Shift cue 200 ms later (sequential, not overlap) |
| Flow 2 cut 2→3 harsh | 150 ms equal-power crossfade + transition at −14 dB |
| Cold open fights clip 1 | Fade open −8 dB over 400 ms as speech enters |

---

## v1 brief → target craft migration

| v1 (`podcast_sfx_brief`) | Target |
|--------------------------|--------|
| Per-chapter different `description` strings | One `chapter_stinger` asset + many cues |
| `beds[].description` short | Palette `ambient_description` → craft → one bed asset |
| Fixed 2s API | `duration_seconds` from craft |

See [podcast-sfx-brief.system.txt](../../assembly/podcast-sfx-brief.system.txt) for v1-only behavior.
