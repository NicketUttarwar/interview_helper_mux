"""Mix's own refusal is asked ahead of dispatch: junction recuts first (ISSUES 131).

The run this guards (one-hour source, exec_102): the walk dispatched mix with
critical incomplete-cut residuals on the live EDL. Mix refused at error level
("incomplete_cut_unresolved"), the stage was logged failed, recovery pinned
junction_snip_qa, and the delivery pass ended failed before the resume did
what the refusal said.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.homunculus import agenda
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "junction_ahead")


def _arm(monkeypatch, *, live: bool, exempt: bool) -> None:
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda c: [{"kind": "on_a_roll", "severity": "critical", "segment_id": "seg_056"}] if live else [],
    )
    monkeypatch.setattr(
        "interview_mux.ordering_authority.ordering_exempt",
        lambda c, stage, pre: "junction_recut_precedes_mix" if exempt else None,
    )
    monkeypatch.setattr("interview_mux.homunculus.runtime._seed_prereq_block", lambda c, s: None)
    monkeypatch.setattr("interview_mux.delivery_guardrails.seed_stage_complete", lambda c, s: True)


def test_junction_runs_before_mix_when_mix_would_refuse(ctx, monkeypatch) -> None:
    _arm(monkeypatch, live=True, exempt=True)
    ran: list[str] = []
    retried: set[str] = set()
    out = agenda._run_seed_prerequisites_first(ctx, "mix", retried, lambda c, s: ran.append(s))
    assert ran == ["junction_snip_qa"]
    assert out == ["junction_snip_qa"]
    assert "junction_snip_qa" in retried


def test_it_runs_once_per_walk(ctx, monkeypatch) -> None:
    _arm(monkeypatch, live=True, exempt=True)
    ran: list[str] = []
    retried: set[str] = set()
    agenda._run_seed_prerequisites_first(ctx, "mix", retried, lambda c, s: ran.append(s))
    agenda._run_seed_prerequisites_first(ctx, "mix", retried, lambda c, s: ran.append(s))
    assert ran == ["junction_snip_qa"]


def test_a_clean_edl_dispatches_mix_directly(ctx, monkeypatch) -> None:
    _arm(monkeypatch, live=False, exempt=True)
    ran: list[str] = []
    assert agenda._run_seed_prerequisites_first(ctx, "mix", set(), lambda c, s: ran.append(s)) == []
    assert ran == []


def test_junction_is_not_sent_ahead_when_it_may_not_run_before_mix(ctx, monkeypatch) -> None:
    """Without the ordering exemption its dispatch would refuse on the seed order."""
    _arm(monkeypatch, live=True, exempt=False)
    ran: list[str] = []
    assert agenda._run_seed_prerequisites_first(ctx, "mix", set(), lambda c, s: ran.append(s)) == []
    assert ran == []


def test_other_stages_are_untouched(ctx, monkeypatch) -> None:
    _arm(monkeypatch, live=True, exempt=True)
    ran: list[str] = []
    assert agenda._run_seed_prerequisites_first(ctx, "edl", set(), lambda c, s: ran.append(s)) == []
    assert ran == []


def test_a_junction_failure_is_raised_as_the_prerequisite_failure(ctx, monkeypatch) -> None:
    _arm(monkeypatch, live=True, exempt=True)

    def _boom(c, s):
        raise RuntimeError("junction ladder exhausted")

    with pytest.raises(agenda.SeedPrerequisiteFailed) as info:
        agenda._run_seed_prerequisites_first(ctx, "mix", set(), _boom)
    assert "junction_snip_qa is not complete ahead of mix" in str(info.value)


def test_the_check_is_mixs_own_refusal_and_the_ordering_authority() -> None:
    src = Path(agenda.__file__).read_text(encoding="utf-8")
    body = src[src.find("def _junction_owes_recut_before_mix") :]
    body = body[: body.find("\ndef ", 10)]
    assert "live_incomplete_cut_critical_findings(ctx)" in body
    assert 'ordering_exempt(ctx, "junction_snip_qa", "mix")' in body
