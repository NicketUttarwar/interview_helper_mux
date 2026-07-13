# 07 — FINISH BUILD-SS-06 signoff

Run full audit block; clear repository-map gap; scorecard + DoD.

## Verify

```bash
./tools/check_prerequisites.sh
pytest tests/ -k "soundscape or sound_design or placement or acoustic or sonic" -q
./scripts/verify_artifact_contract.sh
python tools/audit_config_keys.py
python tools/audit_operator_action_catalog.py
python tools/audit_stage_reuse_matrix.py
python tools/ui_truth_smoke.py
```
