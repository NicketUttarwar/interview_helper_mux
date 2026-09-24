# Publishability contract

**North star:** A run that reaches delivery must finish with a playable `master/master.wav` and a passing ship envelope (`post_master_quality.json` → `publish_allowed: true`) before cover/package/S3. Publishability stops contract drift **before mix** so mix/finalize are not asked to heal producer bugs.

**Reference fixture:** `tests/fixtures/exec_2538/` (Mohan podcast `exec_2538` failure family).

Implementation: `src/interview_mux/publishability_boundary.py` · heal playbooks: `src/interview_mux/heal_routing.py` · reports: `operator/publishability_report.json`, `operator/publishability_repair_plan.json`.

---

## Tier 0 — Constitutional law

These invariants apply at every checkpoint. Violations block downstream work when enforcement is on (homunculus runs or `resilience.publishability_enforce: true`).

| ID | Rule | Violation `error_class` |
|----|------|-------------------------|
| T0-1 | **No zero-duration speech on air order** — punch non-CTA keeps inside dropped CTA parents; omit CTA-class keeps | `never_touch_zeroed_keep` |
| T0-2 | **VO audibility** — active synthesize/record gap lines with WAV must have matching EDL `vo_pickup` clips | `vo_audibility_drift` |
| T0-3 | **Selection leads EDL** — speech clip order must match `ordered_segment_ids` | `selection_edl_order_drift` |
| T0-4 | **Opening orientation contract** — episode orientation must be audible in EDL when required | `opening_orientation_inaudible` |
| T0-5 | **Producer heal only** — geometry/id/text/order problems resume at the producer stage, not mix remaster | playbook `resume_stage` |
| T0-6 | **No staging ghosts at mix** — pending writes for edl/junction/mix/finalize must be cleared | `pending_write_barrier` |
| T0-7 | **PMQ before ship** — `publish_allowed: false` or missing PMQ at finalize is not ship-ready | `post_master_quality_missing`, `pmq_incomplete_ship_walk` |
| T0-8 | **Connector fuse on in full-auto** — `analysis.connector_fuse.enabled` cannot stay false under full-auto / production parity (pre-ranking mid-thought chops) | soft force via `ensure_connector_fuse_enabled_for_full_auto` |

**Never-touch geometry (T0-1 detail):** When a packaging keep (e.g. `seg_003a`) sits inside a dropped CTA parent (`seg_002`), punch holes use **manifest** bounds so the keep airs at full span. CTA/sponsor/promo-tagged keeps omit with `never_touch_unplayable` instead of punching onto air.

**Omit collateral (T0-2 / T0-4 detail):** `reconcile_edl_with_omit_ledger` strips omitted layup VO only. Episode orientation (`episode_orientation: true`) and `required: true` lines are **never** stripped when a layup on the same target is omitted.

**Opening orientation waive (T0-4 detail):** While `opening_orientation.required` is true, the VO execution-contract ladder **must not** waive that line (`tier_d_logged_waive` refuses). Durable waive is only atomic meta `omitted=true` **and** `required=false` (native cold-open / explicit operator G1 skip). Orphan line stamps (`execution_contract_waive` / `tier_d_logged_waive`) alone are not durable — seats, policy_omit, and revive clear them.

**Hosted VO floor (Cluster C):** See [hosted-vo-authority.md](hosted-vo-authority.md). `identify_hosted_vo_floor` labels `HOLLOW_ZERO` / `PARTIAL` / `MET`. Never aspirational-continue at zero seats. Keep/omit/seat disposition is single SSOT; WAV/EDL heard beats gap omit.

---

## Tier 1 — Producer checkpoints

Checkpoints run via `checkpoint_publishability(ctx, checkpoint=…)` at stage boundaries. Default is **fail-open** (log + write report); homunculus / enforce config **fail-closed**.

| Checkpoint | When | Checks |
|------------|------|--------|
| `post_cta_prune` | After CTA omit / never-touch prune | zero keeps |
| `post_edl` | End of `run_edl`, before `stage_done` | zero keeps, phantom VO, order drift, opening orientation |
| `post_junction` | After successful `junction_snip_qa` | zero keeps, order drift, critical junction residuals |
| `pre_mix` | Start of `run_mix` | all post_edl checks + pending writes + critical junction |

