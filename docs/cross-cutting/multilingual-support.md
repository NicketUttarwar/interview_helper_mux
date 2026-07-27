# Multilingual source audio — implementation plan

## Purpose

This document describes what it would take for `interview_helper_mux` to accept interview **source audio in different languages** and produce a trustworthy `master/master.wav` **in the same language as that source**.

**Product rule:** source language = master language. Spanish interview audio yields a Spanish master; French yields French; English continues to work as today. The pipeline does not translate the episode, dub guest speech, or publish a different-language master.

This is not a single transcription setting. The current product has multilingual-capable building blocks, but its editorial contract is English-first. Supporting other source languages safely requires coordinated changes to transcription, artifact contracts, prompts, deterministic checks, transcript review, voice-over, quality evaluation, configuration, and test data.

## Product scope (v1)

### In scope

- Different **source audio languages** (one primary language per run).
- Final **spoken master** in that same primary language.
- Transcript, claims, gap scripts, and any new interviewer VO in that same language.
- Detect and **preserve** incidental code-switched words or phrases as spoken (do not translate them out of the master).
- Operator GUI chrome may stay English; interview content language follows the source.

### Out of scope (later products)

- Translating the master into another language.
- Dubbing or replacing guest/source speech with another language.
- Bilingual dual-track delivery.
- Localizing the operator UI.
- Optional analysis-only translation glosses as a required feature (may be explored later for operator convenience; never overwrite source text or change the master language).

## Current state

### What is already favorable

- The implemented STT model family is Whisper-based (`tools/stt_transcribe.py` and `src/interview_mux/stt_runner.py`), so the underlying model family is not inherently English-only.
- Transcript text is stored as Unicode JSON and the main audio pipeline is mostly language-neutral.
- G0 already requires a human transcript review before analysis.
- LLM stages receive the transcript rather than depending only on hand-written English NLP.
- The mastering strategy already forbids invented guest evidence and requires semantic-integrity checks.
- Sound design, EDL rendering, mixing, and loudness mastering mostly operate on timestamps and audio rather than language.

### What currently blocks trustworthy non-English source support

- The local STT command does not expose or persist a language choice, auto-detection result, or transcription-versus-translation task.
- The legacy AWS adapter hard-codes `en-US` in `src/interview_mux/stages/transcribe_aws.py`.
- `transcript/full.json` has no run-, segment-, or token-level language metadata.
- `tools/stt_transcribe.py`, `src/interview_mux/stages/transcript_review.py`, and several consumers assume whitespace-delimited “words.” This is unreliable for languages such as Chinese, Japanese, and Thai.
- The fallback transcript path can assign every whitespace token the same segment timestamps.
- The English prompt constitution explicitly judges comprehension for a “general English podcast listener” and contains English-specific dialect and code-switch rules.
- Some deterministic semantic checks use English lexical markers such as `not`, `never`, `if`, `because`, and English pronouns. Those checks cannot silently be treated as valid in other languages.
- `frontend/src/utils/fuzzyMatch.ts` uses ASCII-oriented `\w` normalization, which can strip non-Latin transcript tokens during fuzzy replacement.
- Pacing and VO estimates in `src/interview_mux/stages/understanding.py`, `src/interview_mux/value_analysis/features_transcript.py`, and `src/interview_mux/gap_framing.py` use English-oriented words-per-minute or words-per-second assumptions.
- Text retrieval and theme comparison include whitespace- or Latin-oriented tokenization, including `src/interview_mux/interview_spine/retrieval.py` and `src/interview_mux/coherence/theme_alignment.py`.
- The transcript-quality helper does not currently carry the documented `dialect_hint`, detected languages, or language-span confidence into downstream stages.
- The GUI has no run-language selection, detected-language confirmation, code-switch display, right-to-left handling contract, or language-aware input guidance.
- New VO scripts and synthesis are not gated by a declared language or by a tested backend/language capability matrix.
- The quality corpus is not organized around language coverage or native-speaker review.

The result is that non-English source audio may transcribe and flow through the pipeline, but the application cannot currently prove that analysis, edits, gap detection, VO, or semantic checks are correct for that language—or that the master stayed in the source language.

## Target language contract

Add one authoritative language profile early in the run, preferably at:

`transcript/language_profile.json`

It should contain:

```json
{
  "version": 1,
  "selection_mode": "auto_confirmed",
  "primary_language": "es-ES",
  "observed_languages": ["es-ES", "en-US"],
  "code_switching": true,
  "master_language": "es-ES",
  "operator_display_language": "en-US",
  "detection_confidence": 0.96,
  "confirmed_by": "operator",
  "confirmed_at": "..."
}
```

**Invariant:** `master_language` always equals `primary_language` (the confirmed source language). There is no separate editorial-output language in v1.

