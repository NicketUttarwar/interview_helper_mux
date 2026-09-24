# Artifact sanitize

Deterministic, **non-amplifying** baseline cleanup for selection-class handoffs. Sanitizers refuse hollow growth, stamp `_meta.sanitize`, and hard-gate consumers when unsanitary (`artifact_sanitize.block_consumers`).

**Code:** [`src/interview_mux/artifact_sanitize/`](../../src/interview_mux/artifact_sanitize/) · CLI [`tools/sanitize_run.py`](../../src/interview_mux/tools/sanitize_run.py)

---

## Purpose

Selection-class sanitize runs at fixed delivery seams so downstream producers (layup, Pass B seats, transitions, VO, EDL) inherit a sanitary baseline instead of repairing amplification mid-flight.

| Concern | Behavior |
|---------|----------|
| Non-amplifying | Never grow air order / seats beyond budgets; CTA readmit capped |
| Authority split | Gap (W1) cleans copy/shape only; seats/omit live in air contract (W3) |
| Halt | `sanitize_refused:*` / `*_unsanitary` → operator stamp (not auto-continue) |

---

## Precedence

Constitutional order for seat / omit / bind decisions ([`precedence.py`](../../src/interview_mux/artifact_sanitize/precedence.py)):

1. **Required orientation** — never strip
2. **Operator override skip** — explicit skips win
3. **Clamp seats ≤ rendered WAVs** — when floor met, clamp wins
4. **Pass B published seats** — after clamp
5. **Hosted framing ensure** — only when floor unmet and clamp would not undo
6. **Bind freshness** (`line_vo_wav_fresh`) — mismatch ⇒ delete + regenerate
7. **Synth regenerate** — after seats sanitary and text final
8. **Ledger mirrors** gap/seats — never invents seat expansion

Gap sanitize (W1) must **not** mutate: `vo_seats`, omit-ledger entries, clamp seats, ensure hosted framing (those are W3).

---

## Ship units (waves)

| Unit | Waves | Artifacts | Note |
|------|-------|-----------|------|
| Baseline text | **W1 + W2 together** | `gap_report` + `nugget_layup_plan` | Ship as one; do not trust layup/gap handoffs until both sanitary |
| Seat contract | **W3 before trusting seat stamps** | `mastering_plan` vo_seats ↔ gap flags ↔ omit ledger | Seat stamps are not authoritative until air-contract sanitize |
| Selection-class | W4 | `transitions` | After air order stable |
| Bind / render | W5–W6 | VO synth report, EDL + assembly ledger | After seats sanitary |
| SDP schema | W7 | `sound_design_plan` | Schema-correct only |
| Closeout | **W8** | docs / stage guidance / homunculus pins | This doc |

---

## Pipeline stages

Thin delivery stages in [`DELIVERY_ORDER`](../../src/interview_mux/v2/config.py):

| Stage | Artifact | Role |
|-------|----------|------|
| `selection_order_sanitize` | `master/selection.json` | After ranking; non-amplifying air-order cleanup. Prefers hard-keeps; **refuses** (pins `full_master_ranking`) when depth/family/span cannot be met without dropping a hard-keep. Seat-freeze restore must not stamp `sanitize.ok=True` over an unsanitary order. |
| `gap_report_sanitize` | `understanding/gap_report.json` | After `nugget_layup_compose`; W1 shape/dedupe/lock |
| `air_contract_sanitize` | `mastering/mastering_plan.json` (+ omit mirror) | After `air_script_seams`; W3 seats ↔ flags ↔ ledger |

Recovery maps `selection_unsanitary` / `gap_unsanitary` / `air_contract_unsanitary` / `sanitize_refused:*` to these stage pins. Lattice / integrity tokens (`hard_keep_*`, `air_order_integrity_critical`) pin **`full_master_ranking`** — sanitize does not amplify.

---

## Out of scope

- **`seam_autopsy`** — junction listenability between mix and master ([seam-autopsy.md](./seam-autopsy.md))
- **MusicGen epoch** — Phase B/C music planning / `mmaudio_sfx` ([delivery-phases.md](./delivery-phases.md))
- **Analysis P2** — talking points / ideal cuts / content-brief analysis passes

---

## Invalidate matrices (high-level)

Sanitizers prefer stamp + refuse over broad rewinds. When mutation does change order or seats:

| Source | Typical clear / stale | Must not wipe |
|--------|----------------------|---------------|
| `selection_order_sanitize` (order change via air-order bus) | `transitions` / `edl` stage_done; assembly seating stale; layup invalidate when fingerprint changes | Music epoch seal; junction-only remaster must not archive layup |
| `gap_report_sanitize` | Blocks consumers until sanitary; marker-only unmark via `maybe_invalidate_after_sanitize` | Pass B seats, omit ledger authority (W3); no EDL/music wipe |
| `air_contract_sanitize` | Rewrites seats ↔ gap omit flags ↔ omit ledger; may re-clamp to WAVs; marker cascade | Selection air order; MusicGen assets |
| Bounded heal profiles | See [`execution_invalidation_profiles.py`](../../src/interview_mux/execution_invalidation_profiles.py) + [`INVALIDATION_BLAST_RADIUS`](../../src/interview_mux/delivery_guardrails.py) | Profiles forbid clearing sealed music / wrong producers |

