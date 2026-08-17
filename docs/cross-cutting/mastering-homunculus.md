# Mastering homunculus — versioned brains

The operator picks a **brain** on the Start tab. The choice is stored on `run_meta.homunculus_version` and **never changes mid-run**.

| Version | Kind | What runs |
|---------|------|-----------|
| **0.0.0** | `original_pipeline` | Linear 65-stage walk (`ANALYSIS_ORDER` + `DELIVERY_ORDER`). Existing gates, per-stage LLMs, remutate, recovery. No conductor. |
| **0.1.0** (default — latest) | `homunculus` | First mastering homunculus: in-process OpenAI tool loop, admit/pack, persona, issue bus, Shape organ, ears, retrieve+cite docs. Same host callables; authority is the conductor. |

Later minors (`0.2.0`, …) are extra slider stops. **New runs default to the highest registered brain** (`latest` in config; currently **0.1.0**). Unknown versions refuse to start (HTTP 400). CLI: `MUX_HOMUNCULUS_VERSION`.

**0.0.0 is not deprecated.** It remains on the Start slider as the original iterative walk.

## 0.1.0 law (code + prompts)

- Every catch is an Issue; analysis of a problem signature is **once**.
- Every output is **admitted** (keep / reformat / drop). Persist only after keep/reformat.
- Next LLM packet: conductor picks **fact IDs**; **host code renders** user/assistant turns.
- Closed G0 transcript + operator must-keep IDs are always packable (**bootstrap**).
- Missing required facts → **starvation** halt.
- Tape-only denylist remains hard (`exists` / `stage_done` / `run_meta`).
- Hard limits (cannot waive): max **3** invokes per identity; one analysis per issue; max 3 masters; max 3 mixes; conductor turns `3 × 65`; same ear window ≤ 3; no nested conductor; audio-mutating tools serialized.
- Halt writes `mastering/homunculus/limit_exhausted.json`. Ship stays blocked.

## Not tools

Terraform, AWS CLI, `bootstrap_venv`, pytest, `build_gui`, codegen/audit scripts.

## Artifacts

Under `mastering/homunculus/`: `persona.json`, `speaker_dossier.json`, `memory.json`, `admitted.jsonl`, `volley_packs/`, `issues.jsonl`, `analyses/`, `ledger.json`, `agenda.json`, `gate_decisions.json`, `prompt_stack.json`, `promotions.json`, `mints/`, `end_judgment.json`, `ears/`, `docs_cited.jsonl`, `limit_exhausted.json`.

Registry: [versions.yaml](../homunculus/versions.yaml). Prompts: [docs/prompts/homunculus/](../prompts/homunculus/).
