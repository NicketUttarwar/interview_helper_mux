# Interview scenario atlas

Diverse English interview formats the pipeline must handle without format-specific code paths. Stages read `memory_updates.style_patch.format_class` and `tone_class` from `content_context`; this atlas supplies **detection signals**, **prompt adaptations**, **sound posture**, and **failure modes** for each class.

Injected into volley context when `analysis_state.style` is sparse. Pair with [analysis-preamble.system.txt](./analysis-preamble.system.txt) and per-stage system prompts.

---

## one_on_one

Classic two-person Q&A: one interviewer, one interviewee, turn-taking.

### Signals

| Signal | Where to look |
|--------|---------------|
| Two dominant speaker roles | `speakers.json`: `interviewer` + `interviewee` |
| Alternating short questions / long answers | `manifest.json` segment lengths and `speaker_id` swaps |
| Low overlap speech | Diarization confidence high; few `crosstalk` segments |
| Thesis in guest voice | `content_brief.thesis` attributable to interviewee claims |

### Prompt adaptations

- **speaker_roles:** Default role assignment; flag third speaker only if sustained (>30s).
- **content_context:** `format_class: one_on_one`; `tone_class` from interviewer cadence (probing vs celebratory).
- **boundary_detection:** Split on question→answer pivots; avoid micro-segments on brief interviewer follow-ups.
- **missing_framing:** Expect `missing_question` when answer references prior off-mic context.
- **transitions:** Mirror interviewer diction from `interviewer_sample_lines`; one sentence bridges.

### Sound posture

- Sparse beds under emotional beats only; `stinger_max_per_minute` ≤ 2.
- Chapter stingers at major topic shifts (`after_segment` on `narrative_plan` chapter ends).
- Duck 16–18 dB; beds loop under single long answers.

### Failure modes

| Failure | Symptom | Recovery |
|---------|---------|----------|
| Role swap | Interviewer labeled interviewee | Re-run `speaker_roles`; check G0 name corrections |
| Chronological-only ranking | Master follows recording order | `narrative_arc_plan` + ranking re-run |
| Over-bridging | VO for every answer | Tighten `missing_framing` severity threshold |

---

## panel

Three or more participants; moderator may not be sole question-asker.

### Signals

| Signal | Where to look |
|--------|---------------|
| ≥3 speakers with sustained airtime | `speakers.json` duration share |
| Multiple `interviewee` or `panelist` roles | Role assignment ambiguity |
| Crosstalk / overlap segments | Low diarization confidence clusters |
| Topic handoffs without clear question | `segment_classification`: `panel_discussion` |

### Prompt adaptations

- **speaker_roles:** Distinguish `moderator` vs `panelist`; never collapse panelists to one `interviewee`.
- **content_context:** `format_class: panel`; thesis may be collective (“the panel agreed…”).
- **boundary_detection:** Prefer speaker-change boundaries; tolerate mid-sentence splits on overlap.
- **segment_classification:** Tag `speaker_id` per segment; note `multi_speaker` when overlap.
- **highlight_selection:** Favor clips with single-speaker clarity for Flow 2.

### Sound posture

- Minimal beds during multi-speaker overlap (masking risk).
- Stingers only at moderator chapter resets; cap 1/min.
- Flow 2: shorter crossfades (80–100 ms) to preserve energy across speakers.

### Failure modes

| Failure | Symptom | Recovery |
|---------|---------|----------|
| Speaker collapse | One guest role for three people | `speaker_roles` + manual G0 speaker labels |
| Lost attribution | Quote without speaker | `content_brief` entity patch; reanchor |
| Mud mix | Beds under overlap | Lower bed level; skip `under_segment` on overlap segments |

---

## fireside

Loose, conversational; long answers; interviewer as facilitator not prosecutor.

### Signals

| Signal | Where to look |
|--------|---------------|
| Long `interviewee_answer` segments (>90s median) | `manifest.json` |
| Low question density | Few `interviewer` segments per 10 min |
| Narrative / anecdote tags | `segment_classification` types |
| Warm `tone_class` | Emotional beats: nostalgia, humor |

### Prompt adaptations

- **boundary_detection:** Fewer boundaries; merge adjacent same-speaker anecdotes.
- **narrative_arc_plan:** Story-arc chapters (setup → tension → resolution).
- **missing_framing:** Lower severity on `ok_with_light_bridge`; fireside context often in-segment.
- **full_master_ranking:** Prefer narrative continuity over punchy cuts.

### Sound posture

- Warm ambient beds; longer fade-in (200 ms) / fade-out (250 ms).
- Rare stingers; use bed swell instead of punctuation SFX.
- `sonic_identity`: intimate room, soft room tone, no trailer energy.

