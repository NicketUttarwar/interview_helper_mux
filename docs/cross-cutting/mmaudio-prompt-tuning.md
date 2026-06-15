# MMAudio prompt tuning

Local **MMAudio `large_44k_v2`** text-to-audio for podcast SFX. Generation runs in `ASSETS/local_mmaudio/venv` via `tools/mmaudio_generate.py`.

## Positive vs negative

| Field | Passed to MMAudio as | Content |
|-------|----------------------|---------|
| `sfx_prompt` | `prompt` | Acoustic scene, texture, temporal arc, mix role |
| `negative_prompt` | `negative_prompt` | Vocal/speech bans + role-specific bans |

Do **not** append `Avoid: …` into the positive prompt — the runner passes negatives natively.

## CFG strength vs `prompt_influence`

`prompt_influence` (0–1) maps to CFG adherence in `mmaudio_runner.resolve_cfg_strength`:

| `prompt_influence` | Effect |
|--------------------|--------|
| ≤ 0.25 | Role base CFG − 0.6 (looser) |
| 0.26–0.39 | Role base CFG |
| ≥ 0.40 | Role base CFG + 0.5 (stricter) |

Explicit `cfg_strength` on the craft row overrides mapping (2.0–8.0).

Default role bases (`config/app.defaults.json`):

| Role | CFG |
|------|-----|
| `ambient_bed` | 3.8 |
| `chapter_stinger` | 4.8 |
| `transition_stinger` | 4.6 |
| `cold_open` | 5.0 |
| `vo_bridge` | 4.2 |
| `accent_foley` | 4.5 |

## Failure modes

| Symptom | Try |
|---------|-----|
| Vocals / speech leak | Strengthen `negative_prompt`; lower CFG slightly |
| Too cinematic / detailed | Lower CFG; simplify positive scene |
| Muddy bed | Fewer layers in positive; lower CFG |
| Duration too long | Mix trim; QA suggests `suggested_trim_ms` |
| Loop click on bed | Simplify texture; note loop seam in craft |

## Operator loop

1. Craft / approve prompts (G1.5)
2. `mmaudio_sfx_flow*` generates WAVs
3. `sound_design/mmaudio_qa.json` deterministic checks (Tier 0 signal + Tier 1 theme fit + optional Tier 2 CLAP when `mmaudio.semantic_qa_enabled`)
4. Post-listen pass/fail in GUI
5. Optional **Auto-refine** or manual edit → **Regenerate** subset

## Hardware

- Prefer CUDA or Apple MPS; CPU is supported but slow
- `num_steps` default 25; reduce for faster iteration (10–15)
- Duration clamp 3.0–8.0 s per `mmaudio.min_duration_sec` / `max_duration_sec`

## Regression

See `docs/prompts/_shared/examples/sfx-prompt-regression.md`. Log tokens: `mmaudio_regression_pass` / `mmaudio_regression_fail`.
