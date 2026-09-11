# LLM volley packet contract

Every OpenAI / local-framer **user packet** must be **this run’s source-audio meaning**, not pipeline metadata.

See [NORTH_STAR.md](../../NORTH_STAR.md) and [volley-glossary.md](./volley-glossary.md).

## Allowed

- Transcript / segment text from this tape
- Speaker roles, claims, timestamps, gap severity
- Must-keep IDs as **editorial constraints**
- Compact spine windows with real words (`attach_spine_to_payload`)
- STT island excerpts and vernacular must-keep text (`attach_disfluency_context`)

## Forbidden (stripped by `volley_packet_lint`)

- `exists`, `path_ok`, `stage_done`, `artifact_exists`, `file_exists`, `exists_on_disk`
- Fingerprint hashes, raw `run_meta` dumps
- `e2e_soft` / `e2e_heal` notices, overlay path lists

**Conductor dual view (SYN-PACK-01):** `pack_conductor_context_views` keeps
`host_prereq_view` (stamps OK for seed/legal_next) separate from
`llm_conductor_view` (ready_bool / content hashes / tape summaries only). The
conductor LLM receives only the LLM view.

Enforcement: `lint_llm_user_payload` in `llm_simple.run_llm_stage_simple`. New stages go through `attach_conversation_context` + `attach_spine_to_payload` (or an explicit exemption).

**0.1.0 packer:** `attach_conversation_context` is a no-op. Nested stage LLMs go through `nested_chat_create`, which **replaces user turns** with a host-rendered pack. The conductor (or `axis_select`) chooses fact IDs; bootstrap always includes closed G0, must-keep IDs, `source_card`, and recent KB lessons. Missing required facts → starvation halt. **0.0.0** still uses `attach_conversation_context`.

Resume vs invalidate: `run_analysis(..., invalidate=False)` skips `.stage_done` without archiving. Only pass `invalidate=True` when the operator explicitly restarts a span.

**Three budgets (do not conflate):** LLM volley attempts (`v2.llm_max_attempts`, default 2) ≠ junction remaster rounds ≠ listen-delight remutate family (`MAX_ATTEMPTS` in `listen_delight_remutate.py`).
