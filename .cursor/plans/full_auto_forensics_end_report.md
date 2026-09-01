## What happened

INPUT `mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3` → ship on run_id `exec_4741_d19c15b58ab4_20260901T001444Z`. ~18 interventions. Final package under `publish/` (audio.mp3, cover.jpg, transcript.vtt, chapters). Master ~171 MiB / 1865 s.

## Root causes fixed

| Predicate | Class | Files |
|-----------|-------|-------|
| Driver suicide on fresh DELETE | keep_driver | web ensure_run / driver launch path |
| G1 VO open seed-order | seed → producer | g1 / seed-order routing |
| Chapter overflow | clamp + commit | chapter merge/clamp |
| Hollow layup seed thrash | seed-complete | layup seed thrash fix |
| Stale transitions → layup wipe | route | stale transition router |
| Stale SDP seed-complete | SDP completeness | stale SDP detection |
| Synth hash thrash | backfill | synthesis_report refresh |
| Mint/suppress gap mismatch | bridge mint | gap mint vs skip |
| Clone-adj transition thrash | suppress | clone adjacency |
| Missing SDP WAVs → wrong resume | safe_mix_resume | `delivery_guardrails.py` |
| Hollow mmaudio marked done | incompleteness | `stage_completion.py`, `agenda.py` |
| Lazy MusicGen vs full palette | E3 referenced-only | `sdp_cross_validate.py` |
| Junction remaster archives mix | skip layup invalidate | `air_order_integrity.py` |
| PMQ `spoken_unsupported_entity:Mohan` | enrich at PMQ | `spoken_copy_guard.py`, `post_master_quality.py` |
| Sentence-initial `Every`/`Each` false entity | ENTITY_IGNORE | `spoken_copy_guard.py` |
| Advisories blocked local encode | docs/product mismatch | `post_master_quality.py`, `aspirational_quality.py`, `sync_assets.py` |

## Guardrails added

- `test_safe_mix_resume_routes_missing_sdp_wavs_to_mmaudio`
- `test_mmaudio_incomplete_when_sdp_wavs_missing`
- `test_missing_sdp_wavs_ignores_unreferenced_lazy_slots`
- `test_junction_source_skips_layup_invalidate`
- `test_sentence_initial_determiners_are_not_unsupported_entities`
- S3 sync still gated by advisories until G-Publish Prepare (`g_publish_cleared`)

## Dead ends

- Driver/homunculus diverting `master_finalize` → junction remaster (wipe assembly) — direct `run_master_finalize` sealed master; junction must not invalidate layup from junction source.
- Forcing PMQ / e2e quality waivers — forbidden; fixed grounding + advisory/local-package split instead.
- Hash-only refresh without aligning gap↔synthesis scripts — `vo_layup_seg_043` Every→Each aligned to synthesis_report.

## Quality & cleanup

| Gate | Result |
|------|--------|
| `master/master.wav` | present (~179 MB) |
| `tools/verify_master.py` | OK — LUFS −16.03, TP −1.00 |
| `listen_delight_audit` | `passed: true`, overall 0.9376, `blocking: false` |
| PMQ `publish_allowed` | **true** (honest; no waivers) |
| `episode_cover_generate` / `podcast_publish` | stage_done; local `publish/` package ready |
| Daemon | stopped; no full_auto_driver / keepalive |

S3 upload left for operator G-Publish sync (advisory consent path intact).
