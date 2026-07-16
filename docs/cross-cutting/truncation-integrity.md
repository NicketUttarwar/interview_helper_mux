# Truncation integrity (universal LLM contract)

No LLM call may **silently** proceed on truncated input. Truncation is detected via canonical markers in volley text:

| Marker | Flag |
|--------|------|
| `…[stage data truncated]` | `max_stage_data_chars` |
| `…[digest truncated]` | `framer_digest_truncated` |
| `…[truncated]` | `field_truncated` |
| `…[volley_middle_truncated]` | `volley_middle_truncated` |

## Gateways (only allowed LLM entry points)

| Gateway | Module |
|---------|--------|
| OpenAI | `stages/llm_runner.run_prompt_envelope` |
| Local MLX | `local_llm_runner.generate_local_chat` |

Every call records `_llm_meta.truncation_escalation`:

```json
{ "rounds": 1, "steps": ["tier_bump"], "final_flags": ["framer_digest_truncated"], "provider": "openai" }
```

## Escalation ladder

**Local MLX:** detect → skip infer when truncated → return `{escalate: true, volley_turns: []}` for framer tasks → OpenAI primary always runs for P0–P2.

**OpenAI gateway:** detect truncation markers in volley → log `truncation.input_truncated` → **do not call** primary/shard with truncated messages when `never_accept_truncated_output` → raise `TruncationEscalationRequired` (primary) or return blocked envelope with `needs[].type: decompose`.

**Routing (`run_llm_stage_with_routing`) — holistic rebuild before hard-block:**

1. Scan prepared volley for truncation flags.
2. **Cap-boost rebuild** (`rebuild_volley_clearing_truncation`): re-run `prepare_volley_for_llm` under `context_cap_boost` with progressive multipliers from `context_cap_boost_steps` (default `[1, 2, 4, 8, 16]`). Field clips also raise to `field_truncation_clear_floor_chars` (default 8000) so `…[truncated]` markers can clear.
3. If the rebuilt volley is clean → proceed with primary (no decompose needed).
4. If still truncated and the stage is decompose-eligible → **auto shard/collate** with the same boosted caps; shard failures that are truncation-blocked trigger another full-shard rebuild at the next boost round.
5. Only after boost rounds are exhausted (and decompose is impossible / still fails) → hard-block for operator recovery.

High-severity stages without a viable clean volley or shard plan still hard-block (no silent truncated primary).

Never accept `status: complete` when `final_flags` is non-empty on a persisted critical artifact.

## Critical stages vs write approval

Critical LLM stages (`block_partial_on_quality_fail`) do **not** stage write-approvable partials after lint/schema/truncation/accept failure — only `understanding/stage_runs/<stage>/attempt_*_resilience.json` audit sidecars. Write approval is skipped when the stage is incomplete or a quality gate is open.

## Config

`analysis.truncation_integrity` in `config/app.defaults.json`:

- `enforce_at_gateways`, `never_accept_truncated_output`, `never_inject_framer_when_truncated`
- `raise_escalation_required` — primary gateway raises `TruncationEscalationRequired` (caught → decompose need)
- `framer_digest_limits` (per-stage, e.g. `speaker_roles` / `content_context`: 24000)
- `context_cap_boost_steps` — multipliers for rebuild rounds (default `[1, 2, 4, 8, 16]`)
- `field_truncation_clear_floor_chars` — minimum clip floor during clear-field rebuild (default `8000`)
- `openai_tier_ladder`, `max_escalation_rounds_per_call`

## Operator-visible action IDs

- `truncation.input_truncated` — scan found markers before call
- `truncation.blocked` — gateway blocked call (truncated primary/shard)
- `truncation.cap_boost_rebuild` — rebuild attempted under higher context caps
- `truncation.cap_boost_cleared` — rebuild produced a clean (non-truncated) volley
- `truncation.shard_cap_boost_retry` — all shards re-run after truncation-blocked failures
- `truncation.auto_decompose` — routing auto-escalated to shard/collate (after boost)
- `truncation.escalation_required` — `TruncationEscalationRequired` caught in primary path
- `llm.flagship_promote` — uptier exhausted at flagship but lint/schema clean
- `llm.resilience.partial_blocked` — critical stage skipped write-approvable partial persist
