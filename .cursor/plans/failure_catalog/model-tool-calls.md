# Model & local-tool call-site register

Identify-only. HEAD. Brain 0.1.0.

---

### MTL-OA-01 — OpenAI via llm_simple

- Surface: LLM
- Modes: all
- Call graph: `stages/analysis_stage.py` / delivery runners → `llm_simple.run_llm_stage_simple` → OpenAI
- Invariant: schema validate → max 2 attempts → StageError
- Why weak: hard stop with no arbiter UI; heal must map to producer; spend/skip paths
- Likelihood: L2 | Severity: S3
- Evidence: `llm_simple.py`, `analysis_stage.py`
- Fix-cluster: `llm-hard-stop-routing`
- Status: OPEN_RISK

### MTL-OA-02 — OpenAI via homunculus loop gateway

- Surface: LLM / homunculus
- Modes: 0.1.0 runs
- Call graph: nested LLM → `homunculus/loop.py:nested_chat_create` → packer → create; conductor tool loop separately
- Invariant: budget + ledger + admit; packed user turns
- Why weak: LimitExhausted; ledger desync; CTA cover exempt path
- Likelihood: L2 | Severity: S3
- Evidence: `homunculus/loop.py`
- Fix-cluster: `homunculus-budget-ledger`
- Status: OPEN_RISK

### MTL-COVER-01 — episode_cover_generate cascade

- Surface: LLM / local
- Modes: all (ship tail)
- Call graph: cover prompt craft → generate candidates → vision pick prompts under `docs/prompts/publishing/`
- Why weak: vision pick fails; cascade partial; SHIP_AFTER_MASTER without committed master
- Likelihood: L2 | Severity: S2
- Evidence: podcast/cover stages; publishing prompts
- Fix-cluster: `ship-tail-cover`
- Status: OPEN_RISK

### MTL-MLX-STT-01 — local STT / diarization venv

- Surface: local-ML
- Modes: all (Prepare)
- Call graph: transcribe stage → ASSETS/local_speech/venv (per docs)
- Why weak: venv missing → hard fail; Partial reaches G0 on STT quality; no cloud fallback
- Likelihood: L2 | Severity: S3
- Evidence: local-audio-stack.md; transcribe stage modules
- Fix-cluster: `local-ml-venvs`
- Status: OPEN_RISK

### MTL-MLX-FRAMER-01 — local volley framer fail-open

- Surface: local-ML
- Modes: 0.1.0
- Call graph: local framer prompt `docs/prompts/_shared/local-volley-framer.system.txt`; `local_framer_response.schema.json`
- Why weak: fail-open may drop framing quality silently
- Likelihood: L2 | Severity: S2
- Evidence: llm_interaction_registry LOCAL_FRAMER; docs
- Fix-cluster: `local-ml-venvs`
- Status: OPEN_RISK

### MTL-PROBE-01 — audio probes MLX prefer + heuristic fallback

- Surface: local-ML
- Modes: all
- Call graph: `audio_probe_orchestrator` → `classify_clip_mlx` or heuristic_after_mlx
- Why weak: heuristic fallback marks probes “done” with weaker evidence → downstream trust
- Likelihood: L2 | Severity: S2
- Evidence: `audio_probe_orchestrator.py`
- Fix-cluster: `audio-probe-fallback`
- Status: OPEN_RISK

### MTL-CHATTERBOX-01 — VO synthesize

- Surface: local-ML
- Modes: all (G1 / vo_synthesize)
- Call graph: `vo_synthesize` → Chatterbox clone; voice-ref gate; script↔WAV audit
- Why weak: missing voice-ref blocks coverage audit; WAV bind thrash; pending flush
- Likelihood: L3 | Severity: S4
- Evidence: vo_synthesize stage; vo_synthesis_audit; gap_vo_gates
- Fix-cluster: `vo-seat-authority`
- Status: OPEN_RISK

### MTL-MUSICGEN-01 — music_palette_compose / MusicGen

- Surface: local-ML
- Modes: all (music epoch)
- Call graph: music_palette_compose → MusicGen assets; music_epoch_complete gates mix
- Why weak: stub WAVs; orphan replan; expensive lease; epoch seal break
- Likelihood: L2 | Severity: S4
- Evidence: music epoch guards; sdp_cross_validate
- Fix-cluster: `music-epoch`
- Status: LIKELY_MITIGATED_ON_HEAD (guards) / residual OPEN on stub paths

### MTL-MMAUDIO-01 — mmaudio_sfx + QA

- Surface: local-ML
- Modes: all
- Call graph: mmaudio_sfx → mmaudio_qa; `ensure_mmaudio_qa_before_mix`; incompleteness in stage_completion
- Why weak: hollow QA marked done; missing referenced WAVs; unreferenced lazy slots
- Likelihood: L2 | Severity: S3
- Evidence: `stage_completion` mmaudio; `delivery_recovery.ensure_mmaudio_qa_before_mix`
- Fix-cluster: `music-epoch`
- Status: LIKELY_MITIGATED_ON_HEAD

### MTL-DFN-01 — DeepFilterNet preclean

- Surface: local-ML
- Modes: Manual/Full-auto early; Partial deferred
- Call graph: audio_preclean → DeepFilterNet venv
- Why weak: never auto without offer; Partial checksum shift after G0; venv fail
- Likelihood: L2 | Severity: S2
- Evidence: audio_preclean; PARTIAL_AUTO_PREPARE_UNTIL_G0
- Fix-cluster: `partial-prepare-order`
- Status: OPEN_RISK

### MTL-FFMPEG-01 — mix / loudnorm / encode

- Surface: local-ML / ffmpeg
- Modes: all
- Call graph: mix → assembly.wav; master_finalize loudnorm; podcast_encode_mp3
- Why weak: binary read-as-JSON acceptance bugs; pending master; LUFS fail → remutate
- Likelihood: L2 | Severity: S3
- Evidence: stage_acceptance; master_finalize; post_master_quality
- Fix-cluster: `pending-flush-honesty`
- Status: OPEN_RISK
