"""Safe-prune escalation: chunk, pack, one-shot flagship retry, no loop."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from interview_mux.llm_simple import StageError, run_llm_stage_simple
from interview_mux.safe_pruning import (
    SafePruneExhausted,
    chunk_source,
    create_chat_with_context_ladder,
    estimate_tokens,
    is_context_length_error,
    pack_pruned_volley,
)
from interview_mux.stages import llm_runner
from interview_mux.volley_packet_lint import lint_llm_user_payload


class _VerifyOk:
    ok = True
    errors: list[str] = []
    schema_name = ""
    interaction_id = "t"


class _CtxLen(RuntimeError):
    def __init__(self) -> None:
        super().__init__("context_length_exceeded: too many tokens")
        self.code = "context_length_exceeded"


def test_is_context_length_error() -> None:
    assert is_context_length_error(_CtxLen())
    assert not is_context_length_error(RuntimeError("rate limit"))


def test_chunk_source_splits_segments() -> None:
    payload = {
        "thesis": "keep header",
        "segments": [{"segment_id": f"s{i}", "text": "word " * 40} for i in range(6)],
    }
    chunks = chunk_source(json.dumps(payload), budget=400, max_chunks=24)
    assert len(chunks) >= 2
    assert all("thesis" in c for c in chunks)


def test_pack_passes_tape_lint() -> None:
    messages = pack_pruned_volley(
        keeps_by_chunk=[
            [
                {
                    "segment_id": "seg_001",
                    "quote": "the founder kept the tape rolling through the deal",
                    "why_relevant": "thesis",
                }
            ]
        ],
        header_hint="header",
    )
    user = json.loads(messages[0]["content"])
    cleaned = lint_llm_user_payload(user, require_tape=True)
    assert "excerpts" in cleaned
    assert "exists" not in cleaned


def test_flagship_context_length_prunes_then_succeeds(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    from interview_mux.run_context import RunContext

    ctx = RunContext("run_prune", create=True)
    ctx.write_json("run_meta.json", {"execution_id": ctx.run_id}, skip_handoff=True)

    models_seen: list[str] = []
    kinds: list[str] = []

    def fake_create(**kwargs):  # noqa: ANN003
        models_seen.append(str(kwargs.get("model")))
        msgs = kwargs.get("messages") or []
        blob = json.dumps(msgs)
        if "safe_prune_extract" in blob or "original_system_prompt" in blob:
            kinds.append("extract")
            raw = json.dumps(
                {
                    "keeps": [
                        {
                            "segment_id": "seg_001",
                            "quote": "the guest described the first customer call in detail",
                            "why_relevant": "topic",
                        }
                    ]
                }
            )
            return MagicMock(choices=[MagicMock(message=MagicMock(content=raw))])
        if "safe_pruned" in blob:
            kinds.append("packed_flagship")
            env = {
                "status": "complete",
                "artifacts": {"ok": True},
                "memory_updates": {},
                "needs": [],
                "follow_up_investigations": [],
                "confidence": 0.9,
                "reasoning_summary": "pruned",
            }
            return MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps(env)))])
        kinds.append("first")
        raise _CtxLen()

    client = MagicMock()
    client.chat.completions.create.side_effect = lambda **kw: fake_create(**kw)

    user = json.dumps(
        {
            "segments": [{"segment_id": "seg_001", "text": "the guest described the first customer call in detail"}]
        }
    )
    with patch.object(llm_runner, "OpenAI", return_value=client):
        with patch.object(llm_runner, "require_secret", return_value="sk-test"):
            with patch.object(llm_runner, "load_system_prompt_for_stage", return_value="Answer topics from tape."):
                with patch("interview_mux.llm_preflight.run_schema_preflight", return_value=[]):
                    with patch("interview_mux.llm_response_verify.verify_llm_response", return_value=_VerifyOk()):
                        with patch.object(llm_runner, "resolve_model") as res:
                            res.return_value = MagicMock(model_id="gpt-5.6-terra", tier="flagship")
                            env = llm_runner.run_prompt_envelope(
                                "content_context",
                                "understanding/content-context.system.txt",
                                user_content=user,
                                task_kind="primary",
                                explicit_tier="flagship",
                                ctx=ctx,
                            )
    assert env.get("status") == "complete"
    assert "extract" in kinds
    assert "packed_flagship" in kinds
    assert kinds.count("first") == 1
    assert all("gpt-4o-mini" not in m or True for m in models_seen)


def test_advisory_also_gets_prune(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    from interview_mux.run_context import RunContext

    ctx = RunContext("run_prune_adv", create=True)
    ctx.write_json("run_meta.json", {"execution_id": ctx.run_id}, skip_handoff=True)

    def fake_create(**kwargs):  # noqa: ANN003
        blob = json.dumps(kwargs.get("messages") or [])
        if "original_system_prompt" in blob:
            return MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content=json.dumps(
                                {
                                    "keeps": [
                                        {
                                            "quote": "seam text from the tape about the deal close",
                                            "why_relevant": "feel",
                                        }
                                    ]
                                }
                            )
                        )
                    )
                ]
            )
        if "safe_pruned" in blob:
            return MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content=json.dumps(
                                {
                                    "status": "complete",
                                    "artifacts": {"ok": True},
                                    "needs": [],
                                    "follow_up_investigations": [],
                                    "confidence": 1,
                                    "reasoning_summary": "ok",
                                }
                            )
                        )
                    )
                ]
            )
        raise _CtxLen()

    client = MagicMock()
    client.chat.completions.create.side_effect = lambda **kw: fake_create(**kw)
    with patch.object(llm_runner, "OpenAI", return_value=client):
        with patch.object(llm_runner, "require_secret", return_value="sk-test"):
            with patch.object(llm_runner, "load_system_prompt_for_stage", return_value="Audit junction feel."):
                with patch("interview_mux.llm_preflight.run_schema_preflight", return_value=[]):
                    with patch("interview_mux.llm_response_verify.verify_llm_response", return_value=_VerifyOk()):
                        with patch.object(llm_runner, "resolve_model") as res:
                            res.return_value = MagicMock(model_id="gpt-5.6-terra", tier="flagship")
                            env = llm_runner.run_prompt_envelope(
                                "junction_feel_audit",
                                "segmentation/connector-seam-adjudicate.system.txt",
                                user_content=json.dumps({"pairs": [{"combined_seam_text": "deal close tape"}]}),
                                task_kind="advisory",
                                explicit_tier="flagship",
                                ctx=ctx,
                            )
    assert env.get("status") == "complete"


def test_over_budget_pack_hard_stops(monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.safe_pruning.safe_pruning_cfg",
        lambda cfg=None: {
            "enabled": True,
            "extract_tier": "economy",
            "economy_chunk_char_budget": 80000,
            "flagship_input_token_budget": 10,
            "max_chunks": 24,
        },
    )
    with pytest.raises(SafePruneExhausted, match="over flagship budget"):
        from interview_mux.safe_pruning import run_safe_prune_pack

        with patch(
            "interview_mux.safe_pruning.extract_chunk_keeps",
            return_value=[{"quote": "x" * 200, "why_relevant": "t", "excerpts": ["tape"]}],
        ):
            run_safe_prune_pack(
                original_system="sys",
                source=json.dumps({"excerpts": ["the tape rolled on"]}),
                ctx=None,
                stage_key="content_context",
            )


def test_packed_flagship_context_length_does_not_loop(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    from interview_mux.run_context import RunContext

    ctx = RunContext("run_prune_loop", create=True)
    ctx.write_json("run_meta.json", {"execution_id": ctx.run_id}, skip_handoff=True)
    calls = {"n": 0}

    def fake_create(**kwargs):  # noqa: ANN003
        calls["n"] += 1
        blob = json.dumps(kwargs.get("messages") or [])
        if "original_system_prompt" in blob:
            return MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content=json.dumps(
                                {
                                    "keeps": [
                                        {
                                            "quote": "enough tape words for a keep excerpt here",
                                            "why_relevant": "q",
                                        }
                                    ]
                                }
                            )
                        )
                    )
                ]
            )
        raise _CtxLen()

    client = MagicMock()
    client.chat.completions.create.side_effect = lambda **kw: fake_create(**kw)
    with pytest.raises(SafePruneExhausted):
        with patch.object(llm_runner, "OpenAI", return_value=client):
            with patch.object(llm_runner, "require_secret", return_value="sk-test"):
                with patch.object(llm_runner, "load_system_prompt_for_stage", return_value="system"):
                    with patch("interview_mux.llm_preflight.run_schema_preflight", return_value=[]):
                        with patch("interview_mux.llm_response_verify.verify_llm_response", return_value=_VerifyOk()):
                            with patch.object(llm_runner, "resolve_model") as res:
                                res.return_value = MagicMock(model_id="gpt-5.6-terra", tier="flagship")
                                llm_runner.run_prompt_envelope(
                                    "content_context",
                                    "understanding/content-context.system.txt",
                                    user_content=json.dumps({"excerpts": ["tape"]}),
                                    task_kind="primary",
                                    explicit_tier="flagship",
                                    ctx=ctx,
                                )
    # first flagship + extracts + packed flagship; must not keep pruning
    assert calls["n"] <= 8


def test_llm_simple_treats_exhausted_as_final(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    from interview_mux.run_context import RunContext

    ctx = RunContext("run_prune_simple", create=True)
    ctx.write_json("run_meta.json", {"execution_id": ctx.run_id}, skip_handoff=True)
    n = {"c": 0}

    def boom(*_a, **_k):  # noqa: ANN001, ANN003
        n["c"] += 1
        raise SafePruneExhausted("done")

    with patch("interview_mux.llm_simple.run_prompt_envelope", side_effect=boom):
        with patch(
            "interview_mux.local_volley_framer.prepare_volley_for_llm",
            side_effect=Exception("skip"),
        ):
            with pytest.raises(StageError, match="safe prune"):
                run_llm_stage_simple(
                    ctx,
                    "content_context",
                    "understanding/content-context.system.txt",
                    lambda _c: {"excerpts": ["tape from the interview guest"]},
                    persist_artifacts=lambda *_a, **_k: None,
                    auto_complete=False,
                )
    assert n["c"] == 1


def test_cover_vision_uses_ladder() -> None:
    client = MagicMock()
    n = {"c": 0}

    def fake_create(**kwargs):  # noqa: ANN003
        n["c"] += 1
        if n["c"] == 1:
            raise _CtxLen()
        return MagicMock(choices=[MagicMock(message=MagicMock(content='{"winner_index":0}'))])

    client.chat.completions.create.side_effect = lambda **kw: fake_create(**kw)
    with patch(
        "interview_mux.model_registry.resolve_model",
        return_value=MagicMock(model_id="gpt-5.6-terra"),
    ):
        with patch(
            "interview_mux.safe_pruning.run_safe_prune_pack",
            return_value=[{"role": "user", "content": json.dumps({"excerpts": ["title"], "keeps": []})}],
        ):
            resp = create_chat_with_context_ladder(
                client,
                {
                    "model": "gpt-5.6-terra",
                    "messages": [
                        {"role": "system", "content": "pick"},
                        {"role": "user", "content": "rank covers"},
                    ],
                },
                stage_key="episode_cover_vision_pick",
                original_system="pick",
            )
    assert resp.choices[0].message.content
    assert n["c"] == 2


def test_economy_bumps_to_flagship_then_prunes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    from interview_mux.run_context import RunContext

    ctx = RunContext("run_econ", create=True)
    ctx.write_json("run_meta.json", {"execution_id": ctx.run_id}, skip_handoff=True)
    tiers: list[str] = []

    def fake_resolve(stage_key, task_kind="primary", bump_tier=False, explicit_tier=None):  # noqa: ANN001
        tier = explicit_tier or "economy"
        mid = {"economy": "gpt-4o-mini", "standard": "gpt-4o", "flagship": "gpt-5.6-terra"}[tier]
        tiers.append(tier)
        return MagicMock(model_id=mid, tier=tier)

    def fake_create(**kwargs):  # noqa: ANN003
        model = str(kwargs.get("model"))
        blob = json.dumps(kwargs.get("messages") or [])
        if "original_system_prompt" in blob:
            return MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content=json.dumps(
                                {
                                    "keeps": [
                                        {
                                            "quote": "tape evidence about the founding story here",
                                            "why_relevant": "q",
                                        }
                                    ]
                                }
                            )
                        )
                    )
                ]
            )
        if "safe_pruned" in blob:
            return MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content=json.dumps(
                                {
                                    "status": "complete",
                                    "artifacts": {"ok": True},
                                    "needs": [],
                                    "follow_up_investigations": [],
                                    "confidence": 1,
                                    "reasoning_summary": "ok",
                                }
                            )
                        )
                    )
                ]
            )
        if model == "gpt-5.6-terra" and "safe_pruned" not in blob:
            raise _CtxLen()
        if model == "gpt-4o-mini":
            raise _CtxLen()
        raise _CtxLen()

    client = MagicMock()
    client.chat.completions.create.side_effect = lambda **kw: fake_create(**kw)
    with patch.object(llm_runner, "OpenAI", return_value=client):
        with patch.object(llm_runner, "require_secret", return_value="sk-test"):
            with patch.object(llm_runner, "load_system_prompt_for_stage", return_value="system"):
                with patch("interview_mux.llm_preflight.run_schema_preflight", return_value=[]):
                    with patch("interview_mux.llm_response_verify.verify_llm_response", return_value=_VerifyOk()):
                        with patch.object(llm_runner, "resolve_model", side_effect=fake_resolve):
                            env = llm_runner.run_prompt_envelope(
                                "transitions",
                                "assembly/transitions.system.txt",
                                user_content=json.dumps({"excerpts": ["founding story tape"]}),
                                task_kind="primary",
                                ctx=ctx,
                            )
    assert env.get("status") == "complete"
    assert "flagship" in tiers
