# Homunculus prompts (brain 0.1.0)

Used only when the operator selects **0.1.0**. **0.0.0** keeps the existing per-stage tree under `docs/prompts/` (analysis, selection, sound_design, …).

| Path | Role |
|------|------|
| `conductor/system.txt` | OpenAI conductor: tool selection, admit/pack, gates, ears, judgment |
| `conductor/mlx.system.txt` | Shorter local-MLX conductor variant (same law, fewer tokens) |
| `perspectives/direct_listener_monetization.system.txt` | Omit subscribe/buy-now CTAs; keep interesting business-system talk |

**Stock process (tools):** `stack_prompt_module`, `mint_prompt`, `promote_prompt`. Promotion requires `corpus_ok` (eval corpus thresholds). Minted bodies land under `mastering/homunculus/mints/`; promotions under `mastering/homunculus/promotions.json`.

Do not treat Whisper / DeepFilterNet / MusicGen weights as system-prompt models. MusicGen/MMAudio **text** prompts are still produced by nested LLM tools.

Canon: [docs/cross-cutting/mastering-homunculus.md](../cross-cutting/mastering-homunculus.md).
