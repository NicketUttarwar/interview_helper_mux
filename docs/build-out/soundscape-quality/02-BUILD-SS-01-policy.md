# 02 — BUILD-SS-01 policy produce + resolve

Implement `soundscape_policy_build` after `delivery_brief_build`; `soundscape_policy.py` with `build_policy`, `load_policy`, `resolve_mix_contract`; wire pipeline + consumers.

## Verify

```bash
pytest tests/ -k "soundscape_policy or acoustic_profile" -q
./scripts/verify_artifact_contract.sh
```