Wiring: `stages/assembly.py` (`post_edl`, `pre_mix`), `junction_snip_qa.py` (`post_junction`).

---

## Tier 2 — Ship

| Stage | Gate | Notes |
|-------|------|-------|
| `mix` → `master.wav` | Tier 1 `pre_mix` must pass (when enforced) | Mix does not repair EDL geometry |

### Aspirational rubrics (default)

When `mastering.aspirational_quality.enabled` is true (default), **Tier 0** remains blocking. **Rubric gates** (listen delight floors, PMQ scorecard, listenability contract, non-critical junction feel, LUFS band) are recommendations: up to three attempts per family, then `select_best_quality_candidate` restores the best-scored `master.wav` and writes `run_meta.quality_advisories`.

### Progress floors (default)

`mastering.progress_floors.enabled` (default **true**) extends the same idea to **count/score floors** across the walk — hosted VO line count, layup row density, nugget air, listenability bands, soundscape density, boundary coverage, and (when `listen_delight.catastrophic_as_advisory` is true) former catastrophic score floors:

1. **Stretch** — revive discarded / soft-omitted / skip-materializable pools (never invent under hard freeze; End-A allowlists `revive_discarded_floor_candidate`).
2. **Best-of-N** — up to `max_attempts_per_family` (default 3) where creative variance helps.
3. **Advisory-continue** — stamp `run_meta.floor_advisories` (mirrored into `quality_advisories`) and keep walking toward `master/master.wav`.

**Playability-only hard stops remain:** missing/empty master when claiming ship, zero-ms keeps / order drift / pending-write ghosts (repair or omit then continue), seated VO without render path after WAV clamp, unreadable PMQ / ship-reachability (`STRUCTURAL_PMQ_CHECKS`).

Rollback: `progress_floors.enabled: false` restores legacy fail-closed floors (including `hosted_vo_floor_unsatisfiable`). G-Publish / S3 still requires operator consent when advisories are non-empty.

When `progress_floors.listen_delight.catastrophic_as_advisory` is true (default), former catastrophic **score** floors become loud advisory + ship-best after remutate budget — they no longer mid-pipeline halt. Never-soft PMQ / playability checks (`STRUCTURAL_PMQ_CHECKS`) still hard-stop. Roll back progress floors or set `catastrophic_as_advisory: false` to restore score hard-stops; set `aspirational_quality.enabled: false` for full rubric blocking.

### Nugget air coverage goal (layup)

`analysis.nugget_layup.min_nugget_air_coverage` (**0.85**) is an **aspirational goal** when `air_coverage_aspirational` is true (default): compose archives up to `air_coverage_max_attempts` plan candidates, scores by coverage (tie-break fewer open high / craft errors), and may `select_best_layup_candidate` on attempt cap or hash oscillation. Under-goal coverage with every eligible high-salience nugget **accounted** (aired ∪ orientation-parked ∪ waived ∪ discharged) is a QC / `run_meta.layup_air_advisories` warning — not infinite thrash. Unaccounted open high-salience and coverage below `catastrophic_nugget_air_coverage` stay hard. Roll back with `air_coverage_aspirational: false`.

| Rubric | Artifact | Structural exceptions |
|--------|----------|----------------------|
| Listen delight | `mastering/listen_delight_audit.json` | Below catastrophic floors; air-script **errors** |
| PMQ scorecard | `master/post_master_quality.json` | `spoken_vo_speakable`, hash agreement, omit ledger, duration floor |
| Listenability | `master/listenability_contract.json` | — |
| Junction | `master/junction_snip_qa.json` | **Critical** residuals |
| Nugget air (layup) | `understanding/nugget_layup_qc.json` / `layup_candidates.json` | Unaccounted open high-salience; catastrophic air floor |

