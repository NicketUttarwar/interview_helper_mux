# Operator journey — v2 simplified

See [NORTH_STAR.md](../../NORTH_STAR.md) for the single product goal: **`master/master.wav`**.

## Ten phases

| # | Phase | Operator action |
|---|-------|-----------------|
| 1 | Start | Select audio; optional preclean offer (accept/dismiss) |
| 2 | Prepare | Automated: preclean → ingest → transcribe → review queue |
| 3 | Fix transcript | **G0 mandatory** — correct STT in transcript review |
| 4 | Understand | Automated analysis batch through `episode_structure_compose` |
| 5 | Fill gaps | **Optional G1** — record pickup VO or **Skip — continue without gap VO** |
| 6 | Plan & rank | Coverage audit → narrative plan → ranking → transitions |
| 7 | Edit | Optional NLE trims (Timeline sub-tab) |
| 8 | Sound | SDP plan → VO finalize → SFX prompt craft |
| 9 | Build | EDL → preview → MMAudio → mix |
| 10 | Ship | `master_finalize` → download `master.wav` |

## Removed from v2

Deleted from the codebase — not disabled, not behind a flag. Full list: [docs/v2/drop-manifest.md](../v2/drop-manifest.md).

- G0.5 disfluency review, analysis profile gate, G2 flow picker (Flow 2 / Flow 3)
- Autopilot / Decision Wizard, per-stage write approval, handoffs
- Story / Debug / Volley / Profile / Files pipeline sub-tabs (Stage + Timeline only)
- AWS Transcribe — STT is local MLX only

## CLI path

```bash
python tools/run_analysis.py --run-id <exec_id>
python tools/run_delivery.py --run-id <exec_id>
python tools/verify_master.py ASSETS/executions/<exec_id>/master/master.wav
```

Legacy multi-flow docs: [docs/archive/pre-v2/README.md](../archive/pre-v2/README.md).
