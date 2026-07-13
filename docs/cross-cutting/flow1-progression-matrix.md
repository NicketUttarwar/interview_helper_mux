# Flow 1 progression matrix

Stage → primary writes → hard gates → validation checkpoints. Canonical orders: `pipeline.py` (`ANALYSIS_ORDER`, `DELIVERY_ORDER`).

| Stage | Primary artifact(s) | Gates before run | Checkpoints after commit |
|-------|---------------------|------------------|--------------------------|
| `speaker_roles` | `understanding/speakers.json` | G0 | P0 spine |
| `content_context` | `understanding/content_brief.json` | P0 upstream | P0 spine |
| `boundary_detection` | `segments/boundaries.json` | P0 upstream | `post_segmentation` |
| `segment_classification` | `segments/manifest.json` | P0 upstream | `post_segmentation`, propagation |
| `content_brief_reanchor` | patches `content_brief.json` | manifest | **`post_reanchor`** (blocks `analysis_complete`) |
| `optimal_questions` | `gap_report.json` | reanchor complete | `post_gaps` |
| — | `analysis_complete.json` | G1 clear | — |
| `topic_coverage_audit` | `coverage_audit.json` | G2 flow1, profile, **`assert_delivery_ready`** | `pre_delivery` |
| `narrative_arc_plan` | `narrative_plan.json` | coverage audit | Flow 1 spine |
| `full_master_ranking` | `selection.json` | narrative plan | Flow 1 spine |
| `transitions` | `transitions.json` | selection | Flow 1 spine |
| `sound_design_plan` | SDP merge | transitions + gap_report | SDP cross-validate |
| `edl` | `edl.json` | G1 VO, transitions | EDL verify |
| `assembly_preview` | `assembly_preview.wav` | edl | pre-audio |
| `mmaudio_sfx` | SFX assets | **assembly_preview.wav** | pre-audio readiness |
| `mix` | `assembly.wav` | SDP flow1 cues | mix QC |
| `master_finalize` | `master.wav` | assembly.wav | master QC |

**Readiness APIs:** `GET /api/runs/{id}/flow1-readiness?scope=flow1|pre_audio`

**Regression:** `python tools/progression_chain_sanity.py --scope full`

Generated manifest: `docs/cross-cutting/artifact-manifest.json` via `tools/codegen_artifact_manifest.py`.
