# Operator gates — v2 simplified

Canonical charter: [NORTH_STAR.md](../../NORTH_STAR.md).

## Hard gates

| Gate | ID | Behavior |
|------|-----|----------|
| **G0** | `transcript_review` | **Mandatory.** Pipeline stops after `transcript_review_build` until STT corrections are complete. |
| **G1** | `g1_vo_pickup` | **Optional.** Operator may record `delivery: record` lines or click **Skip — continue without gap VO** (`POST …/g1/skip-optional`). |

## Non-gates (optional offers)

| Offer | When | Behavior |
|-------|------|----------|
| Pre-clean source | Before ingest | Never auto-run; dismissible |
| NLE edits | After ranking / before EDL | Operator choice via Timeline tab |
| Assembly preview listen | After `assembly_preview` | Soft milestone; does not block mix by default |

## Removed gates (v2)

- G0.5 `disfluency_review`
- `analysis_profile` / `operator_verified`
- G2 flow selection
- G1.5 SFX prompt approval (default off: `g1_5_require_prompt_approval: false`)
- Per-stage write approval (auto-commit artifacts)
- Custom-run handoff acks

## LLM failures

v2 uses **schema validate → one retry → hard stop** (`llm_simple.py`). No volley, arbiter, or investigation queue. Re-run with `--from-stage <id>` after fixing upstream artifacts.

See [docs/v2/drop-manifest.md](../v2/drop-manifest.md).
