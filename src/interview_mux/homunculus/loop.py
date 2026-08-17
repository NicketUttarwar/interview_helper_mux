"""OpenAI tool-loop gateway. Nested LLM calls also enter here on 0.1.0+."""

from __future__ import annotations

import json
from typing import Any

from interview_mux.homunculus.admit import admit
from interview_mux.homunculus.budget import LimitExhausted, check_audio_serialize, check_dispatch
from interview_mux.homunculus.ledger import append_ledger, packet_hash_for
from interview_mux.homunculus.registry import ToolSpec, openai_tools_payload, spec_by_name
from interview_mux.homunculus.runtime import dispatch_stage, is_homunculus_run
from interview_mux.run_context import RunContext

CONDUCTOR_PROMPT_REL = "docs/prompts/homunculus/conductor/system.txt"


def nested_chat_create(ctx: RunContext, identity: str, client: Any, kwargs: dict[str, Any]) -> Any:
    """Single OpenAI create. 0.0.0: passthrough. 0.1.0: budget + ledger + admit.

    Schema retries inside one stage invoke do not consume a second identity count.
    """
    if not is_homunculus_run(ctx):
        return client.chat.completions.create(**kwargs)
    from interview_mux.homunculus.ledger import read_ledger

    last_for = None
    for row in reversed(read_ledger(ctx)):
        if row.get("identity") == identity:
            last_for = row
            break
    counting = not (last_for and last_for.get("status") == "started")
    if counting:
        check_dispatch(ctx, identity=identity, kind="llm")
        ph = packet_hash_for(kwargs.get("messages") or kwargs.get("user"))
        check_dispatch(ctx, identity=identity, kind="llm", packet_hash=ph)
        append_ledger(
            ctx,
            {
                "kind": "llm",
                "identity": identity,
                "packet_hash": ph,
                "status": "started",
            },
        )
    resp = client.chat.completions.create(**kwargs)
    if counting:
        admit(ctx, identity=identity, action="keep", payload={"identity": identity, "ok": True})
        append_ledger(ctx, {"kind": "llm", "identity": identity, "status": "done"})
    return resp


def _tool_result(name: str, body: Any) -> dict[str, str]:
    if not isinstance(body, str):
        body = json.dumps(body, default=str)
    return {"role": "tool", "name": name, "content": body[:24000]}


def _dispatch_tool(ctx: RunContext, spec: ToolSpec, args: dict[str, Any]) -> Any:
    from interview_mux.homunculus.admit import admit as admit_fn
    from interview_mux.homunculus.admit import persist_artifact
    from interview_mux.homunculus.issues import analyze_issue
    from interview_mux.homunculus.packer import pack_volley

    name = spec.name
    if name.startswith("run_stage_"):
        stage = spec.identity
        from interview_mux.pipeline import run_single_stage as _orig

        setattr(ctx, "_homunculus_inner_stage", True)
        try:
            dispatch_stage(ctx, stage, lambda: _orig(ctx, stage), source="conductor")
        finally:
            if hasattr(ctx, "_homunculus_inner_stage"):
                delattr(ctx, "_homunculus_inner_stage")
        return {"ok": True, "stage": stage}
    if name == "admit_result":
        return admit_fn(
            ctx,
            identity=str(args.get("identity") or "unknown"),
            action=str(args.get("action") or "keep"),  # type: ignore[arg-type]
            payload=args,
            fact_id=args.get("fact_id"),
        )
    if name == "pack_volley":
        return pack_volley(
            ctx,
            fact_ids=list(args.get("fact_ids") or []),
            tool_id=str(args.get("tool_id") or "nested"),
        )
    if name == "persist_artifact":
        persist_artifact(
            ctx,
            str(args["rel"]),
            args.get("payload") or {},
            fact_id=str(args["fact_id"]),
        )
        return {"ok": True}
    if name == "analyze_issue":
        return analyze_issue(
            ctx,
            str(args["issue_id"]),
            quality_hypothesis=str(args.get("quality_hypothesis") or ""),
            action=str(args.get("action") or "retry"),
            docs_cited=list(args.get("docs_cited") or []),
        )
    if name == "retrieve_canon":
        from interview_mux.homunculus.retrieve import record_docs_cited, retrieve_canon

        hits = retrieve_canon(str(args.get("query") or ""), k=int(args.get("k") or 5))
        record_docs_cited(ctx, hits)
        return hits
    if name == "read_json":
        rel = str(args.get("rel") or "")
        if rel in {"run_meta.json"} or rel.startswith(".stage_done"):
            return {"error": "tape_only_denied"}
        if not ctx.artifact_exists(rel):
            return {"error": "missing", "rel": rel}
        return ctx.read_json(rel)
    if name == "ears_stt_window":
        from interview_mux.homunculus.ears import stt_window

        return stt_window(
            ctx,
            window_id=str(args.get("window_id") or "w"),
            rel=str(args.get("rel") or "master/master.wav"),
            start_ms=int(args.get("start_ms") or 0),
            end_ms=int(args.get("end_ms") or 8000),
        )
    if name == "end_judgment":
        from interview_mux.homunculus.judge import write_judgment

        return write_judgment(
            ctx,
            verdict=str(args.get("verdict") or "reject"),
            reason=str(args.get("reason") or ""),
        )
    if name == "shape_pre_critique_gates":
        from interview_mux.homunculus.shape import run_shape_pre_gates

        try:
            return run_shape_pre_gates(ctx)
        except Exception as exc:
            return {"ok": False, "error": type(exc).__name__, "message": str(exc)[:400]}
    if name == "shape_post_critique_gates":
        from interview_mux.homunculus.shape import run_shape_post_gates

        try:
            return run_shape_post_gates(ctx)
        except Exception as exc:
            return {"ok": False, "error": type(exc).__name__, "message": str(exc)[:400]}
    if name == "set_gate":
        from interview_mux.homunculus.gates import set_gate_decision

        return set_gate_decision(
            ctx,
            str(args.get("category") or ""),
            str(args.get("action") or "present_operator"),
        )
    if name == "promote_prompt":
        from interview_mux.homunculus.prompts import promote_prompt

        return promote_prompt(ctx, str(args.get("mint_id") or ""), corpus_ok=bool(args.get("corpus_ok")))
    if name == "mint_prompt":
        from interview_mux.homunculus.prompts import mint_prompt

        return mint_prompt(
            ctx,
            str(args.get("mint_id") or "mint"),
            str(args.get("body") or ""),
            runtime=str(args.get("runtime") or "openai"),
        )
    if name == "stack_prompt_module":
        from interview_mux.homunculus.prompts import stack_module

        return stack_module(ctx, str(args.get("module") or ""))
    if name == "build_speaker_dossier":
        from interview_mux.homunculus.speakers import build_speaker_dossier

        return build_speaker_dossier(ctx)
    if name in {"run_musicgen", "run_mmaudio", "run_chatterbox", "run_s2s", "run_deepfilter", "verify_master"}:
        append_ledger(ctx, {"kind": "host", "identity": spec.identity, "args": args, "status": "started"})
        return {"ok": True, "identity": spec.identity, "queued": True, "note": "host callable via stage tools"}
    if spec.kind == "operator_action":
        append_ledger(ctx, {"kind": "operator_action", "identity": spec.identity, "args": args})
        return {"ok": True, "action_id": spec.identity, "presented": True}
    return {"ok": False, "error": f"unbound tool {name}"}