Use BCP 47 language tags where a locale is known. Permit a base language such as `es` when the locale is unknown. Do not infer nationality or dialect from a voice.

Extend the transcript contract without deleting source text:

- Run-level `primary_language` / `master_language` (same value).
- Segment-level `language` and `language_confidence`.
- Optional language spans for incidental code-switching.
- Optional token-level language only where the STT provider supplies reliable data.
- Immutable `source_text` in the language spoken on the tape.
- A segmentation unit that can be a provider word, token, or timed text span instead of assuming every language has whitespace-delimited words.

`source_text` remains authoritative for quotations, clip boundaries, G0 correction, evidence, and the spoken master. Analysis and VO must operate on that text, not on a translated substitute.

## Required workstreams

### 1. Product and operator policy

Add a language step during Start or Prepare:

- Choose `Auto-detect` or a specific **source** language.
- Confirm the detected primary language before completing G0.
- Display that the master will be produced in that same language.
- Warn when more than one language is detected on the tape.

Define behavior for:

- A single non-English primary language.
- Regional variants and dialects of that language.
- Incidental code-switching inside a sentence or turn (preserve; do not treat as a different master language).
- Multiple speakers who mostly share one primary language.
- An operator who cannot review the source language.
- Unsupported STT, analysis, or VO languages for that source.

For the first release, an operator who cannot validate the source language should see a trust warning. G0 is only a meaningful quality gate when the reviewer can understand the audio or a qualified reviewer is involved.

### 2. STT and diarization

Update the local STT path to accept:

- `--language <BCP-47-or-model-code>` or auto-detect.
- `--task transcribe` only — **never** translate source audio into English (or any other language).
- Language-detection metadata in its output.
- Segment-level language labels where available.

Then pass those options from:

- `config/app.defaults.json`
- `src/interview_mux/stt_runner.py`
- `src/interview_mux/stages/transcribe_local.py`
- `tools/stt_transcribe.py`

The exact argument shape must be verified against the pinned `mlx-audio` version before implementation.

Replace the AWS `en-US` constant if that legacy path remains supported. Use explicit language selection or the provider’s language-identification mode, then normalize the result into the same contract.

Diarization should be evaluated separately from language accuracy. Current fallback behavior that alternates speakers on pauses can corrupt conversation structure in any language. A language launch should include real two-speaker and overlapping-speech fixtures for each pilot language.

### 3. Transcript normalization and timing

Refactor transcript normalization so downstream code does not equate “token separated by a space” with “safely editable timed word.”

Required changes:

- Preserve provider-native segments and timing.
- Represent untimed or segment-timed tokens honestly rather than manufacturing precise word boundaries.
- Add script-safe tokenization for review and search.
- Make word-count heuristics language-aware or replace them with duration, characters, graphemes, syllables, or model tokens as appropriate.
- Preserve Unicode normalization consistently without stripping diacritics.
- Test punctuation attached to right-to-left and CJK text when those scripts are in pilot scope.
- Ensure transcript correction can update text without breaking source-time alignment.

The EDL must cut on verified acoustic or provider boundaries in the source-language timeline.

### 4. G0 transcript review and GUI

Extend the transcript review payload and interface with:

- Detected and confirmed source/master language.
- Language badges on code-switched spans.
- Source-language editing as the only authoritative transcript view.
- `dir="auto"` or explicit right-to-left rendering when needed.
- IME-safe editing for CJK and other composed input.
- Unicode-aware search and replacement.
- Fonts and line wrapping that work for the pilot scripts.
- Warnings for low language-detection confidence.

Review-queue ranking should account for language confidence in addition to STT confidence and acoustic stress. The operator GUI chrome can remain English; interview content stays in the source language.

### 5. LLM context and prompts

Replace the static “English editorial standards” section in authoritative prompts with a generated language policy included in every relevant LLM volley.

The shared policy should declare:

- Confirmed source language (= master language).
- Intended listener: a native or fluent listener of that language.
- That all analysis outputs, gap scripts, and framing VO must be written in that language.
- That source text controls quotations and evidence.
- How to handle names, honorifics, formality, dialect, idiom, and incidental code-switching.
- That a model must report uncertainty instead of silently translating content into English (or any other language).

Audit every prompt under `docs/prompts/`, especially:

- Shared analysis preamble and scenario atlas.
- Content context and speaker roles.
- Boundary detection and segment classification.
- Missing framing and optimal questions.
- Coverage, narrative planning, ranking, and transitions.
- Mastering research, shape, critics, semantic integrity, and polish.
- Any generated VO script.

Prompts in `docs/prompts/` remain authoritative. Python should inject the run’s language profile; it should not maintain a second copy of editorial language rules.

Model routing also needs a capability policy. A configured model must be certified for the run’s source language and required structured output. Unsupported combinations should stop before analysis or require an explicit, visible degraded-mode decision.

