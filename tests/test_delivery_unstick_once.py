"""O8: maybe_auto_unstick_once — second same sig does not re-unstick."""

from __future__ import annotations

from pathlib import Path

from interview_mux.delivery_unstick import maybe_auto_unstick_once
from run_fixtures import isolated_run_ctx, patch_executions_root


def test_second_same_sig_does_not_re_unstick(
    tmp_path: Path, monkeypatch
) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = isolated_run_ctx(tmp_path, "exec_unstick_once")
    calls: list[str] = []

    def fake_unstick(c, **kwargs):  # noqa: ANN001
        calls.append("unstick")
        return {
            "ok": True,
            "from_stage": "music_palette_compose",
            "intent": "delivery_blocked",
            "mode": "delivery",
            "thrash_cleared": True,
            "phase_a_sealed": False,
        }

    monkeypatch.setattr(
        "interview_mux.delivery_unstick.run_delivery_unstick",
        fake_unstick,
    )
    sig = "incomplete_after_conductor:edl:delivery_blocked:tok1"
    first = maybe_auto_unstick_once(ctx, sig)
    assert first.get("invoked") is True
    assert first.get("already_attempted") is False
    assert calls == ["unstick"]
    second = maybe_auto_unstick_once(ctx, sig)
    assert second.get("invoked") is False
    assert second.get("already_attempted") is True
    assert calls == ["unstick"]
    ledger = ctx.read_json("operator/unstick_attempts.json")
    assert len(ledger.get("attempts") or []) == 1
    assert (ledger["attempts"][0]).get("sig") == sig
