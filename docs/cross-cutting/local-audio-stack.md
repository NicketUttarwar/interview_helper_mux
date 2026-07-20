# Local audio stack (DeepFilterNet + MMAudio)

Interview MUX runs **noise reduction** and **SFX generation** locally via isolated venvs under `ASSETS/`. No ElevenLabs API keys or cloud audio spend.

**Planned:** speech-to-speech gap VO (synthesis, voice conversion, prosody/tone) — [speech-to-speech-vo.md](./speech-to-speech-vo.md) (R&D; not in bootstrap yet).

## Components

| Stack | Upstream | Purpose | Venv |
|-------|----------|---------|------|
| DeepFilterNet | [rikorose/deepfilternet](https://github.com/rikorose/deepfilternet) | Optional `audio_preclean` noise reduction | `ASSETS/local_deepfilter/venv` |
| MMAudio | [hkchengrex/MMAudio](https://github.com/hkchengrex/MMAudio) | `mmaudio_sfx` / `REMOVED_mmaudio_flow2` text-to-audio | `ASSETS/local_mmaudio/venv` |

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
| `sfx_prompt_craft` | `sound_design/sfx_prompts.json` (positive + negative + optional CFG) | `mmaudio_sfx_flow*` |
| `sfx_prompt_refine` | merged prompt rows for failed assets (optional) | regen via `mmaudio_sfx_flow*` |
| `mmaudio_sfx_flow*` | WAVs + `mmaudio_qa.json` | mix via `placement_adjustments` |

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

See also [SETUP.md](../SETUP.md) § Local audio stack.
