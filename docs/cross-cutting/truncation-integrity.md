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

**OpenAI:** detect → tier bump → routing decompose/shard → operator gate. Never accept `status: complete` when `final_flags` is non-empty.

## Config

`analysis.truncation_integrity` in `config/app.defaults.json`:

- `enforce_at_gateways`, `never_accept_truncated_output`, `never_inject_framer_when_truncated`
- `framer_digest_limits` (per-stage, e.g. `speaker_roles: 24000`)
- `openai_tier_ladder`, `max_escalation_rounds_per_call`

## Operator-visible action IDs

- `truncation.input_truncated` — scan found markers before call
- `truncation.blocked` — gateway blocked call after ladder exhaustion
- `llm.flagship_promote` — uptier exhausted at flagship but lint/schema clean