### Failure modes

| Failure | Symptom | Recovery |
|---------|---------|----------|
| Over-segmentation | >150 boundaries on 60 min | Re-run `boundary_detection` with merge bias |
| Trailer tone | Stingers every 3 min | Reduce `stinger_max_per_minute` in SAP |
| Lost through-line | Ranking feels random | `narrative_arc_plan` constraints before ranking |

---

## technical_deep_dive

Domain jargon, acronyms, precision; listener may lack background.

### Signals

| Signal | Where to look |
|--------|---------------|
| High type-token ratio in answers | Transcript lexical density |
| Acronym / proper-noun spikes | `content_brief.entities` |
| `definition_needed` gaps | `missing_framing` / specialist risks |
| Low `self_explanatory` rate | `gap_evaluations.json` |

### Prompt adaptations

- **content_context:** Capture `glossary_candidates`; mark claims needing definition.
- **missing_framing:** Elevate `undefined_term` and `missing_setup` severities.
- **comprehension_risk_blind:** Score jargon-dense segments high.
- **optimal_questions:** Propose definitional VO bridges, not hype lines.
- **topic_coverage_audit:** Map technical claims to lay-language brief topics.

### Sound posture

- Very sparse beds; clarity-first duck (18–22 dB).
- No melodic stingers in dense explanation passages.
- Accent foley only at section boundaries, −14 dB max.

### Failure modes

| Failure | Symptom | Recovery |
|---------|---------|----------|
| Assumed knowledge | Listener lost on acronym | `missing_framing` + G1 VO pickup |
| Wrong glossary | Invented term definitions | Re-run `content_context` with G0 fixes |
| Masked consonants | Bed in 1–4 kHz | Regen bed; raise duck |

---

## media_profile

Celebrity / public figure; personality-forward; clip-friendly.

### Signals

| Signal | Where to look |
|--------|---------------|
| High `quotability_signals` | `stage_enrichment` |
| Short punchy answers | Segment duration variance |
| `highlight_selection` candidates abundant | Emotional peaks |
| Public figure entities | `content_brief.entities` |

### Prompt adaptations

- **highlight_selection:** Prioritize standalone clips; `hook_strength` weight up.
- **podcast_show_description:** Lead with personality hook; avoid spoiler thesis.
- **transitions:** Lighter touch; don't over-explain famous context.
- **content_brief_reanchor:** Confirm `hypotheses` about public narrative vs transcript.

### Sound posture

- Flow 2 primary; cold open stinger optional.
- Montage `transition_stinger` shared across cuts.
- Flow 1: fewer chapters, more highlight-style internal peaks.

### Failure modes

| Failure | Symptom | Recovery |
|---------|---------|----------|
| Context dump | Transitions over-explain fame | Shorten transition lines |
| Clip lacks hook | First 3s weak | Re-rank with `quotability_signals` |
| Tabloid tone | Show description sensational | Arbiter reject; rewrite craft |

---

## debate

Adversarial or opposing viewpoints; interruption; rebuttal structure.

### Signals

| Signal | Where to look |
|--------|---------------|
| Challenge / rebuttal segment types | `segment_classification` |
| Interruption boundaries | Short segments, overlap |
| Thesis tension | `content_brief.hypotheses` with conflict |
| High `risk_score` on pivot segments | `comprehension_risks` |

### Prompt adaptations

- **boundary_detection:** Preserve rebuttal pairs; don't merge opposing turns.
- **narrative_arc_plan:** Document position A → challenge → response arcs.
- **missing_framing:** `missing_question` when challenge references unseen prior argument.
- **full_master_ranking:** Keep rebuttal pairs adjacent in `ordering_constraints`.

### Sound posture

- No beds under heated exchange (energy already high).
- Stinger only at round/chapter boundaries.
- Neutral sonic identity; avoid triumphant stingers that bias one side.

### Failure modes

| Failure | Symptom | Recovery |
|---------|---------|----------|
| Lost rebuttal | Answer without challenge context | `missing_framing` + ranking constraints |
| Editorial bias | Ranking favors one side | Audit `narrative_arc_plan` neutrality |
| Harsh montage | Flow 2 cuts mid-rebuttal | Extend crossfade; respect pair boundaries |

---

## noisy_room

High ambient noise, HVAC, handling, room reverb; STT stress.

### Signals

| Signal | Where to look |
|--------|---------------|
| Many G0 `flagged_chunks` | `transcript/review_queue.json` |
| Low mean chunk confidence (<0.80) | G0 queue stats |
| `transcript_quality.flagged_chunks` in volley | `context_volley.py` |
| SAP: high noise floor | `source_acoustic_profile` |

