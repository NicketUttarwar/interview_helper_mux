# Step 04 — FINISH verify

**When:** `flow_1_master/master.wav` exists under the active `run_id`.

---

## Automated checks

```bash
RUN_ID="<from driver/state.json>"
python tools/verify_master.py "ASSETS/executions/${RUN_ID}/flow_1_master/master.wav"
python tools/validate_narrative.py --run-id "${RUN_ID}" --include-edl
```

## Artifact checklist

- [ ] `ingest/normalized.wav`
- [ ] `transcript/full.json`
- [ ] `understanding/content_brief.json` (complete)
- [ ] `segments/manifest.json`
- [ ] `flow_1_master/edl.json`
- [ ] `flow_1_master/assembly_preview.wav`
- [ ] `sound_design/assets/*.wav` (≥1)
- [ ] `flow_1_master/master.wav`

## Manual follow-up

Brief listen per [definition-of-done-signoff.md](../../docs/build-out/definition-of-done-signoff.md).

## Index update

Mark `00-INDEX.md` success criteria `[x]` and step **04** complete.