def run_conductor(
    ctx: RunContext,
    *,
    user_message: str,
    max_turns: int | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Conductor tool loop. Tests inject a stub client."""
    from interview_mux.homunculus.budget import max_conductor_turns
    from interview_mux.homunculus.prompts import load_conductor_system

    specs = [s for s in spec_by_name().values() if s.kind in {"stage", "host", "llm", "operator_action"}]
    # Keep tools array bounded: stages + core host tools.
    core = [s for s in specs if not s.name.startswith("gui_") and s.kind != "prompt"]
    tools = openai_tools_payload(core)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": load_conductor_system()},
        {"role": "user", "content": user_message},
    ]
    turns = 0
    cap = max_turns if max_turns is not None else min(12, max_conductor_turns())
    inflight: set[str] = set()
    last: dict[str, Any] = {"ok": True, "turns": 0}
    if client is None:
        from openai import OpenAI
        from interview_mux.config import require_secret

        client = OpenAI(api_key=require_secret("OPENAI_API_KEY"))
    while turns < cap:
        check_dispatch(ctx, identity="conductor_turn", kind="conductor_turn")
        append_ledger(ctx, {"kind": "conductor_turn", "identity": "conductor_turn"})
        turns += 1
        resp = client.chat.completions.create(
            model=_conductor_model(),
            messages=messages,
            tools=tools,
            tool_choice="auto",
            parallel_tool_calls=False,
        )
        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []
        if not tool_calls:
            last = {"ok": True, "turns": turns, "content": getattr(msg, "content", None)}
            break
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )
        by_name = spec_by_name()
        for tc in tool_calls:
            name = tc.function.name
            spec = by_name.get(name)
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if spec is None:
                result: Any = {"error": f"unknown tool {name}"}
            else:
                try:
                    if spec.mutating_audio:
                        check_audio_serialize(ctx, spec.identity, inflight)
                    inflight.add(spec.identity)
                    result = _dispatch_tool(ctx, spec, args if isinstance(args, dict) else {})
                except LimitExhausted as exc:
                    result = {"error": "limit_exhausted", "identity": exc.identity, "reason": exc.reason}
                    inflight.discard(spec.identity)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result),
                        }
                    )
                    return {"ok": False, "turns": turns, "limit_exhausted": True, **result}
                except Exception as exc:
                    result = {"error": type(exc).__name__, "message": str(exc)[:400]}
                finally:
                    inflight.discard(spec.identity)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str)[:24000],
                }
            )
        last = {"ok": True, "turns": turns}
    return last


def _conductor_model() -> str:
    from interview_mux.config import merged_config

    hom = ((merged_config().get("mastering") or {}).get("homunculus") or {})
    return str(hom.get("conductor_model") or "gpt-4o")
