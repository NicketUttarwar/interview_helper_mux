# Prompt heritage notes

- Canonical LLM system prompts are `*.system.txt` (no dual path).
- `*.tbiy.system.txt` files are **heritage-only** and unused by `prompt_variant()` (always returns the base path).
- Narrative mode / montage grammar condition stages via `mastering_plan` fields in the volley payload, not alternate prompt files.
