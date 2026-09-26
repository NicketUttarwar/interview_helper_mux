# Full-auto forensics end report — exec_002

## What happened

INPUT `mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3` → **ship** (local episode package) on run_id `exec_002_d19c15b58ab4_20260925T213831Z`.

- `fresh_launches = 1` (`MUX_FRESH=1` once; every fix continued this same run_id)
- **20 interventions** (i1–i20); **20 driver restarts** on the same run
- Homunculus product default (0.2.0 registered); `MUX_SKIP_PRECLEAN=1` (no DeepFilterNet)
- Master `master/master.wav` 242,577,102 B (~42:07); `publish/audio.mp3` 60,645,712 B; `publish/cover.jpg` + `package_ready.json`
- Title: **The Rare Cells in a Blood Draw**
- Window: 2026-09-25T21:38:31Z → 2026-09-26T01:47:27Z
- Per-intervene log: [full_auto_forensics_state.md](full_auto_forensics_state.md)

## Root causes fixed

| # | Predicate (short) | Producer | Cascade (`MUX_FORENSICS=0`) |
|---|-------------------|----------|------------------------------|
| i1 | preclean seed-order blocked ingest | `audio_preclean` skip.json complete | `test_skip_preclean_flag` |
| i2 | ranking ghost impact ids | FMR / framing coverage | framing + sanitize ranking tests |
| i3 | stamp-match hid protect_hosted / omit_notes | air_contract_sanitize | stamp-match + omit_notes tests |
| i4 | unpaid ranking producer on selection | selection_order_sanitize | unpaid-land sanitize restamp |
| i5 | guest-first late opening cluster | air_order_integrity | guest-first prepend test |
| i6 | IPP unpaid land vs air_contract | air_contract / done_authority | IPP co-producer paid land |
| i7 | transitions leapt past framing apply | MUST_PRECEDE | filter defers transitions |
| i8 | recompose skip-copy not primary disk | gap_framing_recompose | skip-copy primary disk |
| i9 | freeze emptied transition pairs | sanitize transitions | restore frozen pairs |
| i10 | orphaned CTA scrap children | media_ip_cta / hard_keep | CTA scrap omit tests |
| i11 | missing reorder bridges under freeze | sanitize transitions | admit required bridge |
| i12 | EDL remaining while transitions incomplete | MUST_PRECEDE edl | filter defers EDL |
| i13 | fingerprint ignored dirty content | identical_failures | dirty mtime suffix |
| i14 | persist before seam-glue mint | selection persist | mint-before-done |
| i15 | incompleteness counted justified skips | stage_completion / bridges | incompleteness honors skip |
| i16 | chapter QC used list order | narrative_qc | air-order span contiguity |
| i17 | palette compose skip-write / 0 cues | music_palette_compose End-A | palette compose freeze persist |
| i18 | SDP unpaid after compose paid land | done_authority / agenda | SDP compose co-producer |
| i19 | mix: theme_outro cue missing | music_lane + palette persist | close_bed → outro; mint close; filter defers mix |
| i20 | PMQ omit order_lock stale | omit_ledger / PMQ | `sync_stale_omit_order_lock` |

## Guardrails added

- Skip-preclean is seed-complete; CTA scrap omit is End-A CORE; required bridges survive freeze; EDL waits on transitions; dirty fingerprint includes file mtime; compose mints `compose_close_bed` and filter defers mix until it lands; PMQ rebuilds stale omit lock before evaluate.

## Dead ends

- Did **not** spawn a second `exec_*` to verify late-stage fixes.
- Did **not** attach to unused sibling `exec_001`.
- Did **not** soft-complete `edl` / `mix` / `master_finalize` or use e2e quality waivers.
- Did **not** map predicates onto End-* family ledgers mid-run.

## Quality & cleanup

| Gate | Result |
|------|--------|
| `master/master.wav` | yes (242577102 B, 2526.84 s) |
| `tools/verify_master.py` | **OK** LUFS −16.00 / TP −1.00 / 48 kHz |
| listen delight | overall **0.969**, `failed_dimensions=[]`, floors satisfied at `master_finalize` |
| PMQ `publish_allowed` | **true** (structural=`[]`; rubric advisory `scorecard_dimension_floors` clarity 0.73) |
| Local package | `publish/package_ready.json`, `audio.mp3`, `cover.jpg` |
| S3 upload | deferred — quality advisories need G-Publish consent |
| Daemon / nudge | `full_auto_daemon_launch.py stop`; §3.0a PID 60040 killed |

## Later review (optional)

State intervene log i1–i20 is enough for post-hoc predicate-family clustering. Do not block ship on ledger updates.
