# Local Audio Probe Platform + Vernacular Evidence Covenant

**Status:** Production-capable with STT-listen (once per flow). Default `enforcement_mode=shadow` is advisory; set `authoritative` for hard must_keep.

**North star:** one interview → `master/master.wav` with in-flow vernacular and other audio judgments preserved as golden facts.

## Listen-and-answer data architecture

```
docs/prompts/audio_probes/*.system.txt
        │ (optional warm-up TTS — not used by stt_listen answers)
        ▼
speaker_flow + ingest/normalized.wav
        → extract clip (once per flow that needs listen)
        → tools/s2s_interrogate.py classify  **once per flow**
              listen_mode=stt_listen → mlx Whisper STT
        → evidence cached on the flow
        → audio_probe_listen.answer_from_listen_evidence (all probes on that flow)
              fuse listen transcript with flow text
              → contract answer → golden facts / protected zones
```

Prompts document intended L&A contracts; v1 answers are derived from listen transcript + heuristics (not an audio LLM conditioned on the spoken system prompt).
| Layer | Module |
|---|---|
| CLI (speech venv) | `tools/s2s_interrogate.py` |
| Bridge | `src/interview_mux/audio_probe_mlx.py` |
| Evidence → answer | `src/interview_mux/audio_probe_listen.py` |
| Orchestrator | `src/interview_mux/audio_probe_orchestrator.py` |
| Neutral voice | `scripts/ensure_warmup_voice.py` → `ASSETS/local_speech/warmup_voice/neutral.wav` |

Fail-open: missing clip / STT / runtime → original-flow heuristics + structured logs.

## Pipeline stages

After `transcribe`, `audio_probe_build` writes golden facts, zones, flows, probe report, audio tags.

After `boundary_topic_resplit`, `vernacular_segment_sanitize` N-way splits parents, tags special children, writes must_keep + resplit report.

## Data contracts

| Producer | Consumer | Contract |
|---|---|---|
| `audio_probe_build` | LLM stages via `transcript_quality_for_ctx` | golden facts run flags + zone summary |
| `vernacular_segment_sanitize` | `selection_auto_pack` | authoritative must_keep hard-block; shadow logs `vernacular.shadow.would_keep` |
| same | `mastering_shape_gates` integrity | authoritative must_keep only |
| `GET /api/runs/{id}/audio-probes` | GUI `AudioProbesPanel` | read-only summary |
| corrupt/missing artifacts | all | empty safe payloads + logs when `fail_open` |

## Probe packs

Prompts: [`docs/prompts/audio_probes/`](../prompts/audio_probes/). Registry: `src/interview_mux/audio_probe_registry.py`.

Default `enforcement_mode` is `shadow`. Set `authoritative` to hard-block auto_pack drops.

## Config

See [config-keys.md](./config-keys.md) — `audio_probes.*`, `local_speech.interrogate_mode=stt_listen`.

## Related

- [multilingual-support.md](./multilingual-support.md)
- [segment-lineage.md](./segment-lineage.md)