| Stage | Gate | Notes |
|-------|------|-------|
| `post_master_quality` | `publish_allowed: true` on master completion | `advisory_fail` rubric-only status is normal under aspirational policy |
| `master_finalize` / G-Publish | `pre_finalize` PMQ envelope | Tier-0 PMQ failures still block; rubric advisories logged only |
| Cover / package / S3 | Operator G-Publish (optional) | S3 requires operator consent when `quality_advisories` non-empty |

### Quality status vocabulary (platform)

Wire tokens on disk: `pass` | `fail` | `advisory_fail` — owned by [`quality_status.py`](../../src/interview_mux/quality_status.py). Writers and `run_meta.qc_summaries` must import constants (no raw strings). Schemas in `post_master_quality.schema.json` / `listener_scorecard.schema.json` must match; CI: `tools/audit_quality_status_enum.py` (via `scripts/verify_artifact_contract.sh`). GUI Zod maps the same artifacts. `qc_summaries.blocking` is false for `advisory_fail` (`advisory: true`).

### Residual ledger SSOT (platform)

`operator/delivery_residuals.json` is the blocking SSOT for critical residuals. Rows carry `generation` + `state` (`open`|`remediated`|`waived`|`stale`). Noop thought-complete applies never set `remediated`. Stale/mismatched-generation rows cannot block `pre_mix`. Junction QA findings are evidence; `clear_stale_incomplete_cut_residuals` demotes stamps and bumps `delivery_epoch.junction_residuals_generation`.

### Heal routing SSOT (platform)

[`heal_routing.PLAYBOOK_REGISTRY`](../../src/interview_mux/heal_routing.py) is the only `error_class → resume_stage` map. `incomplete_cut_unresolved` / critical junction → `junction_snip_qa` (never mix). `mmaudio_incomplete` / missing referenced SDP WAVs → `mmaudio_sfx`. `safe_mix_resume_stage`, recovery, and full-auto driver must call `resume_stage_for_error_class`.

### Committed vs pending master (thrash invariant)

Agenda walk-to-master / remaster / ship-stage unlock, and `filter_delivery_candidates` for `SHIP_AFTER_MASTER`, must use **committed** `master/master.wav` only (`final_path(...).is_file()` via `delivery_invariants.committed_master_wav`). A pending finalize write under `.pending_writes/master_finalize/` must not look shipped.

Ship/PMQ heal may promote pending finalize **only when**:
1. `junction_snip_qa` is seed-complete, and
2. seam autopsy commitment matches live assembly (size + sha when present), and
3. PMQ is publishable **or** listen-delight remutate is not exhausted.

Otherwise refuse promote and remutate / resume junction. Soft `e2e_soft` flags must not mark `ship_path_ready` or waive authoritative delight/PMQ floors.

Helpers: `src/interview_mux/delivery_invariants.py`.

---

## Violation catalog

| `error_class` | Typical cause | Playbook `resume_stage` | Playbook `action` |
|---------------|---------------|---------------------------|-------------------|
| `never_touch_zeroed_keep` | Clamp/NLE collapse zeroed speech | `edl` | `punch_or_omit_rebuild_edl` |
| `vo_audibility_drift` | WAV exists, EDL clip missing | `edl` | `rebuild_edl` |
| `opening_orientation_inaudible` | Orientation line not seated in EDL | `edl` | `retarget_rebuild_edl` |
| `omit_collateral_vo_strip` | Omit ledger stripped required VO | `edl` | `exempt_rebuild_edl` |
| `selection_edl_order_drift` | Speech order ≠ selection | `edl` | `rebuild_edl` |
| `incomplete_cut_unresolved` | Critical junction residuals | `junction_snip_qa` | `junction_ladder` |
| `pending_write_barrier` | Staged writes not committed | `junction_snip_qa` | `approve_or_rerun_producer` |
| `musicgen_theme_failed` | Theme bed missing after ladder | `music_palette_compose` | `generate_or_omit_bed` |
| `post_master_quality_missing` | PMQ JSON absent at finalize | `master_finalize` | `run_pmq` |
| `pmq_incomplete_ship_walk` | `publish_allowed: false` | remutate `from_stage` (narrative → `air_script_seams`) | `listen_delight_remutate` |

