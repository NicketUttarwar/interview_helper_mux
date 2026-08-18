"""Bind conductor host tools to the same callables stages use."""

from __future__ import annotations

from typing import Any

from interview_mux.homunculus.admit import admit
from interview_mux.homunculus.ledger import append_ledger, read_ledger
from interview_mux.run_context import RunContext

_CREATIVE_ROLE_HINTS = ("theme", "underscore", "bed", "motif", "stinger")


def musicgen_attempted(ctx: RunContext) -> bool:
    return any(
        row.get("identity") == "run_musicgen" and row.get("status") in {None, "started", "done"}
        for row in read_ledger(ctx)
    )


def _creative_role(role: str) -> bool:
    lower = (role or "").lower()
    return any(h in lower for h in _CREATIVE_ROLE_HINTS)


def run_musicgen_host(ctx: RunContext, args: dict[str, Any]) -> dict[str, Any]:
    from interview_mux.musicgen_runner import generate_music_clip

    prompt = str(args.get("prompt") or "instrumental motif, no vocals")
    role = str(args.get("role") or "theme_underscore")
    out_rel = str(args.get("out_rel") or "mastering/homunculus/host/musicgen.wav")
    out_wav = ctx.path(out_rel)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    model_id = args.get("model_id")
    append_ledger(ctx, {"kind": "host", "identity": "run_musicgen", "status": "started"})
    try:
        kwargs: dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": str(args.get("negative_prompt") or ""),
            "duration_sec": float(args.get("duration_sec") or args.get("duration_seconds") or 8.0),
            "out_wav": out_wav,
            "role": role,
            "seed": int(args["seed"]) if args.get("seed") is not None else None,
        }
        meta = generate_music_clip(**kwargs)
        if model_id:
            meta = dict(meta)
            meta["requested_model_id"] = str(model_id)
        from interview_mux.homunculus.kb import record_musicgen_outcome

        record_musicgen_outcome(ctx, meta if isinstance(meta, dict) else {})
        admit(
            ctx,
            identity="run_musicgen",
            action="keep",
            payload={
                "backend": (meta or {}).get("backend"),
                "fidelity_step": (meta or {}).get("fidelity_step"),
                "model_id": (meta or {}).get("model_id"),
                "role": role,
            },
            fact_id="musicgen_winner",
        )
        append_ledger(ctx, {"kind": "host", "identity": "run_musicgen", "status": "done"})
        return {"ok": True, "identity": "run_musicgen", **(meta if isinstance(meta, dict) else {})}
    except Exception as exc:
        append_ledger(ctx, {"kind": "host", "identity": "run_musicgen", "status": "failed"})
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)[:400]}


def run_mmaudio_host(ctx: RunContext, args: dict[str, Any]) -> dict[str, Any]:
    role = str(args.get("role") or "")
    if _creative_role(role) and not musicgen_attempted(ctx):
        return {
            "ok": False,
            "error": "prefer_musicgen_first",
            "message": "Creative beds must try MusicGen large (host ladder) before MMAudio.",
        }
    from interview_mux.mmaudio_runner import generate_text_to_audio

    out_rel = str(args.get("out_rel") or "mastering/homunculus/host/mmaudio.wav")
    out_wav = ctx.path(out_rel)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    append_ledger(ctx, {"kind": "host", "identity": "run_mmaudio", "status": "started"})
    try:
        meta = generate_text_to_audio(
            prompt=str(args.get("prompt") or "soft non-vocal air"),
            duration_seconds=float(args.get("duration_sec") or args.get("duration_seconds") or 6.0),
            output_wav=out_wav,
            negative_prompt=str(args.get("negative_prompt") or ""),
            role=role or None,
            ctx=ctx,
        )
        append_ledger(ctx, {"kind": "host", "identity": "run_mmaudio", "status": "done"})
        return {"ok": True, "identity": "run_mmaudio", **(meta if isinstance(meta, dict) else {})}
    except Exception as exc:
        append_ledger(ctx, {"kind": "host", "identity": "run_mmaudio", "status": "failed"})
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)[:400]}


def run_deepfilter_host(ctx: RunContext, args: dict[str, Any]) -> dict[str, Any]:
    from interview_mux.deepfilter_runner import enhance_wav

    src_rel = str(args.get("rel") or "ingest/normalized.wav")
    dest_rel = str(args.get("out_rel") or "preclean/isolated.wav")
    src = ctx.path(src_rel)
    dest = ctx.path(dest_rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    append_ledger(ctx, {"kind": "host", "identity": "run_deepfilter", "status": "started"})
    try:
        enhance_wav(src, dest, ctx=ctx)
        append_ledger(ctx, {"kind": "host", "identity": "run_deepfilter", "status": "done"})
        return {"ok": True, "identity": "run_deepfilter", "out_rel": dest_rel}
    except Exception as exc:
        append_ledger(ctx, {"kind": "host", "identity": "run_deepfilter", "status": "failed"})
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)[:400]}


def run_chatterbox_host(ctx: RunContext, args: dict[str, Any]) -> dict[str, Any]:
    from interview_mux.chatterbox_runner import synthesize_line

    line = {
        "line_id": str(args.get("line_id") or "homunculus_vo"),
        "text": str(args.get("text") or ""),
    }
    append_ledger(ctx, {"kind": "host", "identity": "run_chatterbox", "status": "started"})
    try:
        path = synthesize_line(ctx, line)
        append_ledger(ctx, {"kind": "host", "identity": "run_chatterbox", "status": "done"})
        return {"ok": True, "identity": "run_chatterbox", "path": str(path)}
    except Exception as exc:
        append_ledger(ctx, {"kind": "host", "identity": "run_chatterbox", "status": "failed"})
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)[:400]}


def run_s2s_host(ctx: RunContext, args: dict[str, Any]) -> dict[str, Any]:
    from interview_mux.s2s_runner import synthesize_line

    line = {
        "line_id": str(args.get("line_id") or "homunculus_s2s"),
        "text": str(args.get("text") or ""),
    }
    append_ledger(ctx, {"kind": "host", "identity": "run_s2s", "status": "started"})
    try:
        path = synthesize_line(ctx, line)
        append_ledger(ctx, {"kind": "host", "identity": "run_s2s", "status": "done"})
        return {"ok": True, "identity": "run_s2s", "path": str(path)}
    except Exception as exc:
        append_ledger(ctx, {"kind": "host", "identity": "run_s2s", "status": "failed"})
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)[:400]}


def run_verify_master_host(ctx: RunContext, args: dict[str, Any]) -> dict[str, Any]:
    from interview_mux.master_qc import verify_master

    rel = str(args.get("rel") or "master/master.wav")
    path = ctx.path(rel)
    append_ledger(ctx, {"kind": "host", "identity": "verify_master", "status": "started"})
    try:
        result = verify_master(path)
        payload = {
            "ok": bool(getattr(result, "ok", True)),
            "failures": list(getattr(result, "failures", []) or []),
            "checks": list(getattr(result, "checks", []) or [])[:12],
        }
        append_ledger(ctx, {"kind": "host", "identity": "verify_master", "status": "done"})
        return {"ok": True, "identity": "verify_master", "result": payload}
    except Exception as exc:
        append_ledger(ctx, {"kind": "host", "identity": "verify_master", "status": "failed"})
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)[:400]}
