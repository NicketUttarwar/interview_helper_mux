"""The one deterministic heal pass calls the open-nugget / must-keep recoveries (ISSUES 66)."""

from __future__ import annotations

from interview_mux import nugget_layup as nl


def _patch(monkeypatch, errors_seq):
    calls: list[str] = []
    seq = list(errors_seq)
    monkeypatch.setattr(
        "interview_mux.source_topology.vo_posture_is_sparse_omit", lambda c: True
    )
    monkeypatch.setattr(nl, "stamp_sparse_or_empty_corpus_exits", lambda c, p: (p, []))
    monkeypatch.setattr(nl, "stamp_valueless_skips", lambda c, p: (p, []))
    monkeypatch.setattr(nl, "_craft_error_targets", lambda qc: [])

    def _qc(ctx, plan=None):
        errs = seq.pop(0) if seq else []
        return {"ok": not errs, "errors": errs}

    monkeypatch.setattr(nl, "evaluate_layup_qc", _qc)

    def _high(ctx, plan):
        calls.append("high")
        return plan, ["attached:nug_009"]

    def _tp(ctx, plan):
        calls.append("tp")
        return plan, ["already_on_tape:tp_002"]

    monkeypatch.setattr(nl, "recover_open_high_salience_nuggets", _high)
    monkeypatch.setattr(nl, "recover_open_must_keep_talking_points", _tp)
    return calls


def test_both_recoveries_run_when_both_are_open(monkeypatch) -> None:
    calls = _patch(
        monkeypatch,
        [
            ["open_high_salience_nuggets=['nug_009']", "open_must_keep_talking_points=['tp_002']"],
            ["open_must_keep_talking_points=['tp_002']"],
        ],
    )
    _out, notes = nl.ensure_deterministic_floor_before_refuse(object(), {})
    assert calls == ["high", "tp"]
    assert "recover_tp:already_on_tape:tp_002" in notes


def test_no_recovery_when_qc_is_clean(monkeypatch) -> None:
    calls = _patch(monkeypatch, [[]])
    nl.ensure_deterministic_floor_before_refuse(object(), {})
    assert calls == []
