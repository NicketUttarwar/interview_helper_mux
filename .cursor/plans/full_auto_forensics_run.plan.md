---
name: Full-auto forensics run
overview: Agent-driven full-auto from INPUT_FILE to shipped episode with deep forensics on every gate lie and product-code fixes backed by regression tests.
status: active
todos:
  - id: create-plan
    content: Create .cursor/plans/full_auto_forensics_run.plan.md with YAML frontmatter and all 13 sections
    status: completed
  - id: launch
    content: Stop prior runs (full_auto_daemon_launch.py stop); launch fresh Full-auto with MUX_FRESH=1 and INPUT_FILE
    status: pending
  - id: observe
    content: Monitor console log, job status, stage progress; treat CPU/ffmpeg alone as non-progress
    status: pending
  - id: intervene
    content: "On trigger: parallel Agent 1 (Evidence) + Agent 2 (Product intent); fault tree before resume"
    status: pending
  - id: fix
    content: Match repair to shape; product fix + regression test; forbidden heals/waivers/stubs
    status: pending
  - id: verify
    content: Re-verify predicate after resume; verify_master, delight, PMQ, lineage audit as applicable
    status: pending
  - id: ship
    content: Confirm master.wav, cover/publish/S3 or evidenced blocker; north star listenability; stop daemon
    status: pending
---

# Full-auto forensics run

Canonical workflow for a chat that runs Full-auto **and** patches the product when gates, QC, or heals lie. Product debugger in the loop — not driver babysitter.

**INPUT_FILE** = `<placeholder>` (under `ASSETS/input/`)

---

## 1. Launch

Stop any prior Full-auto processes first:

```bash
python tools/full_auto_daemon_launch.py stop
```

Start a **fresh** run (never reuse a prior execution unless resuming the **same** run after a read-only checker fix):

```bash
MUX_RUN_MODE=full-auto \
MUX_HOMUNCULUS_VERSION=0.1.0 \
MUX_FRESH=1 \
MUX_INPUT_AUDIO=ASSETS/input/<INPUT_FILE> \
./scripts/run.sh --full-auto --input ASSETS/input/<INPUT_FILE>
```

Replace `<INPUT_FILE>` with the basename only (e.g. `my_interview.wav`). `MUX_FRESH=1` forces a new `exec_*` directory.

Monitor: `ASSETS/full_auto_console.log`, `ASSETS/full_auto_current_run.txt`, GUI at `./scripts/run.sh` port (default 8765).

---

## 2. Success criteria

Ship bar — all must hold unless a **documented hard blocker** is evidenced (missing secrets, no network for S3, etc.):

| Criterion | Verification |
|-----------|--------------|
| **Master exists** | `ASSETS/executions/<run_id>/master/master.wav` — non-trivial size |
| **Mechanical loudness** | `python tools/verify_master.py <run_dir>/master/master.wav` passes |
| **Listen delight** | `mastering/listen_delight_audit.json` — authoritative floors pass at `master_finalize` (no waiving unless product already defines that path) |
| **Publish envelope** | `master/post_master_quality.json` with `publish_allowed: true` before cover/package/S3 |
| **Cover + publish** | `episode_cover_generate` + `podcast_publish` stage_done, or evidenced hard blocker for optional G-Publish/S3 |
| **North star** | Human-listen rubric in [NORTH_STAR.md](NORTH_STAR.md): idea transmission, nugget retention, conversation fit, finishability |

**Forbidden shortcuts:** `INTERVIEW_MUX_E2E_QUALITY_WAIVERS`, stub MusicGen, soft listenability, fake `stage_done`, predicate waivers not defined in product config.

---

## 3. Session opener template

Paste this one line to start a forensics Full-auto chat:

```
Follow .cursor/plans/full_auto_forensics_run.plan.md. INPUT_FILE = <basename under ASSETS/input/>
```

---

## 4. Major vs nested error taxonomy

### Major errors (intervene — fix product or operator decision)

