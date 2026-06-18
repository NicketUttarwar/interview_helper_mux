# June 2026 build — execution index

**Start here.** Files sort in run order by filename. Run **01 → 07** — one **new Cursor Agent chat** per step file (or automate via `./run.sh`).

### Automation (optional)

**One command** — runs steps 1–7 via Cursor SDK, then after **each** successful step:

```bash
git add .
git commit -m "june182026build: step NN …"
git push origin main
```

```bash
./docs/build-out/june182026build/run.sh
```

Requires `CURSOR_API_KEY` in `config/secrets/secrets.env` or the environment; git auth for `origin/main` assumed. Flags: `--dry-run`, `--no-git`, `--from N --to N`, `--resume`. Queue: [agent-commands.md](./agent-commands.md). See [CURSOR_EXECUTE](../../../CURSOR_EXECUTE/README.md).

---

## Sequence (required path)

| Step | File | What | Status | Gate for next |
|------|------|------|--------|---------------|
| **00** | [00-INDEX.md](./00-INDEX.md) | This index | — | — |
| **01** | [01-SETUP-preflight.md](./01-SETUP-preflight.md) | Environment baseline | [x] | Toolchain + pytest green |
| **02** | [02-WAVE-0-resilience-harness.md](./02-WAVE-0-resilience-harness.md) | Resilience harness (LARGE) | [x] | [§15](./02-WAVE-0-resilience-harness.md#15-promotion-gate-for-wave-a) |
| **03** | [03-WAVE-A-early-truth.md](./03-WAVE-A-early-truth.md) | Early truth (LARGE) | [x] | [Wave B gate](./03-WAVE-A-early-truth.md#wave-b-promotion-gate) |
| **04** | [04-WAVE-B-audio-structure.md](./04-WAVE-B-audio-structure.md) | Audio structure (LARGE) | [x] | [§9](./04-WAVE-B-audio-structure.md#9-wave-c-promotion-gate) |
| **05** | [05-WAVE-C-self-healing.md](./05-WAVE-C-self-healing.md) | Self-healing (LARGE) | [x] | [§13](./05-WAVE-C-self-healing.md#13-wave-d-promotion-gate-from-wave-c) |
| **06** | [06-WAVE-D-output-resilience.md](./06-WAVE-D-output-resilience.md) | Output resilience (LARGE) | [x] | [§13 Shipped](./06-WAVE-D-output-resilience.md#13-wave-d-promotion-gate-for-shipped-default-on) |
| **07** | [07-FINISH-signoff.md](./07-FINISH-signoff.md) | Cross-wave sign-off | [x] | [definition-of-done-signoff.md](../definition-of-done-signoff.md) |

**Out of sequence:** [99-META-regenerate-specs.md](./99-META-regenerate-specs.md) — regenerate wave docs only; not an implementation step.

---

## Gate chain

```text
01 SETUP ──► 02 WAVE-0 ──► 03 A ──► 04 B ──► 05 C ──► 06 D ──► 07 FINISH
```

---

## How to run every step (same pattern)

1. **Cursor Agent mode** → **new chat** (never batch two LARGE waves).
2. Confirm the **previous step** is `[x]` in the table above and its **gate** passed.
3. **`@`-attach** the step file (e.g. `03-WAVE-A-early-truth.md`).
4. **`@`-attach** the **standard companions** below (plus any extras listed in the step file).
5. Paste the **Agent directive** from the step file (or use the [generic directive](#generic-agent-directive)).
6. Agent marks todos `[x]` in the step file; you mark this table `[x]`.
7. Run **Verification** commands in the step file before advancing.

### Standard companions (attach on every code step 02–06)

| Path | Role |
|------|------|
| `docs/build-out/june182026build/00-INDEX.md` | Status table |
| `.cursor/rules/interview-helper-mux.mdc` | Repo constraints |
| `AGENTS.md` | Navigation |
| `docs/build-out/doc-maintenance.md` | PR doc checklist |
| `docs/build-out/testing-and-verification.md` | Verification |

### Standard companions (LARGE waves 02–06 — add these)

| Path | Role |
|------|------|
| `docs/workflows/troubleshooting.md` | Operator error rows |
| `docs/workflows/operator-gates.md` | G0–G2, profile, offers |
| `docs/cross-cutting/config-keys.md` | Config changes |

### Step 01 attachments

See [01-SETUP-preflight.md](./01-SETUP-preflight.md) — adds `anchored-toolchain.md`, `config/app.defaults.json`, `requirements.lock`.

### Step 07 attachments

See [07-FINISH-signoff.md](./07-FINISH-signoff.md) — adds wave gate refs, `definition-of-done-signoff.md`, `repository-map.md`.

---

## Generic Agent directive

Copy into every step chat (replace `NN` and wave name):

```text
Implement June 2026 build step NN per the attached step file.
Read the entire step file before editing code.
Work every unchecked todo; mark [x] in that file as you complete items.
Satisfy the step's promotion gate before finishing.
Deliver one code + docs PR. Update 00-INDEX.md step NN to [x] when done.
Do not edit .cursor/plans/*.
```

---

## Rules

- **One step file per Agent chat** — never batch two LARGE waves.
- Read each LARGE step file **top to bottom** — not optional skimming.
- No `.cursor/plans/*` edits.
- No hypothesis default-on without 15-point gates in the step file.
- [doc-maintenance.md](../doc-maintenance.md) in every code PR.

---

## Related

- [implementation-guide.md](../implementation-guide.md) — shipped BUILD waves 0–7
- [podcast-quality-roadmap.md](../../cross-cutting/podcast-quality-roadmap.md)
