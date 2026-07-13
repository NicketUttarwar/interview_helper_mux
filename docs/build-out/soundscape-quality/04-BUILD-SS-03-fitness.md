# 04 — BUILD-SS-03 asset fitness loop

Execute placement `regenerate` / `skip_cue` in mmaudio + placement_qa (max 1 regen per asset).

## Verify

```bash
pytest tests/ -k "placement or mmaudio or soundscape" -q
```
