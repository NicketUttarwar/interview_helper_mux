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

**Never-touch geometry (T0-1 detail):** When a packaging keep (e.g. `seg_003a`) sits inside a dropped CTA parent (`seg_002`), punch holes use **manifest** bounds so the keep airs at full span. CTA/sponsor/promo-tagged keeps omit with `never_touch_unplayable` instead of punching onto air.

**Omit collateral (T0-2 / T0-4 detail):** `reconcile_edl_with_omit_ledger` strips omitted layup VO only. Episode orientation (`episode_orientation: true`) and `required: true` lines are **never** stripped when a layup on the same target is omitted.

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
| `post_master_quality` | `publish_allowed: true` | Feel-audit missing is **fail-open** when seams are clean (`commit_ok`, zero critical junction residuals) |
| `master_finalize` / G-Publish | `pre_finalize` PMQ envelope | PMQ missing ≠ ship-ready |
| Cover / package / S3 | Operator G-Publish (optional) | Reaching finalize implies delight passed in authoritative mode |

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
| `pmq_incomplete_ship_walk` | `publish_allowed: false` | `mix` | `listen_delight_remutate` |

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
