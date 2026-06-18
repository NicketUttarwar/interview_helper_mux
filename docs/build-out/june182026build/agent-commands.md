# June 2026 build — CURSOR_EXECUTE command queue

**Purpose:** One Agent session per step for [june182026build](./00-INDEX.md) via [CURSOR_EXECUTE](../../../CURSOR_EXECUTE/README.md).

**Run (one command — agents + git add/commit/push after each step):**

```bash
./docs/build-out/june182026build/run.sh
```

After each successful agent step, `run.sh` runs at repo root:

```bash
git add .
git commit -m "june182026build: step NN …"
git push origin main
```

Other flags: `--dry-run`, `--no-git`, `--from N --to N`, `--resume`.

---

## Command 1 — JUN26-01: SETUP preflight

```text
Read:
@docs/build-out/june182026build/01-SETUP-preflight.md
@docs/build-out/june182026build/00-INDEX.md
@.cursor/rules/interview-helper-mux.mdc
@docs/cross-cutting/anchored-toolchain.md
@docs/build-out/testing-and-verification.md
@config/app.defaults.json
@requirements.lock

Run June 2026 build preflight per 01-SETUP-preflight.md.
Fix any failing checks that block development (deps, audit, volley doc drift).
Do not implement Wave 0 hypothesis features yet.
Update 00-INDEX.md step **01** to `[x]` when all Definition of done items pass.
```

---

## Command 2 — JUN26-02: Wave 0 resilience harness (LARGE)

```text
Read:
@docs/build-out/june182026build/02-WAVE-0-resilience-harness.md
@docs/build-out/june182026build/00-INDEX.md
@.cursor/rules/interview-helper-mux.mdc
@AGENTS.md
@docs/build-out/doc-maintenance.md
@docs/build-out/testing-and-verification.md
@docs/workflows/troubleshooting.md
@docs/workflows/operator-gates.md
@docs/cross-cutting/config-keys.md

Implement June 2026 step 02 — Wave 0 Resilience harness per the attached step file.
Read the entire 02-WAVE-0-resilience-harness.md before editing code.
Work every unchecked todo in §14; mark [x] in this file as you complete items.
Satisfy §15 before finishing. Update 00-INDEX.md step **02** to [x] when done.
One code + docs PR. Do not edit .cursor/plans/*. Do not implement Wave A–D features in this PR.
```

---

## Command 3 — JUN26-03: Wave A early truth (LARGE)

```text
Read:
@docs/build-out/june182026build/03-WAVE-A-early-truth.md
@docs/build-out/june182026build/00-INDEX.md
@.cursor/rules/interview-helper-mux.mdc
@AGENTS.md
@docs/build-out/june182026build/02-WAVE-0-resilience-harness.md
@docs/pipeline/transcription/transcript-review.md
@docs/prompts/_shared/transcript-quality-rubric.md
@docs/build-out/doc-maintenance.md
@docs/build-out/testing-and-verification.md

Implement June 2026 step 03 — Wave A Early truth per the attached step file.
Hypotheses: H-ING-03, H-G0-02, H-G0-01, H-GAP-01.
Read the entire 03-WAVE-A-early-truth.md before editing code.
Work every unchecked todo; mark [x] in this file. Update 00-INDEX.md step **03** to [x] when done.
One code + docs PR. Do not edit .cursor/plans/*.
```

---

## Command 4 — JUN26-04: Wave B audio structure (LARGE)

```text
Read:
@docs/build-out/june182026build/04-WAVE-B-audio-structure.md
@docs/build-out/june182026build/00-INDEX.md
@.cursor/rules/interview-helper-mux.mdc
@AGENTS.md
@docs/build-out/june182026build/02-WAVE-0-resilience-harness.md
@docs/build-out/june182026build/03-WAVE-A-early-truth.md
@docs/cross-cutting/interview-spine.md
@docs/cross-cutting/context-padding.md
@docs/build-out/doc-maintenance.md

Implement June 2026 step 04 — Wave B Audio structure per the attached step file.
Hypotheses: H-SEG-02 (pause ladder), H-ORC-01 (interview spine).
Read the entire 04-WAVE-B-audio-structure.md before editing code.
Preserve CLAP fail-open. Work all unchecked todos; mark [x] in this file.
Update 00-INDEX.md step **04** to [x] when done. One code + docs PR. Do not edit .cursor/plans/*.
```

---

## Command 5 — JUN26-05: Wave C self-healing (LARGE)

```text
Read:
@docs/build-out/june182026build/05-WAVE-C-self-healing.md
@docs/build-out/june182026build/00-INDEX.md
@.cursor/rules/interview-helper-mux.mdc
@AGENTS.md
@docs/build-out/june182026build/02-WAVE-0-resilience-harness.md
@docs/build-out/june182026build/04-WAVE-B-audio-structure.md
@docs/workflows/analysis-orchestration-loop.md
@docs/cross-cutting/coherence-orc03.md
@docs/build-out/doc-maintenance.md

Implement June 2026 step 05 — Wave C Self-healing per the attached step file.
Hypotheses: H-ORC-02 (investigation enqueue), H-ORC-03 (long-run coherence).
Read the entire 05-WAVE-C-self-healing.md before editing code.
Respect flow_hardening attempt budgets. Mark todos [x] in this file.
Update 00-INDEX.md step **05** to [x] when done. One code + docs PR. Do not edit .cursor/plans/*.
```

---

## Command 6 — JUN26-06: Wave D output resilience (LARGE)

```text
Read:
@docs/build-out/june182026build/06-WAVE-D-output-resilience.md
@docs/build-out/june182026build/00-INDEX.md
@.cursor/rules/interview-helper-mux.mdc
@AGENTS.md
@docs/build-out/june182026build/02-WAVE-0-resilience-harness.md
@docs/build-out/june182026build/05-WAVE-C-self-healing.md
@docs/cross-cutting/post-generation-placement.md
@docs/build-out/definition-of-done-signoff.md
@docs/build-out/doc-maintenance.md

Implement June 2026 step 06 — Wave D Output resilience per the attached step file.
Hypotheses: H-F1N-02 (emphasis → Flow 1), H-F2-02 (quotability → Flow 2), H-F1S-02 (sting placement QA).
Read the entire 06-WAVE-D-output-resilience.md before editing code.
Run recovery drills §12. No default-on until §13 + nine-scenario listen. Mark todos [x] in this file.
Update 00-INDEX.md step **06** to [x] when done. One code + docs PR. Do not edit .cursor/plans/*.
```

---

## Command 7 — JUN26-07: FINISH sign-off

```text
Read:
@docs/build-out/june182026build/07-FINISH-signoff.md
@docs/build-out/june182026build/00-INDEX.md
@docs/build-out/june182026build/02-WAVE-0-resilience-harness.md
@docs/build-out/june182026build/06-WAVE-D-output-resilience.md
@docs/build-out/definition-of-done-signoff.md
@docs/build-out/testing-and-verification.md
@docs/build-out/repository-map.md
@docs/INDEX.md
@AGENTS.md
@.cursor/rules/interview-helper-mux.mdc

Complete June 2026 build finish per the attached 07-FINISH-signoff.md.

Verify cross-wave consistency: 00-INDEX.md steps **01–06** marked `[x]`; step-file todos closed or waived;
INDEX.md and AGENTS.md link june182026build, pytest green, audit_stage_plans_doc.py clean.
Update definition-of-done-signoff.md checkboxes where automated checks already pass.
Document any remaining manual listen / nine-scenario items for the operator.
```
