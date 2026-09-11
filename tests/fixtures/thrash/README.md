# Thrash mini-fixtures (Wave 10)

Frozen scenarios for heal/resume selection without LLM:

| Fixture | Assert |
|---------|--------|
| `pending_master/` | pending finalize WAV must not unlock ship; `committed_master_wav` false |
| `synth_g1/` | synth-only G1 → resume `vo_synthesize` |
| `stale_autopsy/` | size-mismatched commitment → `ship_path_ready` false |
| `remutate_protect/` | leftover edl + active remutate → not orphan-promoted |

Loaded by `tests/test_major_thrash_fixtures.py`.
