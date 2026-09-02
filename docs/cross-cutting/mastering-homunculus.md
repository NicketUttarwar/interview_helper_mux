# Mastering homunculus — versioned brains

The operator picks a **brain** on the Start tab. The choice is stored on `run_meta.homunculus_version` and **never changes mid-run**.

| Version | Kind | What runs |
|---------|------|-----------|
| **0.0.0** | `original_pipeline` | Linear 66-stage walk (`ANALYSIS_ORDER` + `DELIVERY_ORDER`). Existing gates, per-stage LLMs, remutate, recovery. No conductor. |
| **0.1.0** (default — latest) | `homunculus` | Authoritative conductor: skip / reorder / surgical re-run, dynamic fact packing, per-run knowledge base, host MusicGen ladder, source-relative ears. Same host callables; leftover seed walk only if the conductor asks. |

Later minors (`0.2.0`, …) are extra slider stops. **New runs default to the highest registered brain** (`latest` in config; currently **0.1.0**). Unknown versions refuse to start (HTTP 400). CLI: `MUX_HOMUNCULUS_VERSION`.

**0.0.0 is not deprecated.** It remains on the Start slider as the original iterative walk.

## 0.1.0 law (code + prompts)

- The conductor is the top brain: it **may skip, reorder, and surgically re-run** a done stage with extra facts or mutated inputs when it expects a significantly better outcome. Leftover seed-order walk is **not automatic** (`walk_seed_remainder` only).
- Nested LLM packets are **packed facts only**. Host code renders turns. `attach_conversation_context` stays a no-op on 0.1.0.
- Always packable bootstrap: closed G0 transcript, operator must-keep IDs, `source_card`, recent KB lessons for this identity. Axis choice is dynamic (`axis_select` or heuristic). Missing required facts → **starvation** halt.
- Every output is **admitted** (keep / reformat / drop). Persist only after keep/reformat.
- Every catch is an Issue. Analysis is **once per `(kind, implicated, speaker_id)`** — another speaker or a new style tag may analyze again. Style tags persist in the KB.
- Per-run knowledge base (`kb.json` + `thinking.jsonl`) is written and packed on later calls. Reject lessons must appear on the next mix/master pack.
- Tape-only denylist remains hard (`exists` / `stage_done` / `run_meta`).
- Hard limits (cannot waive): max **3** invokes per identity (reruns count); max 3 masters; max 3 mixes; conductor turns `3 × 66`; same ear window ≤ 3; no nested conductor; audio-mutating tools serialized. Mandatory media-IP CTA cover regenerate (text+voice after a CTA hole) does **not** increment that cap.
- Creative beds: prefer **MusicGen large**; host ladder `large → medium → small → MMAudio` backup. Do not pick MMAudio first for theme/underscore.
- `low_conf_island_scan` / `connector_fuse_pass` may not be skipped unless their artifacts already exist. Least-spoken host clone policy is unchanged. G0 still blocks meaning-bearing analysis.
- Media-IP CTA omit is flagship-on-the-fly (ranking / compose packets). Host executes drops, recuts, never-touch QC. Logs only — no extra GUI gate. 0.0.0 unchanged.
- Halt writes `mastering/homunculus/limit_exhausted.json`. Ship stays blocked.

## Unattended recovery (partial-auto + full-auto)

Homunculus **0.1.0** owns delivery failure recovery for unattended runs. `needs_operator` is stamped only for operator journey gates (G0 transcript, voice reference, **G-DeliveryUnlock**, G-Publish) — not for VO coverage, stale upstream, or seed-order blocks. Classified playbooks in `recovery_controller.py` (`vo_seated_coverage`, `vo_contract_repair`, `upstream_stale_rerun`, …) run via `handle_stage_failure` with a tiered retry budget (3× transient, 1× structural). `MUX_FORENSICS` is a legacy driver shim; new runs rely on this policy instead.

## Not tools

Terraform, AWS CLI, `bootstrap_venv`, pytest, `build_gui`, codegen/audit scripts.

## Artifacts

Under `mastering/homunculus/`: `persona.json`, `speaker_dossier.json`, `source_card.json`, `memory.json`, `admitted.jsonl`, `volley_packs/`, `issues.jsonl`, `analyses/`, `ledger.json`, `agenda.json`, `kb.json`, `thinking.jsonl`, `reruns/`, `gate_decisions.json`, `prompt_stack.json`, `promotions.json`, `mints/`, `end_judgment.json`, `ears/`, `docs_cited.jsonl`, `limit_exhausted.json`. Host CTA execution: `mastering/media_ip_cta.json`.

Registry: [versions.yaml](../homunculus/versions.yaml). Prompts: [docs/prompts/homunculus/](../prompts/homunculus/).