- Job status `error`, `gate`, or `needs_operator`
- `identical_failures` halt (same signature ×3)
- Hard quality gate: `listen_delight_audit`, `verify_master`, PMQ `publish_allowed: false`
- Systemic schema/QC failure (validation errors in payload, not driver substring alone)
- Playbook mismatch: heal action does not match `error_class` / producer stage
- Heal reported OK but **predicate unchanged** (same check still fails)
- **File-on-disk vs checker lie**: artifact exists at expected path but stage/checker says missing (or inverse)

### Nested errors (symptom only — trace upstream)

- Downstream stage fails because an upstream producer did not commit (missing EDL clip because VO never synthesized; missing manifest row because boundary stage failed; phantom ref because lineage remap not propagated)
- Missing artifact while producer stage is in `error` or `escalations/{stage}.json` is open

### Rule

Always trace nested → **major producer**. Fix the major producer only. Revisit nested only if it persists **after** major fix with a **new shape** (different `error_class`, different stage, different line_id/seg_id).

---

## 5. Intervene triggers

Intervene immediately when any of:

1. Job `error` / `gate` / `needs_operator`
2. Same playbook or error substring repeats without predicate flip
3. Disk vs checker lie (path exists, check says missing — or committed vs pending mismatch)
4. Heal OK logged but predicate unchanged on re-read
5. New error surfaced without inspecting prior QC/escalation payload
6. Idle ~8 minutes with no stage progress (CPU/ffmpeg/chatterbox activity alone is **not** progress)
7. Operator sends **PAUSE** or **STOP**
8. Monitor-only exceeded ~15 minutes without actionable forensics

Homunculus 0.1.0 walk engine does **not** replace the parent agent. Driver substring heals are **not** diagnosis.

---

## 6. Forensics protocol

**No resume before predicate understood.**

### Fault tree (walk in order)

```
symptom (log / job / gate)
  → predicate (exact file:function + field that failed)
    → producer stage (who writes that artifact)
      → contract break (which invariant: publishability T0-x, schema, lineage, VO contract)
        → root cause class:
            matcher | commit | stale_producer | schema_writer | playbook_routing
```

### Parallel sub-agents (every intervene)

Launch **Agent 1 (Evidence)** and **Agent 2 (Product intent)** in parallel; parent synthesizes and patches.

**Agent 1 — Evidence**

- `run_id` from `full_auto_current_run.txt` or newest incomplete `exec_*`
- Job status, current stage, gate id
- Exact QC / escalation / publishability payload (`operator/escalations/*.json`, `operator/publishability_report.json`, PMQ `failed_checks`)
- `line_id` / `seg_id` / `targets_segment_id` in failure
- Paths: `exists` on disk vs path checker used
- `script_hash`, `synthesis_entry`, pending vs committed writes
- `recovery_actions` + `identical_failures` signature
- Did predicate flip after last heal?

**Agent 2 — Product intent**

- Real failing check: `file:function` (not driver log substring)
- Failure **shape** (one sentence)
- Correct **producer stage** + repair machinery (`heal_routing` playbook, `invalidate_downstream`, `--from-stage`)
- Blast radius (which artifacts stale)
- Two naive shortcuts and why each breaks later

**Parent actions:** match repair to shape; stop mismatched heal immediately; narrow product fix in source; regression test for predicate; resume per matrix (§7); re-read predicate after resume.

---

## 7. Fix gate

| Step | Action |
|------|--------|
| 1 | Match repair to failure **shape** — if playbook ≠ `error_class`, stop wrong heal |
| 2 | Narrow product fix in source (checker, writer, commit path, matcher) |
| 3 | Add regression test that asserts predicate flips (or documents intentional operator path) |
| 4 | **Forbidden:** false `stage_done`, stubs, quality waivers, healing downstream of producer bug |

### Resume matrix

| Situation | Resume |
|-----------|--------|
| Checker/read bug only (artifact already correct on disk) | Same `run_id`, `--from-stage <producer>` or driver resume |
| Writer/commit bug (artifact wrong or stale) | Same `run_id` after fix + invalidate downstream per ADG |
| Schema/lineage/id churn | Same `run_id` + `audit_segment_lineage.py` after id changes |
| Unrecoverable corruption / wrong execution | `MUX_FRESH=1` fresh run |

After every resume: re-verify predicate (re-run failing check or read payload) before trusting progress.

---

## 8. VO / G1 lie class