### F10 sanitary preflight (dual path)

Shared [`sanitary_preflight_errors`](../../src/interview_mux/artifact_sanitize/preflight.py) feeds both `run_preflight` and `collect_stage_input_issues` (always merge — never elif-xor). First-run missing-artifact is OK; dirty/stale baselines block.

### Write-path allowlists

```bash
bash tools/check_artifact_write_paths.sh
```

Runs selection / gap / air-contract / transitions / EDL allowlists plus
**`check_one_writer_fs_bypass.sh`** (bans `fs_write_json` of hot authority files
outside sanitize / staging / intentional restore). Wired under
`CHECK_ARTIFACT_CONTRACTS=1` / `CI=1` in `tools/check_prerequisites.sh`.

### One-writer admission (hot JSON)

Hot delivery authority files persist through a single admit layer
([`artifact_sanitize/one_writer.py`](../../src/interview_mux/artifact_sanitize/one_writer.py)):

| Rel | Sole commit API |
|-----|-----------------|
| `master/selection.json` | `commit_selection_mutation` |
| `understanding/gap_report.json` | `commit_gap_report_doc` (sanitize + spoken cascade) |
| `master/edl.json` | sanitize-on-write via one_writer; sealed generation via `write_live_edl` |
| `master/transitions.json` | `commit_transitions_doc` / `persist_transitions_doc` |
| `understanding/sound_design_plan.json` | `commit_sound_design_plan_doc` |
| `understanding/nugget_layup_plan.json` | `commit_nugget_layup_plan_doc` |

`RunContext.write_json` and `write_committed_json` route these rels after schema
validation. Commit helpers set `_one_writer_admit` to avoid recursion. Tests /
progression fixtures may set `_one_writer_raw = True` or use `fs_write_json`
(allowlisted) for seed stamps.

---

## Config

Keys under `artifact_sanitize` in `config/app.defaults.json` (also [config-keys.md](./config-keys.md)):

| Key | Default | Role |
|-----|---------|------|
| `artifact_sanitize.block_consumers` | `true` | Hard-gate consumers while unsanitary |
| `artifact_sanitize.halt_after` | `3` | Identical sanitize refuse halt (code default) |
| `artifact_sanitize.selection.max_same_family_on_air` | `8` | Cap NLE children from one base id |
| `artifact_sanitize.selection.max_fragment_depth` | `3` | Collapse deeper fragment trees |
| `artifact_sanitize.selection.max_cta_readmit` | `0` | Disable unbounded CTA story readmit (`_readmit_cta_story_children` honors this) |
| `artifact_sanitize.selection.max_order_growth_pct` | `15` | Clamp repair amplification past growth budget |
| `artifact_sanitize.gap.min_layup_coverage` / `layup.min_layup_coverage` | `0.70` | Optional coverage floor for gap/layup refuse |

### Sanitize-last (selection)

`commit_selection_mutation` always runs `sanitize_master_selection` **after** checkpoint and **before** disk. Amplifying `repair_master_selection` must not reverse sanitize drops (`max_cta_readmit=0`, excluded/banned membership ceiling, growth clamp). Stale `_meta.sanitize` stamps that diverge from `order_content_hash` are ignored by `selection_sanitary_errors`.

### Resume after sanitize↔repair thrash (ops)

Do **not** hand-edit `master/selection.json`. After product fix is green:

1. Stop the full-auto driver thrash loop.
2. Resume the **same** `run_id` so sanitize can commit and flip the incompleteness predicate.
3. Identical-failure / sticky counters clear only on predicate flip (or forensics force) — never by deleting the execution folder mid-campaign.

---

## CLI

Dry-run sanitize (no commit):

```bash
python -m interview_mux.tools.sanitize_run --run-id X --artifact gap
```

Commit selection when ok (selection path only commits via air-order bus):

```bash
python -m interview_mux.tools.sanitize_run --run-id X --artifact gap --commit
```

Aliases: `selection`, `gap` / `gap_report`, `transitions`, `edl`, `vo`, `layup`, `sdp`. Add `--json` for machine output.

---

## Related

- [air-order-boundary.md](./air-order-boundary.md) — selection mutation lifecycle
- [air-script.md](./air-script.md) — Pass A / Pass B seats
- [publishability-contract.md](./publishability-contract.md) — selection leads EDL
- [nugget-layup-system.md](./nugget-layup-system.md) — layup → gap_report handoff
