---
id: execution-step-6-plus
tier: both
status: spec
depends_on: [execution-readme]
---

# Step 6+ — Production execution (future)

Run only after [SETUP.md](../../SETUP.md) Steps 1–5 pass.

| Step | Intent | Not yet automated |
|------|--------|-------------------|
| **6** | Real interview E2E (30–90 min) | `medium`/`small` Whisper, LLM rank, listen to master |
| **7** | Human QA | Review manifest; ban segments; re-mux |
| **8** | Delivery export | True-peak limiter; MP3/M4A; chapters (preset B) |
| **9** | Preset E production | De-reverb, room-tone bridges; A/B before `--approve-dsp` |
| **10** | Presets B–D | Chapter metadata, budget solver, graph mux CLIs |
| **11** | CI regression | Golden LUFS/duration bounds on fixture |
