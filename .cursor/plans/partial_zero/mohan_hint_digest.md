# Mohan hint digest — forensics_errors histograms

**HINT only.** Code is SSOT. Do not treat these counts as proof of HEAD bugs.

**Source runs (Mohan):**
| HINT exec | Folder |
|-----------|--------|
| 13159 | `ASSETS/executions/exec_13159_d19c15b58ab4_20260918T235157Z` |
| 13161 | `ASSETS/executions/exec_13161_d19c15b58ab4_20260919T034356Z` |
| 13163 | `ASSETS/executions/exec_13163_d19c15b58ab4_20260920T034124Z` |
| 13165 | `ASSETS/executions/exec_13165_d19c15b58ab4_20260920T142408Z` |
| 13167 | `ASSETS/executions/exec_13167_d19c15b58ab4_20260921T044550Z` |

Classifier: primary-family match on `operator/forensics_errors.json` entry text (first hit wins). See [`cousin_matrix.md`](cousin_matrix.md).

## Family × exec (entry counts)

| Family | 13159 | 13161 | 13163 | 13165 | 13167 | Σ |
|--------|------:|------:|------:|------:|------:|--:|
| HOLLOW_DONE | 0 | 0 | 0 | 0 | 48 | 48 |
| MIX_JUNCTION_SEAT | 77 | 11 | 5 | 5 | 58 | 156 |
| PIN_PREMATURE | 173 | 30 | 2 | 24 | 28 | 257 |
| FREEZE_CONSTITUTION | 47 | 52 | 34 | 37 | 45 | 215 |
| SDP_CUE_SLOTS | 10 | 33 | 6 | 4 | **655** | 708 |
| VO_LADDER_PARTIAL | 103 | 40 | **449** | 36 | 119 | 747 |
| ESR_POST_MASTER | 7 | 0 | 0 | 0 | 0 | 7 |
| SHIP_BAR_VOCAB | 79 | 2 | 2 | 2 | 2 | 87 |
| BUDGET_THRASH | 74 | 37 | 14 | 10 | 16 | 151 |
| UNCLASSIFIED | 152 | 190 | 26 | 19 | 39 | 426 |
| **entries** | **722** | **395** | **538** | **137** | **1010** | **2802** |

## Per-exec snapshot

| HINT | entries | uniq preds | by_source (top) | dominant family | top stages |
|------|--------:|-----------:|-----------------|-----------------|------------|
| 13159 | 722 | 92 | identical 412 · driver 193 · stall 72 | PIN_PREMATURE | layup, podcast_publish, transitions |
| 13161 | 395 | 77 | identical 205 · driver 141 | FREEZE + UNCLASS | finalize, layup, sound_design_plan |
| 13163 | 538 | 49 | identical 459 | VO_LADDER_PARTIAL | vo_synthesize (394), adjudicate |
| 13165 | 137 | 48 | identical 96 | FREEZE / VO / PIN | synth, edl_narrative_audit, delivery |
| 13167 | 1010 | 73 | driver 735 · identical 253 | SDP_CUE_SLOTS | sound_design_plan (662), delivery, mix |

## Intervene map (HINT state i1–i11h → family)

| Intervene | Family |
|-----------|--------|
| i1 hosted_vo / UnboundLocal | VO_LADDER_PARTIAL · HOLLOW cousin |
| i2 interrupt / premature_cap | PIN_PREMATURE |
| i3 SDP cue_slots | SDP_CUE_SLOTS |
| i4 hollow mark_done adjudicate | HOLLOW_DONE |
| i5 / i6 intro schema + spoken lint | VO_LADDER_PARTIAL |
| i7 max_invokes / lease / vo_g1 | BUDGET_THRASH · VO_LADDER |
| i8 ESR vo_wavs on sound_design | ESR_POST_MASTER |
| i9 narrative_plan hard_freeze | FREEZE_CONSTITUTION |
| i10 continuity / remutate | (spoken continuity — outside seed nine; note only) |
| i11–i11g mix⇄junction seat | MIX_JUNCTION_SEAT · HOLLOW |
| i11h finalize hollow / PMQ | HOLLOW_DONE · SHIP cousin |

## Read carefully

- **ESR_POST_MASTER** under-counts in json (often `stage_error` / driver path without wait tokens) — trust BP-C1–C4 + HINT i8 over this histogram.
- **BUDGET_THRASH** shares tokens with seed_order storms that are really VO/mix root failures.
- **SDP** spike is almost entirely HINT exec_13167 (i3 class).
