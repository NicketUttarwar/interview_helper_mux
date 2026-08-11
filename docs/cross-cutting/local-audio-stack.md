# Local audio stack (DeepFilterNet + MusicGen + MMAudio)

Interview MUX runs **noise reduction** and **theme music generation** locally via isolated venvs under `ASSETS/`. No ElevenLabs API keys or cloud audio spend. STT and diarization are likewise local (MLX, `ASSETS/local_speech/venv`) — AWS Transcribe was removed.

| Tool | Upstream | Stage use | Venv |
|------|----------|-----------|------|
| DeepFilterNet | DeepFilterNet | preclean | `ASSETS/local_deepfilter/venv` |
| **MusicGen** | facebook/musicgen-large (+ melody-large) | creative-delivery `theme_*` stems | `ASSETS/local_musicgen/venv` (`./scripts/bootstrap_musicgen.sh`) |
| MMAudio | [hkchengrex/MMAudio](https://github.com/hkchengrex/MMAudio) | legacy / non-creative SFX only (disabled for show path when MusicGen enabled) | `ASSETS/local_mmaudio/venv` |

**Music-only rule:** creative delivery never ships whoosh/tick/foley/murmur. Theme stems share a motif family (`understanding/music_brief.json` + SDP `motif_family`). QA failure → regen → fallback to a passed stem in the same family → else fail-closed.

**MusicGen resources:** Default device is **CPU**. PyTorch **MPS** (`device: mps`) can `abort()` inside Metal (`MTLReportFailure` / `Python quit unexpectedly`). After a SIGABRT the runner bans MPS for the rest of the run and retries once on CPU. Generation is serialized (`ASSETS/local_musicgen/generate.lock`) and launched via the framework CLI `python3.12`, not `Python.app`. Per-clip timeout is **1 hour**, then a cheaper ladder (short bare prompt on CPU, then a cached medium/small model if present), then a deterministic musical-note stub so mix always has audio. `fail_closed_on_stub` defaults **false** so that last-resort stub is accepted.

**Local runtime JSON:** scripts emit one JSON object on stdout `{ok, error?, out_wav?, warnings?}`. Progress stays on stderr. `run_runtime_json` parses stdout then stderr, logs `gui_log` + `vo_pickup/local_runtime_last_error.json` with `likely_cause`. G1 synthesize-all collects per-line errors instead of aborting the batch.

**Planned:** deeper ML speech-to-speech voice conversion — [speech-to-speech-vo.md](./speech-to-speech-vo.md). DSP timbre match for operator gap VO is shipped.

## Components

| Stack | Upstream | Purpose | Venv |
|-------|----------|---------|------|
| DeepFilterNet | [rikorose/deepfilternet](https://github.com/rikorose/deepfilternet) | Optional `audio_preclean` noise reduction | `ASSETS/local_deepfilter/venv` |
| MMAudio | [hkchengrex/MMAudio](https://github.com/hkchengrex/MMAudio) | `mmaudio_sfx` text-to-audio | `ASSETS/local_mmaudio/venv` |

Weights for MMAudio are downloaded by the upstream package on first generation (HF; CC-BY-NC 4.0).

## Bootstrap (single entry)

```bash
./scripts/bootstrap_venv.sh
./scripts/verify_local_models.sh
```

This creates the core `.venv`, clones both upstream repos, builds isolated venvs, and runs verify gates.

**Requires Rust** (`rustc`) for DeepFilterNet's native `pyDF` build. Without Rust, MMAudio still bootstraps; preclean falls back until Rust is installed and bootstrap re-run.

Manual steps:

```bash
./scripts/clone_local_audio_repos.sh
bash scripts/lib/bootstrap_local_runtimes.sh
./scripts/verify_local_models.sh
```

## Verify

```bash
ASSETS/local_deepfilter/venv/bin/python scripts/download_deepfilter.py --verify
ASSETS/local_mmaudio/venv/bin/python scripts/download_mmaudio.py --verify
```

Each stack writes `ASSETS/local_*/install.json` with repo commit, venv path, and `verified_at`.

## Runtime tools

| Script | Invoked by |
|--------|------------|
| `tools/deepfilter_enhance.py` | `deepfilter_runner.enhance_wav` |
| `tools/mmaudio_generate.py` | `mmaudio_runner.generate_text_to_audio` |

## Existing runs (migration)

Runs that completed under old stage ids (`mmaudio_sfx_flow*`) are **not** auto-migrated. Re-run from `sfx_prompt_craft` after approving `sound_design/sfx_prompts.json`.

## Prompt architecture (MMAudio SFX)

| Stage | Output | Consumed by |
|-------|--------|-------------|
| `sound_design_palettes` | coherence, palettes | plan stages |
| `sound_design_plan/2` | `assets[]`, cues, optional `generation_notes` | `sfx_prompt_craft` |
| `sfx_prompt_craft` | `sound_design/sfx_prompts.json` (positive + negative + optional CFG) | `mmaudio_sfx` |
| `sfx_prompt_refine` | merged prompt rows for failed assets (optional) | regen via `mmaudio_sfx` |
| `mmaudio_sfx` | WAVs + `mmaudio_qa.json` | mix via `placement_adjustments` |

Tuning: [mmaudio-prompt-tuning.md](./mmaudio-prompt-tuning.md) · Regression: [sfx-prompt-regression.md](../prompts/_shared/examples/sfx-prompt-regression.md).

### Tier-2 semantic QA (CLAP)

When `mmaudio.semantic_qa_enabled` is `true` (shipped default), `mmaudio_qa` invokes `tools/clap_similarity.py` inside the MMAudio venv (`transformers` + `librosa` from `requirements-local-mmaudio.txt`). First run downloads `laion/clap-htsat-fused` from Hugging Face. Fail-open: missing deps or timeouts set `semantic_qa_verdict=skipped` without blocking generation. Set `semantic_qa_enabled: false` to skip Tier-2 entirely.

| Config key | Default | Role |
|------------|---------|------|
| `semantic_qa_threshold` | `0.18` | Cosine similarity pass floor |
| `semantic_qa_fail_on_low` | `false` | When true, sub-threshold scores fail QA |
| `semantic_qa_timeout_sec` | `120` | Per-asset subprocess timeout |

Re-run `./scripts/bootstrap_venv.sh` (or pip install the MMAudio requirements file) after pulling CLAP deps.

## Troubleshooting

| Issue | Action |
|-------|--------|
| `Missing venv python` | Re-run `./scripts/bootstrap_venv.sh` |
| DeepFilter `maturin` failure | Install Rust toolchain; ensure repo cloned |
| `pip install -e` flat-layout error on repo root | Bootstrap installs `DeepFilterNet/DeepFilterNet` subpackage, not repo root — re-run `./scripts/bootstrap_venv.sh` |
| `torchaudio.backend` import error | Mismatched torch/torchaudio — bootstrap pins `2.5.1` for deepfilter venv |
| MMAudio demo fails | Confirm `ASSETS/local_mmaudio/MMAudio/demo.py` exists after clone |
| Preclean falls back to `ffmpeg_local` | DeepFilter stack unavailable; check `preclean/provider.json` |

See also [SETUP.md](../../SETUP.md) § Local audio stack.
