# Reliability charter — voice + pipeline guardrails

Holistic reliability for gap framing, Chatterbox synthesis, and Flow 1 delivery. Operator gates remain the primary control surface; automation degrades gracefully rather than blocking `master/master.wav`.

## Voice degradation ladder

```mermaid
flowchart TD
    CB[Chatterbox zero-shot]
    MLX[mlx-audio S2S fallback]
    REC[Operator record/upload]
    SKIP[Skip line G1 optional]
    SRC[Source-only G-Framing No]
    CB -->|fail_open| MLX
    MLX -->|fail_open| REC
    REC -->|skip_optional| SKIP
    SKIP --> SRC
    CB -->|both fail| REC
```

When Chatterbox and mlx-audio both fail (or Chatterbox runtime is missing at G-Delivery), the run **automatically switches to manual record/upload** at G1. Operators see `run_meta.synthesis_fallback_notice`; the pipeline continues.

## QC tiers

| Tier | Mechanism | Default posture |
|------|-----------|-----------------|
| Schema | `prompt_validation` + JSON schemas | Blocking on write |
| Deterministic lint | `deterministic_lint` per stage | Warn (v2 simple path) |
| Framing guards | `framing_coverage_guard` after ranking | Strict on primary impact / topic survival |
| EDL narrative QC | `edl_narrative_qc` at `edl` | `strict: true` |
| Master verify | `verify_master` LUFS/TP | Release checklist |

## Config knob index

| Key block | Purpose |
|-----------|---------|
| `analysis.gap_framing.*` | Word caps, exclusion ratio, topic survival, framing-before-impact |
| `analysis.gap_vo.*` | Chatterbox default, fail-open, reference length, post-synthesis QC |
| `edl_narrative_qc.*` | Strict EDL checks, synthesized VO requirement, framing alignment |

See `docs/cross-cutting/config-keys.md` for full key list.

## v2 lint / crossval

`v2.lint_blocking` and `v2.cross_validate_blocking` remain **documentation-only** on the v2 simple path (defaults `false`). Tiered enforcement uses stage lint + EDL QC + operator gates instead.

## Release checklist

1. `./tools/check_prerequisites.sh` (includes Chatterbox WARN in `verify_local_models.sh`)
2. Gap path smoke: `docs/workflows/smoke-test.md`
3. `./scripts/verify_artifact_contract.sh`
4. Targeted pytest: gap framing, synthesis report, EDL QC, framing guard

Related: [chatterbox-interviewer-vo.md](chatterbox-interviewer-vo.md), [operator-gates.md](../workflows/operator-gates.md).