### 6. Deterministic analysis and semantic integrity

Inventory all English lexical heuristics. The semantic-integrity design currently names English negation, conditional, causal, and referent markers. Similar assumptions may exist in filler detection, jargon handling, sentence boundaries, salience scoring, and comprehension-risk checks.

For each heuristic, choose one of:

- A tested language-specific lexicon or parser for the pilot language.
- A Unicode/script-neutral acoustic or structural check.
- An LLM judgment over a bounded evidence window in the source language.
- Disabled with a visible “not evaluated for this language” result.

Never report a non-English run as having passed a check that was actually skipped.

Semantic integrity must compare **source-language** context. Critical findings still block a mastering candidate in authoritative mode.

### 7. Gap analysis, framing scripts, and voice

Every proposed VO line needs:

- `language` equal to `master_language` / `primary_language`.
- Source evidence references in that same language.
- A pronunciation plan for names, acronyms, and borrowed terms.
- A check that the selected voice backend supports that language.

Chatterbox and the MLX/Qwen synthesis fallback must be tested, not assumed, per language and script. Certification should cover intelligibility, pronunciation, speaker similarity, incidental code-switching, punctuation, numbers, and long-form prosody.

If no backend is certified for the source language:

- Fall back to manual recording **in that language**.
- Keep the rest of the episode usable.
- Explain the fallback in G1.
- **Do not** synthesize English VO for a non-English master.

Voice-clone consent and the absolute ban on guest cloning remain unchanged. Add language and script text to `mastering/voice_clone_audit.json` and synthesis reports so every generated utterance remains attributable.

### 8. Mastering and sound

Most waveform operations do not need language-specific branches:

- Ingest and preclean.
- EDL rendering from trusted timestamps.
- Crossfades and speech-first ducking.
- SFX and music generation that contain no speech.
- Loudness and true-peak verification.

The language-sensitive parts are speech-rate estimation, pause interpretation, intelligibility auditing, VO placement, lyric/voice-like SFX rejection, and listener-fatigue judgments. Pace should prefer duration and syllable- or script-aware measures over raw whitespace word counts.

MMAudio prompts may stay in English as craft instructions to the sound model when that is intentional and documented; generated beds/stingers must not introduce intelligible speech in the wrong language under dialogue.

### 9. Schemas, validators, and provenance

Add or update schemas for:

- Language profile (`primary_language` = `master_language`).
- Full transcript and timed units.
- Transcript review and corrections.
- Transcript-quality summaries.
- Content context and speaker metadata where language is relevant.
- Gap reports and VO lines (language must match master).
- Mastering evidence packets, plans, semantic-integrity reports, and audits.

Update prompt validation, artifact completeness, cross-validation, compactors, reuse fingerprints, and stage invalidation. A language-policy change must invalidate STT when it changes recognition behavior and invalidate downstream analysis whenever the confirmed source/master language changes.

Add a hard check: any VO or publishing speech artifact whose `language` differs from `master_language` fails validation for v1.

### 10. Quality corpus and evaluation

Do not launch based only on “the model says it supports the language.” Add real, licensed fixtures and native-speaker review of both transcript and **same-language master**.

A practical pilot corpus should include:

- One Latin-script language with punctuation and inflection unlike English.
- One non-Latin script if in launch scope.
- One right-to-left language if RTL is in launch scope.
- One interview with incidental code-switching into another language.
- Two or more speakers, interruptions, names, numbers, acronyms, emotion, room noise, and music bleed.
- An English regression set to prove no loss in the existing path.

Measure:

- STT word or character error rate, with named-entity accuracy separately.
- Diarization error and speaker-turn integrity.
- Language identification accuracy.
- G0 correction effort per audio minute.
- Claim fidelity against source speech.
- Boundary and EDL cut correctness.
- Gap detection false positives caused by language or culture.
- VO intelligibility and pronunciation from native listeners **in the source language**.
- Semantic-integrity critical miss rate.
- Final-master preference and trust ratings from native listeners of that language.
- Confirmation that the master contains no systematic translation into English (or another language).

Automated tests should include schema round trips, Unicode and RTL fixtures, code-switch preservation, prompt-language injection, skipped-check disclosure, backend capability rejection, manual-VO fallback, and `master_language == primary_language` enforcement.

## Staged delivery plan

### Phase 0 — decisions and spike

Duration: roughly 3–5 engineering days plus reviewer scheduling.

- Select two or three pilot **source** languages (plus English regression).
- Confirm the invariant: master language always equals source language.
- Verify the pinned STT and VO APIs and run short same-language capability samples.
- Identify qualified native-language reviewers for each pilot language.
- Freeze the v1 language artifact contract and acceptance thresholds.

