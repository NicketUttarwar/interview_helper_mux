# MMAudio prompt regression appendix

Golden `sfx_prompt` fixtures for **listening QA** and craft-stage regression. Use after generation (or in spike runs) to verify outputs stay speech-safe and on-brand.

**Pair with:** [sound-design.examples.md](./sound-design.examples.md) (patterns), [local-audio-stack.md](../../../cross-cutting/local-audio-stack.md) (when output drifts).

**Generation:** Local MMAudio `large_44k_v2` text-to-audio via `mmaudio_sfx_flow*` — see [mmaudio-prompt-tuning.md](../../../cross-cutting/mmaudio-prompt-tuning.md) and [local-audio-stack.md](../../../cross-cutting/local-audio-stack.md).

---

## How to run a regression pass

1. Generate each fixture with the listed `duration_seconds` and `prompt_influence`.
2. Solo-listen the WAV, then under the densest speech stem from `ingest/normalized.wav`.
3. Check every **Must not hear** item; any fail → follow tuning guide (influence vs rewrite).
4. Log result in `gui_log.jsonl` (see [GUI operator journey](../../../cross-cutting/local-audio-stack.md#gui-operator-journey)).

| Result | Log `message` pattern (suggested) |
|--------|-----------------------------------|
| Pass | `mmaudio_regression_pass asset_id=<id>` |
| Fail | `mmaudio_regression_fail asset_id=<id> reason=<short>` |

---

## Fixture 1 — `ambient_bed` (farm morning)

**asset_id:** `regression_bed_farm_morning`  
**duration_seconds:** 7.0  
**prompt_influence:** 0.30

**sfx_prompt:**

> This sound supports a warm documentary interview about family farming, sitting far under clear dialogue. Imagine an outdoor pasture at dawn twenty meters from the listener: a gentle dry-grass wind layer, very subtle, with one distant bird call appearing roughly every ten seconds, and an occasional faint wooden creak like a distant gate, never close or sharp. The texture is organic and dry, no reverb tail longer than one second, no low-end rumble below eighty hertz, energy concentrated below six kilohertz so spoken words stay forward in the mix. The seven-second texture must loop seamlessly with no click at the wrap point, no rhythmic pulse, no beat, no melody, no human presence, designed to be ducked eighteen to twenty-four decibels under speech. Emotional color is hopeful and calm, not sentimental or cinematic trailer.

**Must not hear**

- [ ] Words, humming, or crowd chant
- [ ] Steady beat, clap loop, or EDM pulse
- [ ] Cartoon animal close to mic (comedy barn)
- [ ] Audible loop click at wrap
- [ ] Broadband hiss louder than wind bed

---

## Fixture 2 — `ambient_bed` (office neutral)

**asset_id:** `regression_bed_office_neutral`  
**duration_seconds:** 6.0  
**prompt_influence:** 0.28

**sfx_prompt:**

> Neutral documentary office air for an investigative interview podcast, extremely subtle, designed to sit twenty decibels under dialogue. Small room tone with distant HVAC hum above three hundred hertz, no keyboard clicks, no phone rings, no voices in hallway, no music, no rhythm, six seconds seamless loop, dry not cavernous, midrange kept thin so consonants stay clear, gentle static air only, professional not cinematic.

**Must not hear**

- [ ] Speech fragments or laughter
- [ ] Music bed or chord changes
- [ ] Traffic or outdoor ambience (wrong space)
- [ ] Prominent low-frequency rumble

---

## Fixture 3 — `chapter_stinger`

**asset_id:** `regression_stinger_chapter_warm`  
**duration_seconds:** 1.5  
**prompt_influence:** 0.38

**sfx_prompt:**

> Warm documentary chapter punctuation for an interview podcast: a single soft tonal rise over one point five seconds, starting from silence with a gentle mid-frequency swell, no percussion, no cymbal, no trailer whoosh, no vocal formants, harmonic content sparse like a muted synthesizer pad fading in and out, peak controlled then decay fully to silence by one point eight seconds, emotional closure not excitement.

**Must not hear**

- [ ] Drum hit, cymbal splash, or clap
- [ ] Trailer braam or long riser past two seconds
- [ ] Voice-like vowels or whisper
- [ ] Tail still loud after two seconds

---

## Fixture 4 — `transition_stinger` (Flow 2)

**asset_id:** `regression_transition_montage`  
**duration_seconds:** 1.2  
**prompt_influence:** 0.40

**sfx_prompt:**

> Montage transition glue for highlight reel: a one point two second forward spectral glide, soft noise and warm mid band moving upward then cutting cleanly, no vocals, no beat, not a riser longer than one second of motion, energy controlled for ten to fourteen decibels under clip edges, works between disparate interview topics without implying a new song, documentary not social media.

**Must not hear**

- [ ] Full measure of music or recognizable hook
- [ ] Vocal “whoosh” or shouted energy
- [ ] Length beyond ~1.4 s of meaningful energy

---

## Fixture 5 — `cold_open`

**asset_id:** `regression_cold_open`  
**duration_seconds:** 2.0  
**prompt_influence:** 0.42

**sfx_prompt:**

> Short cold open for documentary highlight reel, two seconds, hopeful but restrained, soft upward spectral motion from silence, no percussion, no voice, no lyrics, sets attentive mood without trailer hype, decays enough to hand off to speech within two hundred milliseconds overlap at low level, midrange not harsh.

**Must not hear**

- [ ] Speech, chant, or crowd
- [ ] EDM drop or bass sweep dominating
- [ ] Still blaring at 2.0 s with no decay

---

## Fixture 6 — `vo_bridge`

**asset_id:** `regression_vo_bridge`  
**duration_seconds:** 1.0  
**prompt_influence:** 0.32

**sfx_prompt:**

> Soft non-vocal air texture to precede recorded interviewer voice: one second gentle room tone with high-passed hiss above two hundred hertz, no words, no melody, fades in over three hundred milliseconds and yields to human speech, does not mask consonants, no musical pitch center.

**Must not hear**

- [ ] Syllables or whispered words
- [ ] Melodic tone that competes with VO
- [ ] Click or pop at start/end

---

## Fixture 7 — `accent_foley`

**asset_id:** `regression_accent_paper`  
**duration_seconds:** 0.8  
**prompt_influence:** 0.35

**sfx_prompt:**

> Single dry paper page turn in a quiet studio, one gesture only, close but soft, no voice, no room reverb tail longer than three hundred milliseconds, documentary realism not cartoon, under eight tenths of a second total.

**Must not hear**

- [ ] Multiple turns or shuffling loop
- [ ] Voice or breath
- [ ] Cartoon squash sound

---

## Fixture 8 — control (should fail craft validation)

**asset_id:** `regression_control_bad`  
**Do not call API** — craft stage must reject.

**sfx_prompt (intentionally bad):**

> Crowd cheering yeah yeah with announcer voice over stadium horn loop.

**Must not hear (if API were wrongly called)**

- [ ] Any intelligible speech — **expected fail**

---

## Role summary table

| Role | Fixtures | Default `prompt_influence` |
|------|----------|----------------------------|
| `ambient_bed` | 1–2 | 0.28–0.30 |
| `chapter_stinger` | 3 | 0.38 |
| `transition_stinger` | 4 | 0.40 |
| `cold_open` | 5 | 0.42 |
| `vo_bridge` | 6 | 0.32 |
| `accent_foley` | 7 | 0.35 |
| control | 8 | — |

---

## Per-scenario theme_fit regression (pass / fail pairs)

Quick listen checks after generation — one bed + one stinger archetype per atlas bucket. **Pass** = must-not-hear clear + theme matches posture; **Fail** = any must-not-hear hit or scenario violation.

| Scenario | Pass cue | Fail cue |
|----------|----------|----------|
| `one_on_one` | Warm sparse room bed; soft 1.5s rise | Trailer whoosh or drum loop under dialogue |
| `panel` | No bed on overlap segment; tiny neutral bump at chapter only | Continuous busy bed under crosstalk |
| `fireside` | Gentle air swell; no percussion | Aggressive percussion or jump-scare rise |
| `technical_deep_dive` | Ultra-thin neutral air only | Cinematic braam or cartoon blip |
| `media_profile` | Broadcast-clean sparse bed | Tabloid sting or ironic comedic stab |
| `debate` | Dry studio; no conflict impacts | Sarcasm-coded comedic hit on disagreement |
| `noisy_room` | No bed; no bright riser | Dense masking bed or broadband hiss rise |
| `dense_jargon` | Minimal non-lyrical air | Harmonic busy bed over terminology chains |
| `trauma_adjacent` | Silence or vo_bridge only on flagged segments | Playful motif or loud transient stinger |

Log pass/fail with `mmaudio_regression_pass` / `mmaudio_regression_fail` and `scenario=<atlas_bucket>` in `gui_log.jsonl`.
