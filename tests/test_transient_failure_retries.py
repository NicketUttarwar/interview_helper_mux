"""A network outage must not end the run (run 8, ISSUES 146).

Every OpenAI call failed with "Connection error" for about four minutes. Each
call gave up after 14 seconds, full_master_ranking failed, and the attempt
memo then refused to re-run it ("attempted at this state with no progress"),
which stopped the walk at 42/72.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx


def test_connection_failures_are_transient_and_too_large_is_not() -> None:
    from interview_mux.stages.llm_runner import is_transient_failure

    assert is_transient_failure(RuntimeError("LLM stage full_master_ranking failed: Connection error."))
    wrapped = RuntimeError("stage failed")
    wrapped.__cause__ = TimeoutError("Request timed out.")
    assert is_transient_failure(wrapped)
    assert not is_transient_failure(RuntimeError("Request too large for gpt-4o on tokens per min"))
    assert not is_transient_failure(ValueError("schema validation failed"))


def test_backoff_waits_out_a_short_outage() -> None:
    import openai

    from interview_mux.stages.llm_runner import create_with_transient_retry

    calls = {"n": 0}
    waits: list[float] = []

    def _call():
        calls["n"] += 1
        if calls["n"] < 7:
            raise openai.APIConnectionError(request=None)  # type: ignore[arg-type]
        return "ok"

    assert create_with_transient_retry(_call, stage="x", sleep=waits.append) == "ok"
    assert sum(waits) >= 100 and max(waits) <= 60


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "exec_transient_memo")


def test_memo_does_not_refuse_a_stage_that_failed_on_the_network(ctx, monkeypatch) -> None:
    from interview_mux import dispatch_delta as dd

    monkeypatch.setattr(dd, "memo_enabled", lambda: True)
    dd.record_attempt(ctx, "full_master_ranking", outcome="started")
    dd.record_attempt(ctx, "full_master_ranking", outcome="failed_transient")
    assert dd.memo_skip(ctx, "full_master_ranking") is None


def test_a_dead_network_still_ends_after_a_few_retries(ctx, monkeypatch) -> None:
    from interview_mux import dispatch_delta as dd

    monkeypatch.setattr(dd, "memo_enabled", lambda: True)
    for _ in range(dd.MAX_TRANSIENT_RETRIES + 1):
        dd.record_attempt(ctx, "full_master_ranking", outcome="failed_transient")
    assert dd.memo_skip(ctx, "full_master_ranking") is not None


def test_a_real_failure_is_still_refused(ctx, monkeypatch) -> None:
    from interview_mux import dispatch_delta as dd

    monkeypatch.setattr(dd, "memo_enabled", lambda: True)
    dd.record_attempt(ctx, "full_master_ranking", outcome="failed")
    assert dd.memo_skip(ctx, "full_master_ranking") is not None