Exit condition: a written support matrix names what source languages are supported, degraded, and rejected for same-language mastering.

### Phase 1 — language-aware transcription and G0

Duration: roughly 2–3 engineering weeks.

- Implement the language profile and configuration (`primary_language` = `master_language`).
- Pass language/task through local STT (`transcribe` only).
- Persist detected language and segment metadata.
- Refactor normalization away from mandatory whitespace words.
- Add GUI selection, confirmation, and RTL/IME basics as needed for pilots.
- Add schemas and STT/G0 fixtures.

Exit condition: a native reviewer can produce an accurate, time-aligned transcript in the source language.

### Phase 2 — language-aware analysis and planning

Duration: roughly 2–4 engineering weeks.

- Inject the dynamic language policy into LLM stages (listener = source-language listener).
- Remove or gate English-only prompt language when the run is not English.
- Audit deterministic lexical checks per pilot language.
- Keep claims, segments, evidence packets, and mastering plans tied to source-language text.
- Add per-language model capability checks and evaluations.

Exit condition: claims, structure, exclusions, and semantic-integrity decisions trace to source-language evidence and pass native review.

### Phase 3 — same-language VO and final-master hardening

Duration: roughly 2–3 engineering weeks for a small certified language set.

- Add language to framing lines and synthesis requests (must match master).
- Certify each VO backend/language pair.
- Implement pronunciation handling and manual-record fallback in the source language.
- Add language-aware pacing and intelligibility evaluation.
- Run end-to-end auditions and native-listener master reviews.

Exit condition: every generated line is in the source/master language, authorized, intelligible, source-supported, and fully audited.

### Phase 4 — broader source-language expansion

Each new source language is a capability release, not just a config entry. Add fixtures, native review, prompt evaluation, STT thresholds, VO status, known limitations, and regression results before marking it supported for same-language mastering.

## Refinement Pass language packs (deferred)

[Refinement Pass](./refinement-passes.md) policy packs (`refinement_policy.POLICY_PACKS`) currently key off tape shape (`short_clean`, `asymmetric_technical`, `panel_multi_guest`, `long_meander`, `default`) and are English-listener tuned — pacing kernels such as `vo_second_budget` assume words-per-second and the listener rubric (`refinement_accept.score_gap_report`) assumes English sentence structure for clarity/succinctness/hook scoring. These are **docs-only hooks for now**, not implemented:

- A `language`-keyed dimension alongside `tape_character` in `refinement_agenda.json`, so policy packs can vary eligible classes per source language once Phase 2 (language-aware analysis) lands.
- Locale-aware `vo_second_budget` (words-per-second varies materially by language and script).
- Priors (`refinement_priors.py`) segmented by `(language, tape_character)` instead of `tape_character` alone, so accept-rate bias does not leak across languages.

None of this blocks same-language mastering for English today; Refinement Pass runs unchanged (English-tuned defaults) regardless of source language until this work is scheduled.

## Effort estimate

For two or three pilot source languages, same-language masters, an English operator GUI, and no translation/dubbing:

- **Narrow proof of concept:** approximately 4–6 engineering weeks. It can demonstrate transcription and analysis but should not claim production-grade support.
- **Production pilot:** approximately 8–12 engineering weeks, plus native-speaker editorial/QA time.
- **Broader supported language catalog:** ongoing certification work per source language.

Translation, localization, or dubbed delivery are separate projects and are not part of this estimate.

The largest uncertainty is not audio mixing. It is proving editorial and semantic fidelity across STT, LLM analysis, incidental code-switching, and generated VO **while keeping the master in the source language**.

## Release criteria

A source language can be marked supported only when all of the following are true:

- The run’s source/master language is explicit, equal, and persisted.
- STT uses `transcribe` (not translate) and meets agreed thresholds on representative audio.
- G0 can display and edit the source-language script correctly.
- Source text survives every artifact and remains the evidence authority.
- All LLM stages receive and follow the same-language policy.
- English-only deterministic checks are replaced, certified, or visibly skipped.
- Unsupported model or VO combinations fail clearly before producing misleading output.
- Generated VO is in the source/master language, language-tagged, consented, audited, and native-reviewed.
- Incidental code-switching is preserved rather than silently translated or deleted.
- Native reviewers approve claim fidelity, narrative meaning, and final-master trust **in that language**.
- Existing English fixtures and `master/master.wav` verification still pass.

## Recommended first implementation slice

Start with one non-English Latin-script source language (for example Spanish) plus English regression. Build the language profile (`primary_language` = `master_language`), STT `transcribe`-only controls, G0 language confirmation, shared prompt policy for a source-language listener, and skipped-check disclosure before adding synthetic VO.

That slice tests the foundational architecture while preserving two hard rules: the master stays in the source language, and the application must not create a polished master whose words are authentic but whose meaning is wrong.
