# Mastering audition loop

Audio-grounded evaluation for the Shape Engine and Realization. Canon: [mastering-quality-hardening.md](./mastering-quality-hardening.md).

**Principle:** a plan is a hypothesis. Judge the **rendered audio** before committing, and again before shipping.

---

## Two loops

| Loop | When | Scope | Cost |
|------|------|-------|------|
| **Micro-render audition** | Shape Engine, pre-L4 | 30–90 s excerpts per candidate | cheap |
| **Closed-loop polish** | Realization, post-mix | full preview / mix draft | one flagship pass + bounded remux |

---

## Micro-render auditions

### Selection

After diversity + feasibility + semantic integrity, take the top `max_auditions` survivors (default **3**, config `mastering.quality_hardening.auditions.max_auditions`).

### Window policy

Each audition renders up to three windows, total **30–90 s**:

| Window | Purpose | Default length |
|--------|---------|----------------|
| `opening` | Cold open as planned, or first body segment | 20 s |
| `hinge` | One planned transition / chapter boundary | 20 s |
| `dense` | Densest speech region (highest info rate) | 30 s |

Windows are concatenated with short silence markers into `preview.wav`. If a candidate has no cold open, `opening` renders the body start — the audition still shows how the episode *begins*.

### Layout

```
mastering/auditions/{candidate_id}/
  manifest.json      # mastering_audition_manifest.schema.json
  preview.wav
```

Manifest carries: window list (kind, source refs, start/end ms), total duration, acoustic feature summary, render warnings, and the plan hash it was rendered from.

### Acoustic features

Reuse existing analysis rather than new DSP where possible:

- Source acoustic profile patterns ([`acoustic_profile.py`](../../src/interview_mux/acoustic_profile.py))
- Intelligibility ceiling / speech-band checks ([`master_qc.py`](../../src/interview_mux/master_qc.py))
- MMAudio / CLAP semantic QA patterns ([`mmaudio_asset_qa.py`](../../src/interview_mux/mmaudio_asset_qa.py))

Summarized into `features`: integrated LUFS, peak, speech-band ratio, silence ratio, bed-under-speech margin, transition jolt estimate.

### What critics receive

Critics do **not** get raw audio bytes. They get:

- The audition manifest `features` block
- Window transcripts (from existing transcript slices)
- Render warnings
- The candidate plan excerpt

This keeps audio grounding while staying inside text volleys.

### Reuse

Build on the existing preview path ([`stages/assembly.py`](../../src/interview_mux/stages/assembly.py) `run_preview`) and timeline builders. **Never** render a full master per candidate.

---

## Closed-loop polish

```
mix draft / assembly_preview
  → audio-grounded polish audit (flagship)
  → remux directives (bounded)
  → re-render affected regions
  → re-audit (max rounds)
  → master_finalize → verify_master
```

### Polish audit scores

| Dimension | Detects |
|-----------|---------|
| `speech_masking` | Beds/SFX covering dialogue |
| `transition_jolt` | Abrupt level or tone changes at cuts |
| `dead_air` | Unintended silence runs |
| `sfx_repetition` | Same gesture reused mechanically |
| `listener_fatigue` | Flat energy, overlong uniform stretches |
| `cold_open_payoff` | Opening promise vs what the body delivers |
| `plan_adherence` | Rendered audio matches `mastering_plan` |

### Bounded remux

`max_remux_rounds` (default **2**). Each round may only emit directives within existing plan intent — level changes, cue removal, fade adjustments, silence trims. **Structural** changes (new segments, new shape) require a new Shape Engine pass, not a remux.

If audit still fails after the last round, record `verdict=fail` with residual issues and proceed to `master_finalize` (advisory mode) or block (authoritative mode).

---

## Auditions and hard delight

Both loops judge against the same rubric: the [Essence mutation space](./mastering-shape-engine.md#shape-as-mutation-engine) (native keep/order, synthetic inserts, music/SFX/air, soft duration ideal), not an independent audio-quality checklist.

- **Micro-render auditions** are the search's cheap feedback signal: acoustic features per window (speech-band ratio, bed-under-speech margin, transition jolt) let L4 critics judge a candidate's music/SFX/air and synthetic-insert mutations *before* spending a full mix.
- **Closed-loop polish** dimensions (`speech_masking`, `transition_jolt`, `dead_air`, `sfx_repetition`, `listener_fatigue`, `cold_open_payoff`, `plan_adherence`) each map onto one or more Essence axes — e.g. `speech_masking`/`sfx_repetition` are music/SFX/air weave failures; `dead_air` is an air-budget failure; `cold_open_payoff` is a synthetic-insert failure.
- **`mastering.listen_delight`** (see [listen_delight.py](../../src/interview_mux/listen_delight.py)) is the **terminal, authoritative judge** downstream of both loops — not merely an audio-quality pass. Its seven dimensions (`nugget_retention`, `cut_integrity`, `conversation_fit`, `sonic_weave`, `mode_coherence`, `finishability`, `recommendability`) each trace back to an Essence axis or its ensemble effect. A dimension below floor is a **remutate signal**: [mastering-shape-engine.md § Hard delight as the mutation forcing function](./mastering-shape-engine.md#hard-delight-as-the-mutation-forcing-function) names which capability module should re-enter the loop for that axis. When remutation isn't available, the authoritative floor failure blocks `master_finalize`/publish rather than shipping a plan the audit scored as undelightful.

---

## Config

```
mastering.quality_hardening.auditions.mode          off|advisory|authoritative
mastering.quality_hardening.auditions.max_auditions  3
mastering.quality_hardening.auditions.window_ms      {opening, hinge, dense}
mastering.quality_hardening.polish.max_remux_rounds  2
```