### Prompt adaptations

- **All P0 stages:** Honor `transcript_quality`; lower confidence on flagged regions.
- **content_context:** Mark claims in flagged windows as `confidence: low`.
- **boundary_detection:** Do not split mid-sentence to recover fragmentation unless obvious.
- **disfluency_extract:** Expect higher false-positive rate; operator G0.5 critical.

### Sound posture

- Prefer post-preclean speech stem for mix reference.
- Beds with strong sub-200 Hz roll-off; avoid boosting room rumble.
- Stinger alignment uses longer `stinger_min_pause_after_speech_ms` (500+).

### Failure modes

| Failure | Symptom | Recovery |
|---------|---------|----------|
| Hallucinated proper nouns | Names wrong in brief | G0 fuzzy replace + `content_context` re-run |
| False boundaries | Splits on STT glitches | `boundary_detection` with flagged_chunk mask |
| Noise pumping | Duck breathes with HVAC | Static duck depth; skip beds |

---

## dense_jargon

Similar to technical_deep_dive but emphasis on **uninterrupted** terminology chains (legal, medical, policy).

### Signals

| Signal | Where to look |
|--------|---------------|
| Long runs without common words | Transcript readability metrics |
| Few pauses >400 ms inside answers | SAP `pause_p50_ms` low |
| Entities without lay equivalents | `content_brief.topics` vs transcript |
| Specialist high `risk_score` clusters | Comprehension pass |

### Prompt adaptations

- **segment_classification:** Tag `dense_jargon` on segments; do not over-summarize.
- **topic_coverage_audit:** `emphasis_coverage_pass` for acoustically emphasized jargon.
- **optimal_questions:** Glossary-style VO bridges at first occurrence.
- **podcast_show_description:** Audience line must state expertise level assumed.

### Sound posture

- No stingers inside uninterrupted jargon chains.
- Bed trim ends at first word of next segment (see [post-generation-placement.md](../../cross-cutting/post-generation-placement.md)).
- Maximum duck; beds only in moderator questions between chains.

### Failure modes

| Failure | Symptom | Recovery |
|---------|---------|----------|
| Oversimplified brief | Thesis loses precision | `content_brief_reanchor` with transcript quotes |
| Stinger over word | Alignment missed pause | Check SAP `prefer_stinger_after_pause_tail` |
| Wrong audience | Show description too casual | Rewrite Flow 3 with expertise flag |

---

## trauma_adjacent

Sensitive personal history, grief, abuse, discrimination; dignity and consent posture.

### Signals

| Signal | Where to look |
|--------|---------------|
| Emotional beat tags: grief, fear, anger | `content_brief.emotional_beats` |
| Long pauses after heavy disclosures | SAP pause ladder |
| Interviewer softening questions | Tone shift in `interviewer` segments |
| Operator notes | `analysis_state.operator_notes` |

### Prompt adaptations

- **content_context:** Never sensationalize; `tone_class: trauma_informed`.
- **highlight_selection:** Exclude clips that retraumatize without context; no cold-open on disclosure peak.
- **transitions:** No cheerful pivots; acknowledge weight before topic shift.
- **podcast_show_description:** Content warnings when disclosure is central; no clickbait.
- **elevenlabs_prompt_craft:** No triumphant stingers after heavy segments.

### Sound posture

- Underscore policy: `skip` or single ultra-soft bed at −30 dB.
- Stingers forbidden for 2 min after tagged `emotional_beats` severity ≥ high.
- Flow 2: no montage through disclosure without surrounding context clips.

### Failure modes

| Failure | Symptom | Recovery |
|---------|---------|----------|
| Tonal whiplash | Upbeat SFX after grief | Edit SDP cues; re-run mix |
| Exploitative clip | Highlight isolates trauma | Re-rank; add framing clip |
| Missing warning | Publish without context | `podcast_show_description` + operator gate |

---

## Using this atlas in prompts

1. `content_context` sets `format_class` — downstream stages inherit via `analysis_state_summary`.
2. If format ambiguous, prefer **under-segmentation** and **higher missing_framing scrutiny**.
3. Sound stages read `source_acoustic_profile.mix_contract` + `placement_hints` — override defaults per scenario table above.
4. On conflict between atlas and operator `style_patch`, operator wins.

**Related:** [transcript-quality-rubric.md](./transcript-quality-rubric.md) · [guardrails-and-edge-cases.md](../sound_design/guardrails-and-edge-cases.md) · [stage-quality-scorecard.md](../../cross-cutting/stage-quality-scorecard.md)
