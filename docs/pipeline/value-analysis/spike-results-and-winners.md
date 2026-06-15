# Spike results and section winners

**Status:** fixture sprint complete for all pipeline sections (2026-05-28). Scoring via [phase3-spike-framework.md](./phase3-spike-framework.md) and `tools/run_value_spike.py` (requires `value_analysis.enabled`).

## How to fill this doc

1. One **subsection per pipeline section** (see [sections/](./sections/) if you split by stage).
2. For each section: list **Promote** candidates with mean scores across chosen profiles; list **Park** / **Kill** / **Merge** with one-line rationale.
3. Allow winner = **“No external tool; prompt-only pattern”** if spikes show model adds no COM/LEX lift.

## Section winners

| Section | Winner (tool or pattern) | Profiles tested | Date | Owner |
|---------|--------------------------|-----------------|------|-------|
| shared-ingest-transcribe | NISQA-class quality trajectories (`quality_trajectory_flags`) | listener-first, idea-first | 2026-05-28 | fixture spike |
| shared-g0-and-profile | Communicative salience queue (`communicative_salience_queue`) | listener-first, idea-first | 2026-05-28 | fixture spike |
| shared-understanding | LLM + prosodic clustering validation (`llm_acoustic_beats`) | listener-first, idea-first | 2026-05-28 | fixture spike |
| shared-segmentation | Neural VAD pause ladder (`pause_ladder_vad`) | listener-first, idea-first | 2026-05-28 | fixture spike |
| shared-gaps-and-vo | Blind comprehension-risk scoring (`comprehension_risk_blind`) | listener-first, idea-first | 2026-05-28 | fixture spike |
| flow1-extended-narrative | Acoustic emphasis coverage (`acoustic_emphasis_coverage`) | listener-first, idea-first | 2026-05-28 | fixture spike |
| flow1-sound-and-mix | SDP + OpenAI craft + MMAudio per asset_id (`sdp_craft_path`) | listener-first, idea-first | 2026-05-28 | fixture spike |
| flow2-highlights | Paralinguistic × quotability fusion (`paralinguistic_quotability`) | listener-first, idea-first | 2026-05-28 | fixture spike |
| flow3-show-description | Evidence-anchored show notes (`evidence_anchored_hype`) | listener-first, idea-first | 2026-05-28 | fixture spike |
| cross-orchestration-memory | Acoustic anomaly + text ambiguity queue (`acoustic_anomaly_investigations`) | listener-first, idea-first | 2026-05-28 | fixture spike |

---

## shared-ingest-transcribe

Fixture: `tests/fixtures/value_analysis/spike_shared_ingest_transcribe.json`

| Rank | Candidate | Score | Outcome | Mechanism | Moonshot | Section fit |
|------|-----------|-------|---------|-------------|----------|-------------|
| 1 | NISQA-class quality trajectories over time (H-ING-03) | 3.738 | 3.778 | 3.75 | 3.333 | 4.0 |
| 2 | AWS Transcribe CLI + ingest normalize (current path) | 3.729 | 3.556 | 4.25 | 3.333 | 4.0 |
| 3 | No external tool; prompt-only editorial pattern | 3.4 | 3.222 | 4.0 | 2.667 | 4.0 |

Stable on listener-first and idea-first. **Promote** H-ING-03 quality trajectories for trust-dip flagging. **Park** current AWS path (strong MEC-D, narrow LEX lift). **Kill** prompt-only for ingest (no time-aligned language signal).

