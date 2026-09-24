# from_stage caller census — leapfrog_resume B+

status: shipped_with_B+  
updated: 2026-09-22  
code_is_king: true

Admit Constitution APIs (mode-wide SSOT):

| API | Role |
|-----|------|
| `heal_pin_authority.resolve_heal_from_stage` | propose → clamp → E → admit |
| `heal_pin_authority.admit_resume` | remutate / recovery / driver pin rewrites |
| `heal_pin_authority.admit_schedule` | agenda enqueue / filter defer |
| `delivery_guardrails.clamp_resume_through_order` | MUST_PRECEDE hole collapse (inside admit) |
| `delivery_guardrails.resolve_premature_cap_pin` | cap → E allowlist → admit_resume |

## Census table

| Family | Call sites (HEAD) | Must use admit | B+ wiring |
|--------|-------------------|----------------|-----------|
| Heal navigate / authority | `thrash_hardening.heal_navigate` → `resolve_heal_from_stage` | yes | IN_CODE — clamp always + admit pass |
| Premature cap / execute | `resolve_premature_cap_pin`, `apply_premature_cap_for_execute`, JobRunner | yes | IN_CODE — admit after allowlist |
| Agenda / filter | `defer_until_producers_ready` → `admit_schedule`; `filter_delivery_candidates` | yes | IN_CODE |
| Remutate | `edl_narrative_remutate.apply_edl_narrative_remutate` (+ host repair) | yes | IN_CODE — `_admit_out` |
| Recovery / seed-order | `recovery_controller` VO seed resume; `apply_seed_order_heal` | yes | IN_CODE |
| Driver | `full_auto_driver` via `heal_navigate` / `resolve_premature_cap_pin` | yes | IN_CODE (indirect) |
| CLI / GUI mode start | `cli.py`, `web/server.py` operator `from_stage=` | operator-owned | census OK — not auto-heal |
| Ownership / lifecycle | `artifact_ownership.assert_execute_from_stage`, lifecycle plans | empty-pin gate only | N/A admit |

## Lint contract (test)

`tests/test_admit_constitution.py::test_from_stage_census_allowlisted_sites` greps that the wired modules import `admit_resume` or `admit_schedule` / `resolve_heal_from_stage`.

New raw heal `from_stage=` writers must land in this table + call admit — same spirit as artifact ownership ALLOW rows.

## HAU exception table

`delivery_guardrails.HAU_SPEECH_FIRST_EXCEPTIONS` — currently `{"mix"}`; used by `earliest_incomplete_must_precede` so speech-first mix does not reinject MusicGen/MMAudio beds.
