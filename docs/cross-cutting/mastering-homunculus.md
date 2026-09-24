# Mastering homunculus — versioned brains

The operator picks a **brain** on the Start tab. The choice is stored on `run_meta.homunculus_version` and **never changes mid-run**.

| Version | Kind | What runs |
|---------|------|-----------|
| **0.0.0** | `original_pipeline` | Linear stage walk (`ANALYSIS_ORDER` + `DELIVERY_ORDER`). Existing gates, per-stage LLMs, remutate, recovery. |
| **0.2.0** (default — latest) | `homunculus` | Fixed **seed walk** with ledger, admit, dispatch budgets, packing, MusicGen ladder, source-relative ears. Same host callables. Stages may re-run when artifacts are hollow/stale (heal); order does not rearrange. |

**New runs default to the highest registered brain** (`latest` in config; currently **0.2.0**). Unknown versions refuse to start (HTTP 400). CLI: `MUX_HOMUNCULUS_VERSION`. Pin `0.0.0` for the original walk.

**0.0.0 is not deprecated.** It remains on the Start slider as the original iterative walk. Legacy id `0.1.0` may appear on ancient `run_meta` for resume only — it is not offered on Start.

> **HISTORY:** Earlier builds offered an LLM conductor (0.1.0) and an experimental solver authority flag that could reorder stages; both were removed in favor of a fixed seed walk.

## 0.2.0 law (code + prompts)

- Stage order is the **seed walk** (`ANALYSIS_ORDER` → `DELIVERY_ORDER` → ship). Leftover seed-order walk is the control plane (`walk_seed_remainder` / `_walk_sequence`).
- Nested LLM packets are **packed facts only**. Host code renders turns. `attach_conversation_context` stays a no-op on homunculus brains.
- Always packable bootstrap: closed G0 transcript, operator must-keep IDs, `source_card`, recent KB lessons for this identity. Axis choice is dynamic (`axis_select` or heuristic). Missing required facts → **starvation** halt.
- Every output is **admitted** (keep / reformat / drop). Persist only after keep/reformat.
- Every catch is an Issue. Analysis is **once per `(kind, implicated, speaker_id)`** — another speaker or a new style tag may analyze again. Style tags persist in the KB.
- Per-run knowledge base (`kb.json` + `thinking.jsonl`) is written and packed on later calls. Reject lessons must appear on the next mix/master pack.
- Tape-only denylist remains hard (`exists` / `stage_done` / `run_meta`).
- **Stage-completion honesty:** refuse `.stage_done` when `stage_artifact_incompleteness` is non-empty (`vo_synthesize` G1 parity, `mmaudio_sfx` referenced SDP WAVs, etc.). Heal resume pins come from [`heal_routing.resume_stage_for_error_class`](../../src/interview_mux/heal_routing.py) — never brain-specific forks for `incomplete_cut` / `mmaudio_incomplete` / `g1_vo_incomplete`.
- Hard limits (cannot waive): max **3** invokes per identity (reruns count); max 3 masters; max 3 mixes; same ear window ≤ 3; audio-mutating tools serialized. Mandatory media-IP CTA cover regenerate (text+voice after a CTA hole) does **not** increment that cap.
- Creative beds: prefer **MusicGen large**; host ladder `large → medium → small → MMAudio` backup. Do not pick MMAudio first for theme/underscore.
- `low_conf_island_scan` / `connector_fuse_pass` may not be skipped unless their artifacts already exist. Least-spoken host clone policy is unchanged. G0 still blocks meaning-bearing analysis.
- Media-IP CTA omit is flagship-on-the-fly (ranking / compose packets). Host executes drops, recuts, never-touch QC. Logs only — no extra GUI gate. 0.0.0 unchanged.
- Halt writes `mastering/homunculus/limit_exhausted.json`. Ship stays blocked.
- Seed-order law (`_seed_prereq_block`) and hard contract honesty remain: hollow/incomplete predecessors block later stages until healed.

## Always-HAU seating (mix ↔ music)

Federal for Partial + Full-auto (**no** live music≺mix seating path):

1. Phase A / EDL holes first (skipped once Phase A is sealed).
2. If music epoch complete + speech-first stamp → remaster mix / junction (never speech-first again).
3. Else if `allow_speech_first_mix` → `mix` seats assembly.
4. Else earliest incomplete music producer (`music_palette_compose` → `sfx_prompt_craft` → `mmaudio_sfx`).
5. Else junction / finalize.

SSOT: `mix_junction_seat.next_delivery_seat`. Soft gates: `beds_deferred_for_mix`. Resume/heal/filter/driver must not choose mix vs MusicGen via raw `allow_speech_first_mix` outside the SSOT module. `mix_epoch_block` clears speech-first only via `clear_mix_epoch_for_speech_first` (FG2: bare call stays blocked). After music completes, `speech_first_remaster_owed` / `ensure_speech_first_remaster` keep junction/finalize on `speech_first_remaster_pending` until the bed remaster lands.

**Hard VO freeze (End-A late repairs):** named shrink/clamp/integrity only (`soundscape_bed_trim`, `opening_adjacency_*`, `sdp_theme_outro_rebind`, `sdp_duration_band_repair`) with verify-persist (SDP End-A must commit with the named reason — never bare `write_json`). Expand (`soundscape_bed_seed_repair`, outro create, `optimizer_promote_*`) → honest skip / refuse.

## Unattended recovery (partial-auto + full-auto)

Homunculus **0.2.0** owns delivery failure recovery for unattended runs. `needs_operator` is stamped only for operator journey gates (G0 transcript, voice reference, **G-DeliveryUnlock**, G-Publish) — not for VO coverage, stale upstream, or seed-order blocks. Classified playbooks in `recovery_controller.py` (`vo_seated_coverage`, `vo_contract_repair`, `upstream_stale_rerun`, …) run via `handle_stage_failure` with a tiered retry budget (3× transient, 1× structural). Forensics campaigns use `MUX_FORENSICS=1` with heal-and-continue on the same `run_id`.

**Execution contract ladder** (`execution_contract.py`): when `validate_vo_contract()` fails (orientation missing from `gap_report`, skip flags on seated lines, …), `run_vo_contract_ladder` runs tiers A→D (publish layup + orientation → gap recompose → opening omit → logged unseat/waive) and only reports `recovered` when validation passes. Artifacts: `operator/execution_contract.json`, `operator/vo_contract_repair_plan.json`. Universal classified dispatch lives in `remediation_framework.py`; proactive reconcile in `execution_invariants.py` at analysis→delivery handoff, delivery batch start, and consumer preflight.

## Not tools

Terraform, AWS CLI, `bootstrap_venv`, pytest, `build_gui`, codegen/audit scripts.

## Artifacts

Under `mastering/homunculus/`: `persona.json`, `speaker_dossier.json`, `source_card.json`, `memory.json`, `admitted.jsonl`, `volley_packs/`, `issues.jsonl`, `analyses/`, `ledger.json`, `agenda.json`, `kb.json`, `thinking.jsonl`, `reruns/`, `gate_decisions.json`, `prompt_stack.json`, `promotions.json`, `mints/`, `end_judgment.json`, `ears/`, `docs_cited.jsonl`, `limit_exhausted.json`. Host CTA execution: `mastering/media_ip_cta.json`.

Registry: [versions.yaml](../homunculus/versions.yaml). Prompts: [docs/prompts/homunculus/](../prompts/homunculus/).