Metric link: [value-metrics-library.md §2 — MOS-like predictor](./value-metrics-library.md#2-model-proxies-allowed-with-caveats) (LEX-B regions).

---

## shared-g0-and-profile

Fixture: `tests/fixtures/value_analysis/spike_shared_g0_and_profile.json`

| Rank | Candidate | Score | Outcome | Mechanism | Moonshot | Section fit |
|------|-----------|-------|---------|-------------|----------|-------------|
| 1 | Communicative salience + idea-break risk queue (H-G0-01) | 4.037 | 4.222 | 3.75 | 3.667 | 4.0 |
| 2 | ASR confidence-ranked review queue (current G0) | 3.529 | 3.222 | 4.25 | 3.333 | 4.0 |
| 3 | No external tool; prompt-only editorial pattern | 3.4 | 3.222 | 4.0 | 2.667 | 4.0 |

Stable across profiles. **Promote** H-G0-01 salience-ranked queue. **Park** confidence-only ordering (safe fallback). **Kill** prompt-only queue (no operator throughput gain).

Metric link: [value-metrics-library.md §1.3 — Operator timed task](./value-metrics-library.md#13-operator-timed-task-cre-b) (CRE-B decision latency).

---

## shared-understanding

Fixture: `tests/fixtures/value_analysis/spike_shared_understanding.json`

| Rank | Candidate | Score | Outcome | Mechanism | Moonshot | Section fit |
|------|-----------|-------|---------|-------------|----------|-------------|
| 1 | LLM beats + prosodic clustering validation (H-UND-01/03) | 3.904 | 4.0 | 3.75 | 3.667 | 4.0 |
| 2 | LLM speaker_roles + content_context only (current path) | 3.729 | 3.556 | 4.25 | 3.333 | 4.0 |
| 3 | No external tool; prompt-only editorial pattern | 3.4 | 3.222 | 4.0 | 2.667 | 4.0 |

Stable across profiles. **Promote** acoustic validation of emotional beats. **Park** LLM-only path until prosody features ship. **Kill** prompt-only beats (no role/beat alignment signal).

Metric link: [tools-not-in-repo-landscape.md — Lever A prosody/affect](./tools-not-in-repo-landscape.md#lever-a--find-the-emotional-authentic-peak) (openSMILE-class).

---

## shared-segmentation

Fixture: `tests/fixtures/value_analysis/spike_shared_segmentation.json`

| Rank | Candidate | Score | Outcome | Mechanism | Moonshot | Section fit |
|------|-----------|-------|---------|-------------|----------|-------------|
| 1 | Neural VAD pause ladder split hints (H-SEG-02) | 4.033 | 4.111 | 4.0 | 3.667 | 4.0 |
| 2 | LLM boundaries + fixed 700ms pause heuristic (current path) | 3.729 | 3.556 | 4.25 | 3.333 | 4.0 |
| 3 | No external tool; prompt-only editorial pattern | 3.4 | 3.222 | 4.0 | 2.667 | 4.0 |

Stable across profiles. **Promote** H-SEG-02 pause ladder over single threshold. **Park** fixed 700ms heuristic (documented editorial guide). **Kill** prompt-only boundaries (no boundary-truth lift).

Metric link: [value-metrics-library.md §1.1 — Listener Likert](./value-metrics-library.md#11-listener-likert-1-5) adapted for boundary truth (SectionFit).

---

## shared-gaps-and-vo

Fixture: `tests/fixtures/value_analysis/spike_shared_gaps_and_vo.json`

| Rank | Candidate | Score | Outcome | Mechanism | Moonshot | Section fit |
|------|-----------|-------|---------|-------------|----------|-------------|
| 1 | Blind listener comprehension-risk scoring (H-GAP-01) | 4.037 | 4.222 | 3.75 | 3.667 | 4.0 |
| 2 | Speaking rate + pause structure cognitive-load proxy (H-GAP-02) | 3.804 | 3.889 | 3.75 | 3.333 | 4.0 |
| 3 | No external tool; prompt-only editorial pattern | 3.4 | 3.222 | 4.0 | 2.667 | 4.0 |

Stable across profiles. **Promote** blind comprehension-risk protocol. **Park** H-GAP-02 rate/pause proxy (cheap CRE pre-filter). **Kill** prompt-only gap pass (no COM uplift evidence).

Metric link: [value-metrics-library.md §1.2 — Retell protocol](./value-metrics-library.md#12-retell-protocol-com-a-com-b) (COM-A/COM-B with/without VO).

---

## flow1-extended-narrative

Fixture: `tests/fixtures/value_analysis/spike_flow1_extended_narrative.json`

| Rank | Candidate | Score | Outcome | Mechanism | Moonshot | Section fit |
|------|-----------|-------|---------|-------------|----------|-------------|
| 1 | Coverage weighted by acoustic emphasis (H-F1N-02) | 4.037 | 4.222 | 3.75 | 3.667 | 4.0 |
| 2 | LLM coverage + arc + ranking + transitions (current path) | 3.929 | 3.889 | 4.25 | 3.333 | 4.0 |
| 3 | No external tool; prompt-only editorial pattern | 3.4 | 3.222 | 4.0 | 2.667 | 4.0 |

Stable across profiles. **Promote** acoustic emphasis weighting for quiet-but-vital claims. **Park** current LLM narrative stack. **Kill** prompt-only arc (no arc-coherence lift).

Metric link: [value-metrics-library.md §1.2 — Retell protocol](./value-metrics-library.md#12-retell-protocol-com-a-com-b) (blind chapter order A/B).

---

## flow1-sound-and-mix

Fixture: `tests/fixtures/value_analysis/spike_flow1_sound.json`

| Rank | Candidate | Score | Outcome | Mechanism | Moonshot | Section fit |
|------|-----------|-------|---------|-------------|----------|-------------|
| 1 | SDP + OpenAI craft + MMAudio per asset_id | 3.9 | 3.889 | 4.0 | 3.667 | 4.0 |
| 2 | No external tool; prompt-only editorial pattern | 3.4 | 3.222 | 4.0 | 2.667 | 4.0 |
| 3 | v1 podcast_sfx_brief → MMAudio (legacy) (no craft) | 3.342 | 3.222 | 3.5 | 3.333 | 4.0 |

Stable across profiles. **Promote** `sdp_craft_path`. **Park** v1 brief-direct path (fast but weaker COM). **Kill** prompt-only SFX (no sonic intent fit).

Metric link: [value-metrics-library.md §1.4 — Clip A/B protocol](./value-metrics-library.md#4-clip-ab-protocol) (LEX-B sonic trust).

---

## flow2-highlights

Fixture: `tests/fixtures/value_analysis/spike_flow2_highlights.json`

| Rank | Candidate | Score | Outcome | Mechanism | Moonshot | Section fit |
|------|-----------|-------|---------|-------------|----------|-------------|
| 1 | Paralinguistic peaks × quotability fusion (H-F2-02) | 3.971 | 4.111 | 3.75 | 3.667 | 4.0 |
| 2 | LLM highlight_selection schema (current path) | 3.929 | 3.889 | 4.25 | 3.333 | 4.0 |
| 3 | No external tool; prompt-only editorial pattern | 3.4 | 3.222 | 4.0 | 2.667 | 4.0 |

Stable across profiles. **Promote** H-F2-02 paralinguistic × quotability fusion. **Park** LLM-only highlight schema. **Kill** prompt-only picks (flat hook strength).

Metric link: [tools-not-in-repo-landscape.md — Lever A paralinguistic events](./tools-not-in-repo-landscape.md#lever-a--find-the-emotional-authentic-peak) (laughter/applause detectors).

---

## flow3-show-description

Fixture: `tests/fixtures/value_analysis/spike_flow3_show_description.json`

| Rank | Candidate | Score | Outcome | Mechanism | Moonshot | Section fit |
|------|-----------|-------|---------|-------------|----------|-------------|
| 1 | Evidence-anchored show notes tied to segment_ids (H-F3-01) | 4.258 | 4.222 | 4.5 | 4.0 | 4.0 |
| 2 | Flagship tier + full user/assistant volley (current path) | 3.863 | 3.778 | 4.25 | 3.333 | 4.0 |
| 3 | No external tool; economy one-shot blurb | 3.4 | 3.222 | 4.0 | 2.667 | 4.0 |

Stable across profiles. **Promote** H-F3-01 evidence-anchored copy. **Park** flagship volley (strong prose, weaker factual guardrails). **Kill** economy one-shot (CRE-C/explainability floor).

Metric link: [value-metrics-library.md §1.3 — Operator timed task](./value-metrics-library.md#13-operator-timed-task-cre-b) (CRE-C explainability audit vs `key_claims`).

---

## cross-orchestration-memory

Fixture: `tests/fixtures/value_analysis/spike_cross_orchestration_memory.json`

| Rank | Candidate | Score | Outcome | Mechanism | Moonshot | Section fit |
|------|-----------|-------|---------|-------------|----------|-------------|
| 1 | Acoustic anomaly + text ambiguity investigation queue (H-ORC-02) | 4.071 | 4.222 | 3.75 | 4.0 | 4.0 |
| 2 | analysis_state.json + text-only investigation queue (current path) | 3.729 | 3.556 | 4.25 | 3.333 | 4.0 |
| 3 | No external tool; prompt-only editorial pattern | 3.4 | 3.222 | 4.0 | 2.667 | 4.0 |

Stable across profiles. **Promote** H-ORC-02 joint acoustic+text investigation triggers. **Park** text-only `analysis_state` queue. **Kill** prompt-only memory (no long-run coherence signal).

Metric link: [tools-not-in-repo-landscape.md — Lever E anomaly triggers](./tools-not-in-repo-landscape.md#lever-e--long-run-coherence-memory) (acoustic surprise + text ambiguity).

---

## H-ING-01 T0 spike — SSL idea-density

**Date:** 2026-05-28 · **Verdict:** **Park** (no code or lockfile changes)

Command 8 gate: proceed only if Command 7 recommends SSL for a section. Command 7 fixture sprint promoted **H-ING-03** (NISQA-class quality trajectories, global score 3.738) over the current AWS ingest path (3.729) and explicitly parked H-ING-01 in the deferred table. SSL was not the section winner on either listener-first or idea-first profiles.

### Why not implement `ssl_density` now

| Factor | Assessment |
|--------|------------|
| Command 7 recommendation | H-ING-03 promoted; H-ING-01 parked — gate not met |
| Lift vs existing `audio` profile | No empirical comparison on `ingest/normalized.wav`; existing profile (`silence_ratio`, `rms_p50`/`rms_p90`, `peak_dbfs_proxy`) already covers coarse trust/dynamics without ~2 GB `torch`/`transformers` stack |
| Dependency cost | Wav2Vec2/HuBERT (Family 1) requires `torch` + `transformers` + model weights — violates “do not merge heavy deps” when lift is unproven |
| Spike shape (Family 1) | Needs human boundary-truth marks correlated with frame-level \|h\| deltas; no listener/operator study run in this sprint |
| Reversibility | N/A — feature not shipped |

### Revisit when

1. H-ING-03 quality-trajectory extractor ships and ingest has stable `normalized.wav` fixtures.
2. Operator or listener study shows SSL change-points correlate with idea switches **beyond** NISQA trust dips + transcript change-points.
3. Spike adds pinned versions to [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md) optional research table and passes `pip-audit`.

**Next action:** Park. Do not add `value_analysis.ssl_features` or `features_ssl.py` until the above gates clear.

---

## Deferred / killed (cross-section)

| Hypothesis ID | Verdict | Reason |
|----------------|---------|--------|
| H-ING-01 | Park | T0 spike (2026-05-28): Command 7 did not recommend SSL; no lift vs `audio` profile without heavy deps — see [§ H-ING-01 T0](#h-ing-01-t0-spike--ssl-idea-density) |
| H-ING-04 | Park | Alternate ASR + forced alignment T1; revisit after ingest winner ships |
| H-SEG-01 | Park | Wav2Vec2 boundary fusion deferred — SSL out of scope for fixture sprint |
| H-F2-01 | Park | CLAP text-query retrieval deferred — optional Tier 2 semantic QA now shipped opt-in via `mmaudio.semantic_qa_enabled` (supersedes parked spike) |
| H-F1S-01 | Park | CLAP sting matching deferred — use opt-in CLAP in `semantic_audio_qa.py` when tuning; not default-on |
| H-ORC-01 | Park | Chunked embedding spine T1; ship after investigation trigger wins |
| H-ORC-03 | Park | T2 moonshot; needs 90m+ planted-contradiction fixture |
| prompt_only_pattern (all sections) | Kill | Baseline floor only; no novel evidence channel (MEC-A ≤ 1) |
