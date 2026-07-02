# TBIY Flow 1 E2E fixtures

Topology profiles for listen QC and automated journey checks. Pair with `config.tbiy.yaml`.

## Profiles

| File | Topology class | Use |
|------|----------------|-----|
| `one_on_one_asymmetric.yaml` | `one_on_one_asymmetric` | Reactor pickup on least-spoken interviewer |
| `one_on_one_balanced.yaml` | `one_on_one_balanced` | Balanced banter + punctuators |
| `multi_idea_sparse_host.yaml` | `multi_idea_sparse_host` | Fine segmentation + micro-idea units |
| `monologue_heavy.yaml` | `monologue_heavy` | Coarse acts; beds over punctuators |

## Run (GUI E2E)

```bash
# Default WAV; override production style via Story Board after analyze phase
PRODUCTION_STYLE=tbiy_narrative ./CURSOR_EXECUTE/flow1-gui-e2e/run.sh

# Or use TBIY driver config (same WAV, tbiy gate handlers enabled)
./CURSOR_EXECUTE/flow1-gui-e2e/run.sh --config driver/config.tbiy.yaml
```

## Operator journey checkpoints (TBIY-specific)

1. **Topology confirm** — Story Board → `FlowAdaptationCard` → Confirm topology
2. **Story lock** — Set `production_style: tbiy_narrative` + strategic moat → Lock story
3. **G1 pickup** — Record least-spoken speaker lines (`dummy_vo.wav` in E2E)
4. **Preview listen** — After `assembly_preview` → mark listened
5. **G1.5 re-record** — Post-preview reaction lines only (gate before `mmaudio_sfx_flow1`)
6. **SFX** — Approve prompts → generate → post-listen pass → mix

## API smoke (no GUI)

```bash
.venv/bin/python -m pytest tests/test_tbiy_operator_journey.py -v
```
