"""Lay-up copy must be airable whoever wrote it: model, heal or recovery.

Client run (Mohan source, exec_014): nugget_layup_compose hard-stopped on
spoken_speaker_role_label and spoken_gendered_pronoun for seg_001d then seg_023.
The surviving line was "The host recap adds that the assay discussed covers
more than a thousand genes. Who is he — and why start there?". Recovery for the
open high-salience nug_016 pasted its note-style claim into the line, the heal
skipped it, the nugget reopened, and retries ran out of budget.
"""

from __future__ import annotations

from interview_mux.nugget_layup import CORPUS_REL, recover_open_high_salience_nuggets, repair_or_skip_spoken_copy_layups
from interview_mux.run_context import RunContext
from interview_mux.spoken_copy_guard import REGISTER_VIOLATION_CODES, scrub_spoken_register
from interview_mux.spoken_meta_lint import spoken_structure_hits
from test_nugget_layup import _seed_air_order, _set_host_guest_speakers

CLIENT_LINE = (
    "The host recap adds that the assay discussed covers more than a thousand genes. "
    "Who is he — and why start there?"
)
NOTE_CLAIM = "The host recap adds that the assay discussed covers more than a thousand genes."


def _register_hits(text: str) -> set[str]:
    return set(spoken_structure_hits(text)) & set(REGISTER_VIOLATION_CODES)


def test_scrub_keeps_the_claim_and_clears_the_register_rules() -> None:
    out = scrub_spoken_register(CLIENT_LINE)
    assert not _register_hits(out)
    assert "thousand genes" in out
    assert out[0].isupper()


def _ctx(monkeypatch, name: str) -> RunContext:
    ctx = RunContext(name, create=True)
    _seed_air_order(
        ctx,
        ["seg_002", "seg_023"],
        {
            "seg_002": "Welcome, today we talk about diagnostics.",
            "seg_023": "We built the panel to look at the genes that drive resistance.",
        },
    )
    _set_host_guest_speakers(ctx)
    monkeypatch.setattr("interview_mux.source_topology.pickup_eligible_speaker_id", lambda _c: "spk_0")
    ctx.write_json(
        CORPUS_REL,
        {
            "nuggets": [
                {
                    "nugget_id": "nug_016",
                    "text_claim": NOTE_CLAIM,
                    "evidence_quote": "more than a thousand genes",
                    "in_selection": False,
                    "salience": "high",
                }
            ]
        },
    )
    return ctx


def test_heal_scrubs_model_copy_instead_of_skipping(monkeypatch) -> None:
    ctx = _ctx(monkeypatch, "exec_layup_register_heal")
    plan = {
        "ordered_segment_ids": ["seg_002", "seg_023"],
        "layups": [
            {
                "target_segment_id": "seg_023",
                "line_id": "vo_layup_seg_023",
                "text": CLIENT_LINE,
                "nugget_ids": ["nug_016"],
                "selected_nugget_ids": ["nug_016"],
                "setup_from_nuggets": NOTE_CLAIM,
                "target_beat": "Why the panel targets resistance genes",
                "listener_need_entering_T": "The gene panel needs a setup.",
                "forward_unlock": "Why start there?",
                "skip": False,
            }
        ],
    }
    fixed, _notes = repair_or_skip_spoken_copy_layups(ctx, plan)
    row = next(r for r in fixed["layups"] if r.get("line_id") == "vo_layup_seg_023")
    assert row.get("skip") is not True
    assert not _register_hits(str(row.get("text") or ""))
    assert "thousand genes" in str(row.get("text") or "")


def test_recovery_attaches_an_airable_claim(monkeypatch) -> None:
    ctx = _ctx(monkeypatch, "exec_layup_register_recover")
    plan = {
        "ordered_segment_ids": ["seg_002", "seg_023"],
        "open_high_salience_nugget_ids": ["nug_016"],
        "layups": [
            {
                "target_segment_id": "seg_023",
                "line_id": "vo_layup_seg_023",
                "text": "That panel is the reason the lab could move fast. Why start there?",
                "nugget_ids": [],
                "selected_nugget_ids": [],
                "skip": False,
            }
        ],
    }
    out, _notes = recover_open_high_salience_nuggets(ctx, plan)
    texts = [str(r.get("text") or "") for r in out["layups"] if not r.get("skip")]
    assert any("thousand genes" in t for t in texts)
    assert not any(_register_hits(t) for t in texts)
