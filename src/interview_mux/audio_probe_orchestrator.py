"""Orchestrate Local Audio Probe Platform runs (MLX prefer + heuristic fail-open)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from interview_mux.audio_probe_facts import (
    add_fact,
    empty_run_facts,
    finalize_run_summary,
    zones_from_facts,
)
from interview_mux.audio_probe_flows import build_speaker_flows, flow_signals, passes_prefilter
from interview_mux.audio_probe_heuristics import heuristic_answer
from interview_mux.audio_probe_listen import answer_from_listen_evidence
from interview_mux.audio_probe_mlx import (
    classify_clip_mlx,
    extract_flow_clip,
    mlx_path_enabled,
)
from interview_mux.audio_probe_parse import parse_by_contract
from interview_mux.audio_probe_registry import (
    PROBE_CATALOG_VERSION,
    primary_gate_probes,
    probe_by_id,
)
from interview_mux.config import merged_config

LogFn = Callable[..., None]


def _cfg() -> dict[str, Any]:
    root = merged_config()
    return dict(root.get("audio_probes") or {})


def _budget_state(cfg: dict[str, Any]) -> dict[str, Any]:
    b = dict(cfg.get("budget") or {})
    return {
        "max_clips": int(b.get("max_clips") or 40),
        "max_audio_sec": float(b.get("max_audio_sec") or 600),
        "max_wall_sec": float(b.get("max_wall_sec") or 900),
        "used_clips": 0,
        "used_audio_sec": 0.0,
        "exhausted": {},
        "started_at": time.monotonic(),
    }


def _wall_ok(state: dict[str, Any]) -> bool:
    return (time.monotonic() - float(state["started_at"])) < float(state["max_wall_sec"])


def _consume_budget(state: dict[str, Any], flow: dict[str, Any], budget_class: str) -> bool:
    if not _wall_ok(state):
        state["exhausted"]["wall"] = True
        return False
    if state["used_clips"] >= state["max_clips"]:
        state["exhausted"][budget_class] = True
        return False
    dur_sec = max(0, int(flow.get("duration_ms") or 0)) / 1000.0
    if state["used_audio_sec"] + dur_sec > state["max_audio_sec"]:
        state["exhausted"][budget_class] = True
        return False
    state["used_clips"] += 1
    state["used_audio_sec"] += dur_sec
    return True


def _map_probe_to_fact(probe_id: str, parsed: dict[str, Any], flow_id: str) -> list[dict[str, Any]]:
    """Return list of fact kwargs (without writing)."""
    if not parsed.get("ok"):
        return [
            {
                "fact_id": f"gf_{flow_id}_{probe_id}_unknown",
                "key": f"probe.{probe_id}",
                "value": None,
                "status": "unknown",
                "scope": "speaker_flow",
                "subject_id": flow_id,
                "confidence": 0.0,
                "evidence": {"probe_id": probe_id, "raw": parsed.get("raw")},
                "fact_type": "binary",
            }
        ]
    val = parsed.get("value")
    out: list[dict[str, Any]] = []
    if probe_id == "vprobe.multilingual_or_uncommon":
        out.append(
            {
                "fact_id": f"gf_{flow_id}_special",
                "key": "speaker_flow.is_special",
                "value": bool(val),
                "status": "asserted",
                "scope": "speaker_flow",
                "subject_id": flow_id,
                "confidence": 0.55,
                "evidence": {"probe_id": probe_id, "raw": parsed.get("raw")},
                "fact_type": "binary",
            }
        )
    elif probe_id == "vprobe.non_english_speech":
        out.append(
            {
                "fact_id": f"gf_{flow_id}_non_en",
                "key": "speaker_flow.non_english",
                "value": bool(val),
                "status": "asserted",
                "scope": "speaker_flow",
                "subject_id": flow_id,
                "confidence": 0.55,
                "evidence": {"probe_id": probe_id},
                "fact_type": "binary",
            }
        )
    elif probe_id == "vprobe.uncommon_english":
        out.append(
            {
                "fact_id": f"gf_{flow_id}_uncommon",
                "key": "speaker_flow.uncommon_english",
                "value": bool(val),
                "status": "asserted",
                "scope": "speaker_flow",
                "subject_id": flow_id,
                "confidence": 0.5,
                "evidence": {"probe_id": probe_id},
                "fact_type": "binary",
            }
        )
    elif probe_id == "vprobe.extract_keywords":
        out.append(
            {
                "fact_id": f"gf_{flow_id}_kw",
                "key": "speaker_flow.special_keywords",
                "value": val if isinstance(val, list) else [],
                "status": "asserted",
                "scope": "speaker_flow",
                "subject_id": flow_id,
                "confidence": 0.45,
                "evidence": {"probe_id": probe_id},
                "fact_type": "keyword_set",
            }
        )
    elif probe_id == "vprobe.span_hint":
        out.append(
            {
                "fact_id": f"gf_{flow_id}_spans",
                "key": "speaker_flow.special_spans",
                "value": val if isinstance(val, list) else [],
                "status": "asserted",
                "scope": "speaker_flow",
                "subject_id": flow_id,
                "confidence": 0.4,
                "evidence": {"probe_id": probe_id},
                "fact_type": "span_list",
            }
        )
    elif probe_id == "vprobe.passion_or_emphasis":
        out.append(
            {
                "fact_id": f"gf_{flow_id}_passion",
                "key": "speaker_flow.passion_level",
                "value": val,
                "status": "asserted",
                "scope": "speaker_flow",
                "subject_id": flow_id,
                "confidence": 0.4,
                "evidence": {"probe_id": probe_id},
                "fact_type": "enum",
            }
        )
    elif probe_id == "vprobe.speech_act":
        out.append(
            {
                "fact_id": f"gf_{flow_id}_act",
                "key": "speaker_flow.speech_act",
                "value": val,
                "status": "asserted",
                "scope": "speaker_flow",
                "subject_id": flow_id,
                "confidence": 0.45,
                "evidence": {"probe_id": probe_id},
                "fact_type": "enum",
            }
        )
    else:
        key_map = {
            "vprobe.pull_quote": "speaker_flow.pull_quote",
            "vprobe.crosstalk": "speaker_flow.crosstalk",
            "vprobe.non_speech_bleed": "speaker_flow.bleed",
            "vprobe.unintelligible": "speaker_flow.unintelligible",
            "vprobe.affect_burst": "speaker_flow.affect_burst",
            "vprobe.sensitive_disclosure": "speaker_flow.sensitive",
            "vprobe.disagreement": "speaker_flow.disagreement",
            "vprobe.nonliteral": "speaker_flow.nonliteral",
            "vprobe.acoustic_discontinuity": "speaker_flow.discontinuity",
            "vprobe.retelling": "speaker_flow.retelling",
            "vprobe.payoff_moment": "speaker_flow.payoff",
        }
        if probe_id == "vprobe.name_or_title":
            out.append(
                {
                    "fact_id": f"gf_{flow_id}_names",
                    "key": "speaker_flow.heard_names",
                    "value": val if isinstance(val, list) else [],
                    "status": "asserted",
                    "scope": "speaker_flow",
                    "subject_id": flow_id,
                    "confidence": 0.35,
                    "evidence": {"probe_id": probe_id},
                    "fact_type": "keyword_set",
                }
            )
        elif probe_id in key_map:
            out.append(
                {
                    "fact_id": f"gf_{flow_id}_{probe_id.split('.')[-1]}",
                    "key": key_map[probe_id],
                    "value": bool(val),
                    "status": "asserted",
                    "scope": "speaker_flow",
                    "subject_id": flow_id,
                    "confidence": 0.4,
                    "evidence": {"probe_id": probe_id},
                    "fact_type": "binary",
                }
            )
    return out


def _ctx_log(ctx: Any, *args: Any, **kwargs: Any) -> None:
    if ctx is not None and hasattr(ctx, "log"):
        ctx.log(*args, **kwargs)


def run_probe_on_flow(
    probe: dict[str, Any],
    flow: dict[str, Any],
    *,
    ctx: Any = None,
    listen_evidence: dict[str, Any] | None = None,
    stage: str = "audio_probe_build",
) -> dict[str, Any]:
    """Answer one probe from cached STT-listen evidence, else heuristic fail-open.

    Production rule: STT runs once per flow (see build_audio_probe_artifacts).
    Warm-up TTS is not required for stt_listen and is not invoked here.
    """
    probe_id = str(probe["probe_id"])
    contract = str(probe.get("output") or "YES_NO")
    log: LogFn = lambda *a, **k: _ctx_log(ctx, *a, **k)  # noqa: E731
    answer: dict[str, Any]
    answer_source = "heuristic"

    if listen_evidence and listen_evidence.get("ok"):
        listen_ans = answer_from_listen_evidence(probe_id, listen_evidence, flow)
        answer = {
            "text": str(listen_ans.get("text") or ""),
            "source": "stt_listen",
            "confidence": float(listen_ans.get("confidence") or 0.7),
            "stt_text": listen_ans.get("stt_text"),
            "listen_fused": listen_ans.get("listen_fused"),
            "model_id": listen_ans.get("model_id") or listen_evidence.get("model_id"),
        }
        answer_source = "stt_listen"
    else:
        heur = heuristic_answer(probe_id, flow)
        answer = {
            "text": str(heur.get("text") or ""),
            "source": "heuristic",
            "confidence": float(heur.get("confidence") or 0.4),
        }
        if listen_evidence and listen_evidence.get("error"):
            answer["mlx_fallback_reason"] = str(listen_evidence.get("error"))[:300]
            answer_source = "heuristic_after_mlx"
            log(
                f"Probe {probe_id} on {flow.get('speaker_flow_id')}: heuristic after listen miss",
                level="info",
                stage=stage,
                action_id="audio_probes.answer.heuristic_fallback",
                detail={
                    "probe_id": probe_id,
                    "speaker_flow_id": flow.get("speaker_flow_id"),
                    "reason": answer.get("mlx_fallback_reason"),
                },
            )
        else:
            log(
                f"Probe {probe_id}: heuristic",
                level="info",
                stage=stage,
                action_id="audio_probes.answer.heuristic",
                detail={
                    "probe_id": probe_id,
                    "speaker_flow_id": flow.get("speaker_flow_id"),
                    "reason": "no_listen_evidence",
                },
            )

    parsed = parse_by_contract(
        contract,
        str(answer.get("text") or ""),
        clip_start_ms=int(flow.get("start_ms") or 0),
    )
    if not parsed.get("ok"):
        if contract.upper() in {"YES_NO", "BINARY"}:
            parsed = parse_by_contract("YES_NO", "NO")
            parsed["status"] = "unknown"
            parsed["ok"] = False
            log(
                f"Probe parse repair→unknown NO: {probe_id}",
                level="warning",
                stage=stage,
                action_id="audio_probes.parse.repair",
                detail={"probe_id": probe_id, "raw": answer.get("text")},
            )
    return {
        "probe_id": probe_id,
        "answer": answer,
        "parsed": parsed,
        "answer_source": answer_source,
    }


def _probe_wants_listen(probe: dict[str, Any]) -> bool:
    """always_sample alone should not force a Whisper subprocess."""
    pre = str(probe.get("prefilter") or "")
    if pre == "always_sample":
        return False
    if pre == "escalation_only":
        return False
    return True


def _ensure_flow_listen(
    *,
    flow: dict[str, Any],
    clip_wav: Path | None,
    listen_cache: dict[str, dict[str, Any]],
    ctx: Any,
    stage: str,
    budget: dict[str, Any],
) -> dict[str, Any] | None:
    """Run STT once per flow; charge listen budget once."""
    fid = str(flow["speaker_flow_id"])
    if fid in listen_cache:
        return listen_cache[fid]
    if clip_wav is None or not mlx_path_enabled():
        listen_cache[fid] = {"ok": False, "error": "no_clip_or_mlx_disabled", "fallback": "heuristic"}
        return listen_cache[fid]
    if not _consume_budget(budget, flow, "listen"):
        listen_cache[fid] = {"ok": False, "error": "skipped_budget", "fallback": "heuristic"}
        return listen_cache[fid]

    log: LogFn = lambda *a, **k: _ctx_log(ctx, *a, **k)  # noqa: E731
    evidence = classify_clip_mlx(
        probe_id="flow.listen",
        clip_wav=clip_wav,
        warmup_wav=None,  # stt_listen does not use spoken warm-up
        output_contract="YES_NO",
        ctx=ctx,
        stage=stage,
        log=log,
    )
    listen_cache[fid] = evidence
    _ctx_log(
        ctx,
        f"Flow listen {'ok' if evidence.get('ok') else 'miss'}: {fid}",
        level="success" if evidence.get("ok") else "warning",
        stage=stage,
        action_id="audio_probes.listen.flow",
        detail={
            "speaker_flow_id": fid,
            "ok": bool(evidence.get("ok")),
            "chars": len(str(evidence.get("stt_text") or "")),
            "error": str(evidence.get("error") or "")[:200] or None,
        },
    )
    return evidence


def empty_probe_artifacts(*, enforcement_mode: str = "shadow", reason: str = "") -> dict[str, Any]:
    """Safe empty payload so downstream stages never crash on missing probe data."""
    doc = empty_run_facts(enforcement_mode=enforcement_mode)
    doc["meta"] = {
        "probe_catalog_version": PROBE_CATALOG_VERSION,
        "flows": 0,
        "clips_used": 0,
        "empty_reason": reason or "empty",
    }
    return {
        "golden_facts": doc,
        "protected_zones": {"version": 1, "zones": []},
        "speaker_flows": {"version": 1, "flows": []},
        "probe_report": {
            "version": 1,
            "catalog_version": PROBE_CATALOG_VERSION,
            "rows": [],
            "empty_reason": reason or "empty",
        },
        "audio_tags_by_flow": {},
    }


def build_audio_probe_artifacts(
    transcript: dict[str, Any],
    *,
    ctx: Any = None,
    source_wav: Path | None = None,
    work_dir: Path | None = None,
    stage: str = "audio_probe_build",
) -> dict[str, Any]:
    """Run enabled probes over speaker flows; return facts, zones, flows, report."""
    cfg = _cfg()
    if not bool(cfg.get("enabled", True)):
        _ctx_log(
            ctx,
            "audio_probes disabled by config",
            level="info",
            stage=stage,
            action_id="audio_probes.disabled",
        )
        return empty_probe_artifacts(
            enforcement_mode=str(cfg.get("enforcement_mode") or "shadow"),
            reason="disabled",
        )

    enforcement = str(cfg.get("enforcement_mode") or "shadow")
    enabled_packs = cfg.get("enabled_packs")
    pack_set = set(enabled_packs) if isinstance(enabled_packs, list) else None
    low_conf = float(cfg.get("low_confidence_threshold") or 0.85)
    fail_open = bool(cfg.get("fail_open", True))

    try:
        flows = build_speaker_flows(transcript)
    except Exception as exc:  # noqa: BLE001
        _ctx_log(
            ctx,
            f"Speaker-flow build failed: {exc}",
            level="error",
            stage=stage,
            action_id="audio_probes.flows.fail",
            detail={"error": str(exc)[:400]},
        )
        if fail_open:
            return empty_probe_artifacts(enforcement_mode=enforcement, reason=f"flows_failed:{exc}")
        raise

    flows_by_id = {str(f["speaker_flow_id"]): f for f in flows}
    doc = empty_run_facts(enforcement_mode=enforcement)
    budget = _budget_state(cfg)
    report_rows: list[dict[str, Any]] = []
    audio_tags: dict[str, dict[str, Any]] = {}
    clip_by_flow: dict[str, Path | None] = {}
    listen_by_flow: dict[str, dict[str, Any]] = {}
    stats = {"stt_listen": 0, "heuristic": 0, "heuristic_after_mlx": 0, "skipped": 0, "flows_listened": 0}

    _ctx_log(
        ctx,
        f"Audio probes start: flows={len(flows)} mlx={mlx_path_enabled()} source={bool(source_wav)}",
        level="info",
        stage=stage,
        action_id="audio_probes.build.start",
        detail={
            "flows": len(flows),
            "mlx_enabled": mlx_path_enabled(),
            "has_source_wav": bool(source_wav and Path(source_wav).is_file()),
            "enforcement_mode": enforcement,
            "pack_filter": sorted(pack_set) if pack_set else None,
        },
    )

    gate_probes = primary_gate_probes()
    if pack_set:
        gate_probes = [p for p in gate_probes if p.get("pack") in pack_set]

    clip_root = None
    if work_dir is not None:
        clip_root = Path(work_dir) / "probe_clips"
        clip_root.mkdir(parents=True, exist_ok=True)

    for flow in flows:
        fid = str(flow["speaker_flow_id"])
        sig = flow_signals(flow, low_conf=low_conf)
        tags: dict[str, Any] = {"speaker_id": flow.get("speaker_id")}

        # Decide which probes fire on primary transcript signals.
        passing: list[dict[str, Any]] = []
        deferred_vernacular: list[dict[str, Any]] = []
        for probe in gate_probes:
            ok, reason = passes_prefilter(str(probe.get("prefilter") or ""), sig)
            if ok:
                passing.append(probe)
                continue
            if str(probe.get("prefilter") or "") == "vernacular_candidate":
                deferred_vernacular.append(probe)
                continue
            stats["skipped"] += 1
            report_rows.append(
                {
                    "speaker_flow_id": fid,
                    "probe_id": probe["probe_id"],
                    "skipped": True,
                    "skip_reason": reason,
                }
            )

        wants_listen = any(_probe_wants_listen(p) for p in passing)
        # Extract clip only when we will listen (or may escalate after vernacular YES).
        if wants_listen and source_wav is not None and clip_root is not None and fid not in clip_by_flow:
            dest = clip_root / f"{fid}.wav"
            clip_by_flow[fid] = extract_flow_clip(
                source_wav=Path(source_wav),
                dest_wav=dest,
                start_ms=int(flow.get("start_ms") or 0),
                end_ms=int(flow.get("end_ms") or 0),
                log=lambda *a, **k: _ctx_log(ctx, *a, **k),
                stage=stage,
            )

        listen_evidence: dict[str, Any] | None = None
        if wants_listen:
            listen_evidence = _ensure_flow_listen(
                flow=flow,
                clip_wav=clip_by_flow.get(fid),
                listen_cache=listen_by_flow,
                ctx=ctx,
                stage=stage,
                budget=budget,
            )
            if listen_evidence and listen_evidence.get("ok"):
                stats["flows_listened"] = int(stats.get("flows_listened") or 0) + 1
                # Re-score vernacular after listen fusion (chicken-egg recovery).
                from interview_mux.audio_probe_listen import fuse_flows, listen_flow_from_evidence

                fused = fuse_flows(
                    flow,
                    listen_flow_from_evidence(
                        listen_evidence,
                        speaker_id=str(flow.get("speaker_id") or ""),
                        start_ms=int(flow.get("start_ms") or 0),
                        end_ms=int(flow.get("end_ms") or 0),
                    ),
                )
                if fused.get("listen_fused"):
                    sig = flow_signals(fused, low_conf=low_conf)

            for probe in deferred_vernacular:
                ok, reason = passes_prefilter("vernacular_candidate", sig)
                if ok:
                    passing.append(probe)
                else:
                    stats["skipped"] += 1
                    report_rows.append(
                        {
                            "speaker_flow_id": fid,
                            "probe_id": probe["probe_id"],
                            "skipped": True,
                            "skip_reason": reason,
                        }
                    )
        else:
            for probe in deferred_vernacular:
                stats["skipped"] += 1
                report_rows.append(
                    {
                        "speaker_flow_id": fid,
                        "probe_id": probe["probe_id"],
                        "skipped": True,
                        "skip_reason": "no_vernacular_signal",
                    }
                )

        for probe in passing:
            if not _wall_ok(budget):
                stats["skipped"] += 1
                report_rows.append(
                    {
                        "speaker_flow_id": fid,
                        "probe_id": probe["probe_id"],
                        "skipped": True,
                        "skip_reason": "skipped_wall",
                    }
                )
                continue

            try:
                use_listen = bool(
                    listen_evidence
                    and (
                        _probe_wants_listen(probe)
                        or listen_evidence.get("ok")
                    )
                )
                result = run_probe_on_flow(
                    probe,
                    flow,
                    ctx=ctx,
                    listen_evidence=listen_evidence if use_listen else None,
                    stage=stage,
                )
            except Exception as exc:  # noqa: BLE001 — never abort whole build on one probe
                _ctx_log(
                    ctx,
                    f"Probe exception fail-open: {probe['probe_id']}@{fid}: {exc}",
                    level="warning",
                    stage=stage,
                    action_id="audio_probes.probe.fail_open",
                    detail={"probe_id": probe["probe_id"], "speaker_flow_id": fid, "error": str(exc)[:300]},
                )
                if not fail_open:
                    raise
                heur = heuristic_answer(str(probe["probe_id"]), flow)
                result = {
                    "probe_id": probe["probe_id"],
                    "answer": {"text": heur.get("text"), "source": "heuristic", "confidence": 0.3},
                    "parsed": parse_by_contract(
                        str(probe.get("output") or "YES_NO"),
                        str(heur.get("text") or "NO"),
                        clip_start_ms=int(flow.get("start_ms") or 0),
                    ),
                    "answer_source": "heuristic_exception",
                }

            src = str(result.get("answer_source") or "heuristic")
            stats[src] = stats.get(src, 0) + 1
            report_rows.append(
                {
                    "speaker_flow_id": fid,
                    "probe_id": probe["probe_id"],
                    "skipped": False,
                    "answer_source": src,
                    "answer": {
                        "text": (result.get("answer") or {}).get("text"),
                        "source": (result.get("answer") or {}).get("source"),
                    },
                    "parsed": {
                        "ok": result["parsed"].get("ok"),
                        "status": result["parsed"].get("status"),
                        "value": result["parsed"].get("value"),
                    },
                }
            )
            for fk in _map_probe_to_fact(probe["probe_id"], result["parsed"], fid):
                add_fact(doc, **fk)

            parsed = result["parsed"]
            if probe["probe_id"] == "vprobe.passion_or_emphasis" and parsed.get("ok"):
                tags["passion_level"] = parsed.get("value")
            if probe["probe_id"] == "vprobe.speech_act" and parsed.get("ok"):
                tags["speech_act"] = parsed.get("value")
            if (
                probe["probe_id"] == "vprobe.multilingual_or_uncommon"
                and parsed.get("ok")
                and parsed.get("value")
            ):
                tags["is_special"] = True
                for esc_id in probe.get("escalation") or []:
                    esc = probe_by_id(str(esc_id))
                    if not esc:
                        continue
                    if pack_set and esc.get("pack") not in pack_set:
                        continue
                    if not _wall_ok(budget):
                        continue
                    try:
                        esc_res = run_probe_on_flow(
                            esc,
                            flow,
                            ctx=ctx,
                            listen_evidence=listen_evidence,
                            stage=stage,
                        )
                    except Exception as exc:  # noqa: BLE001
                        _ctx_log(
                            ctx,
                            f"Escalation fail-open: {esc_id}@{fid}: {exc}",
                            level="warning",
                            stage=stage,
                            action_id="audio_probes.escalation.fail_open",
                            detail={"probe_id": esc_id, "error": str(exc)[:300]},
                        )
                        continue
                    report_rows.append(
                        {
                            "speaker_flow_id": fid,
                            "probe_id": esc["probe_id"],
                            "skipped": False,
                            "escalation": True,
                            "answer_source": esc_res.get("answer_source"),
                            "answer": {
                                "text": (esc_res.get("answer") or {}).get("text"),
                                "source": (esc_res.get("answer") or {}).get("source"),
                            },
                            "parsed": {
                                "ok": esc_res["parsed"].get("ok"),
                                "value": esc_res["parsed"].get("value"),
                            },
                        }
                    )
                    for fk in _map_probe_to_fact(esc["probe_id"], esc_res["parsed"], fid):
                        add_fact(doc, **fk)
                    if esc["probe_id"] == "vprobe.extract_keywords" and esc_res["parsed"].get("ok"):
                        tags["keywords"] = esc_res["parsed"].get("value") or []
                    if esc["probe_id"] == "vprobe.span_hint" and esc_res["parsed"].get("ok"):
                        tags["spans"] = esc_res["parsed"].get("value") or []

        if tags:
            audio_tags[fid] = tags

    finalize_run_summary(doc)
    doc["run"]["budget_exhausted_by_class"] = budget.get("exhausted") or {}
    doc["meta"] = {
        "probe_catalog_version": PROBE_CATALOG_VERSION,
        "flows": len(flows),
        "clips_used": budget["used_clips"],
        "answer_stats": stats,
        "flows_listened": stats.get("flows_listened"),
    }
    zones = zones_from_facts(doc, flows_by_id)

    _ctx_log(
        ctx,
        f"Audio probes done: vernacular={doc.get('run', {}).get('has_in_flow_vernacular')} "
        f"zones={len(zones.get('zones') or [])} stats={stats}",
        level="success",
        stage=stage,
        action_id="audio_probes.build.done",
        detail={
            "vernacular": doc.get("run", {}).get("has_in_flow_vernacular"),
            "zones": len(zones.get("zones") or []),
            "answer_stats": stats,
            "enforcement_mode": enforcement,
            "must_keep_placeholder": doc.get("run", {}).get("vernacular_must_keep_segment_ids") or [],
        },
    )

    return {
        "golden_facts": doc,
        "protected_zones": zones,
        "speaker_flows": {"version": 1, "flows": flows},
        "probe_report": {
            "version": 1,
            "catalog_version": PROBE_CATALOG_VERSION,
            "rows": report_rows,
            "answer_stats": stats,
        },
        "audio_tags_by_flow": audio_tags,
    }
