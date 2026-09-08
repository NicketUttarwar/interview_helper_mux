# Conductor system.txt ↔ host parity (R1e)

Source: `docs/prompts/homunculus/conductor/system.txt`. Soft = prompt-only until host enforces.

| Prompt law (summary) | Host enforcement | Soft? | Durable if soft gap |
|----------------------|------------------|-------|---------------------|
| May skip/reorder/surgical rerun | tools skip/schedule/rerun + filters | no | — |
| walk_seed_remainder not automatic | only on tool or post-conductor walk | no | — |
| invalidate only when stale | heal_only vs structural; no BLAST wire | **partial** | Wire BLAST_RADIUS |
| Admit keep/reformat/drop | admit_result tool | no | — |
| Pack fact IDs only | pack_volley / axis_select | no | — |
| Max 3 invokes / masters / mixes | budget.check_dispatch | no | — |
| G0 blocks; cannot skip/auto_resolve | gates.set_gate + g0_blocks_analysis | no | — |
| Never force-complete transcribe without artifacts | seed_stage_complete / hollow | no | Wave 1 |
| Do not skip topology without samples | _refuse_topology_skip_without_samples | no | — |
| adjudicate before synth when Framing Yes | filter / stage order + prompt | **partial** | harden filter if missing |
| hollow_done → rerun once then needs_operator | HollowSkipBlockedError path | no | — |
| No music triad before assembly | _refuse_music_before_assembly + filter | no | — |
| No delivery analysis rewind when artifacts exist | _refuse_delivery_timeline_rewind | no | — |
| After master: ears then end_judgment then ship | prompt + walk_to_publish | soft for ears order | Wave 10 leftover filter |
| Media-IP CTA omit without ranking rerun | media_ip_cta host | no | Wave 4 |
| Do not wipe phase on surgical rerun | rerun_stage unmark only | no | — |