Full-auto routes from `operator/publishability_report.json` and PMQ `failed_checks` via `PLAYBOOK_REGISTRY` — not driver error substrings.

---

## Cascade repair plans

When a checkpoint fails under enforcement:

1. `write_publishability_report` → `operator/publishability_report.json`
2. `write_publishability_repair_plan` → `operator/publishability_repair_plan.json` with `invalidate_set` from the artifact dependency graph
3. `invalidate_downstream(ctx, resume_stage)` clears stale `stage_done` markers
4. Identical failures during the cascade are suppressed via `failure_in_active_repair_cascade`

---

## Full-auto production parity

Full-auto must match production for audio quality and ship gates. **Gate auto-progress is the only e2e affordance.**

| Variable | Full-auto | Rationale |
|----------|-----------|-----------|
| `INTERVIEW_MUX_E2E_SOFT=1` | **On** | Auto-accept G0, G-Framing, G1, G-Publish only |
| `INTERVIEW_MUX_E2E_QUALITY_WAIVERS` | **Off** | Never fake junction / PMQ / listenability |
| `MUX_E2E_MUSICGEN_ALLOW_STUB` | **Must not appear** | Real MusicGen+MMAudio or omit bed |
| `MUX_E2E_SOFT_LISTENABILITY` | **Must not appear** | Remediate or omit; no soft-pass listenability |
| `INTERVIEW_MUX_E2E_LAST_RESORT_SOFT` | **Never set** | No stub layup/orientation corpus |

Verify: `./tools/verify_full_auto_env.sh` · tests: `tests/test_full_auto_production_parity.py`.

**e2e_soft split:** Allowed = gate auto-progress. Forbidden = soft junction commit, PMQ `e2e_softened`, stub theme beds, fake listenability passes.

**No soft music/junction ship path:** Full-auto, forensics (`MUX_FORENSICS`), and production never soft-waive music/junction PMQ checks (`planned_music_preserved`, `episode_close_outro_present`, `opening_music_preserved`, `no_critical_junction_residuals`, etc.). `soft_music_junction_pmq_allowed` in `post_master_quality.py` refuses those waivers; soft music/junction remains gate-only / non-ship smoke when quality waivers are explicitly opted in outside production parity. Cascade: `tests/test_music_pmq_architecture.py`.

**Soft-pass hardness:** `soft_pass_pre_edl_delivery` writes a refuse brief then **`return []`** when last-resort soft is off. Callers must hard-stop (no corpus/transitions/narrative stubs, no pre-EDL heal-marks). Stubs only when `INTERVIEW_MUX_E2E_LAST_RESORT_SOFT=1` **and** `e2e_soft_enabled()`.

**Omit SSOT:** Live omit ledger reads from `understanding/omit_ledger.json` (not `master/`). Publishability / PMQ omit clarity must not invent a ghost master path.

---

## Guardrails (WHEN → THEN → NEVER)

| When | Then | Never |
|------|------|-------|
| Packaging keep overlaps dropped CTA never-touch | Punch (manifest) if non-CTA; else omit | Punch promo onto air |
| Layup omitted for target | Strip layup VO only | Strip episode orientation |
| Orientation WAV exists, EDL clip missing | Rebuild EDL | G1-only or mix remaster |
| Before mix | Run `pre_mix` checkpoint | Advance with zero keeps or phantom VO |
| PMQ missing at finalize | Run PMQ / remutate from producer | Encode or publish |
| Identical playbook ×3 on omitable hole | Omit hole and continue | Halt whole run for geometry bugs |
| Junction critical after ladder + one LLM | `needs_operator` halt | Explicit-omit incomplete cut |

---

## Related docs

- [operator-gates.md](../workflows/operator-gates.md) — G0, G-Publish, PMQ-before-ship
- [air-order-boundary.md](air-order-boundary.md) — selection constitution
- [mastering-quality-hardening.md](mastering-quality-hardening.md) — delight + PMQ floors
- [unattended-breakpoints.json](unattended-breakpoints.json) — Full-auto heal registry