| Shape | Diagnosis | Repair direction |
|-------|-----------|------------------|
| **Missing pickup** | Line in `gap_report` / adjudicate output but no WAV | Adjudicate → synthesize (G1 path); do not skip to EDL |
| **WAV exists, check fails** | `vo_synthesis_audit`, audibility, or matcher drift | Matcher/commit: `script_hash`, stale synthesis entry, EDL `vo_pickup` clip |
| **`synthesized: []` with G1 ok** | Gate cleared without audio | **Not success** — trace why synthesize skipped or audit lied |

Rule: G1 ok with empty synthesis is a product bug until WAV + EDL clip both committed.

---

## 9. Schema / QC

- Read **N validation errors** from LLM/stage payload (`prompt_validation`, schema path in escalation)
- Do **not** diagnose from driver log substring alone
- One retry is built into `llm_simple.py`; second failure = hard stop — fix upstream artifact or prompt contract, then `--from-stage`

---

## 10. Pipeline break shapes (generic)

Eight areas — map symptom → producer without run-specific anecdotes:

1. **Segment lineage** — orphan `seg_*` refs, remap not propagated, NLE split children missing from manifest
2. **Cuts / geometry** — zero-ms keeps, never-touch punch, junction residuals, incomplete cuts
3. **Selection vs EDL** — `ordered_segment_ids` ≠ speech clip order; ranking excludes vs EDL keeps
4. **VO / G1 contract** — gap lines, adjudicate mutations, WAV freshness, audibility drift (T0-2)
5. **EDL / narrative QC** — opening orientation inaudible, omit collateral, phantom VO clips
6. **Mix / delight** — `pre_mix` barrier, listen_delight floors, PMQ `publish_allowed`
7. **Analysis partials** — incomplete research dossier, shape degradation, gap_fill eligibility vs `pipeline_mode`
8. **Orchestration** — homunculus agenda vs ADG prereqs, pending write barrier, identical_failure halt, playbook routing from `publishability_report.json` not console grep

---

## 11. Core invariants + forbidden list

### Core invariants

- Read `operator/escalations/{stage}.json` before re-running a failed stage
- `recovery_actions` in resilience reports are hints — verify against product intent
- Producer resume: geometry/id/text/order → producer stage (`edl`, `vo_synthesize`, `boundary_detection`, …) not mix remaster
- `heal_routing.PLAYBOOK_REGISTRY` maps `error_class` → `resume_stage` + `action`
- After any `seg_*` id change: `python tools/audit_segment_lineage.py --run-id <run_id>`
- Publishability: selection leads EDL; no zero-duration speech on air; PMQ before ship ([publishability-contract.md](docs/cross-cutting/publishability-contract.md))

### Forbidden

- Driver substring as sole diagnosis
- Healing mix/finalize for EDL/VO producer bugs
- Clearing `stage_done` without `invalidate_downstream` when artifacts changed
- `force_publish` / quality waivers on Full-auto production path
- Assuming homunculus auto-heal fixed predicate without re-read
- Slogans without predicate: "just rerun edl", "skip optional", "waive delight" without product-defined path

---

## 12. End report template

When ship bar met or hard blocker documented:

```markdown
## What happened
(one paragraph: INPUT_FILE → outcome, run_id, stages touched)

## Root cause
(predicate, producer stage, root cause class, files changed)

## Guardrails added
(tests, checkers, playbook fixes)

## Dead ends
(what was tried and ruled out — prevents repeat)

## Quality & cleanup
(verify_master, listen delight, PMQ, lineage audit, daemon stopped)
```

---

## 13. When done

```bash
python tools/full_auto_daemon_launch.py stop
```

Confirm no stray `full_auto_driver.py` processes. Archive or note `run_id` and ship artifacts path for operator.

---

## Mission (merged)

Run Full-auto from **INPUT_FILE** to finished listenable episode. When gate/QC/heal is wrong → root cause in **code + artifacts** → patch → regression test → resume.

On every intervene: parallel Evidence + Product-intent sub-agents → parent patches.

VO/G1: missing pickup → adjudicate then synthesize; WAV exists but check fails → matcher/commit; G1 ok with `synthesized:[]` is not success.
