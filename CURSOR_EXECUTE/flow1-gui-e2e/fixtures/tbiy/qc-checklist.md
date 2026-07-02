# TBIY topology listen QC checklist

Manual listen pass after a full Flow 1 master export. Pair fixtures under `tests/fixtures/tbiy/<profile>/`.

## Profiles

| Profile | Expected dynamics | Segmentation | SFX density |
|---------|-------------------|--------------|-------------|
| `one_on_one_asymmetric` | Guest-heavy story; interviewer pickup bridges | Standard | Moderate punctuators |
| `one_on_one_balanced` | Dual-voice banter; balanced reactor moments | Standard | Moderate punctuators |
| `multi_idea_sparse_host` | Many idea threads; sparse host interjections | Fine + resegment | Higher punctuator cap |
| `monologue_heavy` | Single dominant voice; soft five-act hints | Coarse | Beds > punctuators |

## Operator journey (all profiles)

1. Confirm topology on Story Board (`FlowAdaptationCard`)
2. Lock story — `production_style: tbiy_narrative` + strategic moat
3. G1 pickup — least-spoken speaker only
4. Assembly preview listen
5. G1.5 post-preview re-record
6. SFX generate → mix → master listen

## Listen criteria

- [ ] Five-act arc readable (acts 1–5 bands visible on timeline when narrative plan present)
- [ ] Strategic moat chapter identifiable in Act IV band (when flagged `is_moat_chapter`)
- [ ] Pause-triggered punctuators land on breath gaps, not mid-word
- [ ] Pickup voice matches `pickup_eligible_speaker_id` from fixture
- [ ] No pre-preview VO satisfies G1.5 (post-preview metadata required)
- [ ] Speech remains intelligible — beds duck under dialogue

## Automated smoke

```bash
.venv/bin/python -m pytest tests/test_tbiy_topology_fixtures.py tests/test_tbiy_operator_journey.py -q
./CURSOR_EXECUTE/flow1-gui-e2e/run.sh --dry-run --config driver/config.tbiy.yaml
```
