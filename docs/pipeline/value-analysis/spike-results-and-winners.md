# Spike results and section winners

**Status:** in progress — one fixture row for `flow1-sound-and-mix`; other sections TBD. Scoring via [phase3-spike-framework.md](./phase3-spike-framework.md) and `tools/run_value_spike.py`.

## How to fill this doc

1. One **subsection per pipeline section** (see [sections/](./sections/) if you split by stage).
2. For each section: list **Promote** candidates with mean scores across chosen profiles; list **Park** / **Kill** / **Merge** with one-line rationale.
3. Allow winner = **“No external tool; prompt-only pattern”** if spikes show model adds no COM/LEX lift.

## Section winners (placeholder)

| Section | Winner (tool or pattern) | Profiles tested | Date | Owner |
|---------|--------------------------|-----------------|------|-------|
| shared-ingest-transcribe | *TBD* | | | |
| shared-g0-and-profile | *TBD* | | | |
| shared-understanding | *TBD* | | | |
| shared-segmentation | *TBD* | | | |
| shared-gaps-and-vo | *TBD* | | | |
| flow1-extended-narrative | *TBD* | | | |
| flow1-sound-and-mix | SDP + OpenAI craft + ElevenLabs per asset_id (`sdp_craft_path`) | listener-first, idea-first | 2026-05-28 | fixture spike |
| flow2-highlights | *TBD* | | | |
| flow3-show-description | *TBD* | | | |
| cross-orchestration-memory | *TBD* | | | |

## flow1-sound-and-mix — fixture spike (listener-first)

From `tests/fixtures/value_analysis/spike_flow1_sound.json` via `aggregate(..., profiles=["listener-first", "idea-first"])`:

| Rank | Candidate | Score | Outcome | Mechanism | Moonshot | Section fit |
|------|-----------|-------|---------|-------------|----------|-------------|
| 1 | SDP + OpenAI craft + ElevenLabs per asset_id | 3.9 | 3.889 | 4.0 | 3.667 | 4.0 |
| 2 | No external tool; prompt-only editorial pattern | 3.4 | 3.222 | 4.0 | 2.667 | 4.0 |
| 3 | v1 podcast_sfx_brief → ElevenLabs (no craft) | 3.342 | 3.222 | 3.5 | 3.333 | 4.0 |

`sdp_craft_path` ranks #1 on listener-first and idea-first; stable across those profiles.

## Deferred / killed (placeholder)

| Hypothesis ID | Verdict | Reason |
|----------------|---------|--------|
| — | — | — |
