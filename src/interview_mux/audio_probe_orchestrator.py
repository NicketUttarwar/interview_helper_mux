"""Orchestrate Local Audio Probe Platform runs (heuristic fail-open + optional MLX)."""

from __future__ import annotations

from typing import Any

from interview_mux.audio_probe_facts import (
    add_fact,
    empty_run_facts,
    finalize_run_summary,
    zones_from_facts,
)
from interview_mux.audio_probe_flows import build_speaker_flows, flow_signals, passes_prefilter
from interview_mux.audio_probe_heuristics import heuristic_answer
from interview_mux.audio_probe_parse import parse_by_contract
from interview_mux.audio_probe_registry import (
    PROBE_CATALOG_VERSION,
    primary_gate_probes,
    probe_by_id,
)
from interview_mux.config import merged_config


def _cfg() -> dict[str, Any]:
    root = merged_config()
    return dict(root.get("audio_probes") or {})


def _budget_state(cfg: dict[str, Any]) -> dict[str, Any]:
    b = dict(cfg.get("budget") or {})
    return {
        "max_clips": int(b.get("max_clips") or 40),
        "max_audio_sec": float(b.get("max_audio_sec") or 600),
        "used_clips": 0,
        "used_audio_sec": 0.0,
        "exhausted": {},
    }


def _consume_budget(state: dict[str, Any], flow: dict[str, Any], budget_class: str) -> bool:
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
        # Generic YES/NO packs
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


def run_probe_on_flow(probe: dict[str, Any], flow: dict[str, Any]) -> dict[str, Any]:
    """Execute one probe (heuristic path; MLX hook reserved)."""
    probe_id = str(probe["probe_id"])
    ans = heuristic_answer(probe_id, flow)
    parsed = parse_by_contract(
        str(probe.get("output") or "YES_NO"),
        str(ans.get("text") or ""),
        clip_start_ms=int(flow.get("start_ms") or 0),
    )
    if not parsed.get("ok"):
        # one repair: re-ask binary if possible
        if str(probe.get("output") or "").upper() in {"YES_NO", "BINARY"}:
            parsed = parse_by_contract("YES_NO", "NO")
            parsed["status"] = "unknown"
            parsed["ok"] = False
    return {
        "probe_id": probe_id,
        "answer": ans,
        "parsed": parsed,
    }


def build_audio_probe_artifacts(transcript: dict[str, Any]) -> dict[str, Any]:
    """Run enabled probes over speaker flows; return facts, zones, flows, report."""
    cfg = _cfg()
    enforcement = str(cfg.get("enforcement_mode") or "shadow")
    enabled_packs = cfg.get("enabled_packs")
    pack_set = set(enabled_packs) if isinstance(enabled_packs, list) else None
    low_conf = float(cfg.get("low_confidence_threshold") or 0.85)

    flows = build_speaker_flows(transcript)
    flows_by_id = {str(f["speaker_flow_id"]): f for f in flows}
    doc = empty_run_facts(enforcement_mode=enforcement)
    budget = _budget_state(cfg)
    report_rows: list[dict[str, Any]] = []
    audio_tags: dict[str, dict[str, Any]] = {}

    gate_probes = primary_gate_probes()
    if pack_set:
        gate_probes = [p for p in gate_probes if p.get("pack") in pack_set]

    for flow in flows:
        fid = str(flow["speaker_flow_id"])
        sig = flow_signals(flow, low_conf=low_conf)
        tags: dict[str, Any] = {"speaker_id": flow.get("speaker_id")}
        for probe in gate_probes:
            ok, reason = passes_prefilter(str(probe.get("prefilter") or ""), sig)
            if not ok:
                report_rows.append(
                    {
                        "speaker_flow_id": fid,
                        "probe_id": probe["probe_id"],
                        "skipped": True,
                        "skip_reason": reason,
                    }
                )
                continue
            bclass = str(probe.get("budget_class") or "salience")
            if not _consume_budget(budget, flow, bclass):
                report_rows.append(
                    {
                        "speaker_flow_id": fid,
                        "probe_id": probe["probe_id"],
                        "skipped": True,
                        "skip_reason": "skipped_budget",
                    }
                )
                add_fact(
                    doc,
                    fact_id=f"gf_{fid}_{probe['probe_id']}_budget",
                    key=f"probe.{probe['probe_id']}",
                    value=None,
                    status="skipped_budget",
                    scope="speaker_flow",
                    subject_id=fid,
                    evidence={"skip_reason": "skipped_budget"},
                )
                continue

            result = run_probe_on_flow(probe, flow)
            report_rows.append(
                {
                    "speaker_flow_id": fid,
                    "probe_id": probe["probe_id"],
                    "skipped": False,
                    "answer": result["answer"],
                    "parsed": {
                        "ok": result["parsed"].get("ok"),
                        "status": result["parsed"].get("status"),
                        "value": result["parsed"].get("value"),
                    },
                }
            )
            for fk in _map_probe_to_fact(probe["probe_id"], result["parsed"], fid):
                add_fact(doc, **fk)

            # Tag helpers
            parsed = result["parsed"]
            if probe["probe_id"] == "vprobe.passion_or_emphasis" and parsed.get("ok"):
                tags["passion_level"] = parsed.get("value")
            if probe["probe_id"] == "vprobe.speech_act" and parsed.get("ok"):
                tags["speech_act"] = parsed.get("value")
            if probe["probe_id"] == "vprobe.multilingual_or_uncommon" and parsed.get("ok") and parsed.get("value"):
                tags["is_special"] = True
                # Escalation
                for esc_id in probe.get("escalation") or []:
                    esc = probe_by_id(str(esc_id))
                    if not esc:
                        continue
                    if pack_set and esc.get("pack") not in pack_set:
                        continue
                    if not _consume_budget(budget, flow, str(esc.get("budget_class") or "vernacular")):
                        continue
                    esc_res = run_probe_on_flow(esc, flow)
                    report_rows.append(
                        {
                            "speaker_flow_id": fid,
                            "probe_id": esc["probe_id"],
                            "skipped": False,
                            "escalation": True,
                            "answer": esc_res["answer"],
                            "parsed": {
                                "ok": esc_res["parsed"].get("ok"),
                                "value": esc_res["parsed"].get("value"),
                            },
                        }
                    )
                    for fk in _map_probe_to_fact(esc["probe_id"], esc_res["parsed"], fid):
                        add_fact(doc, **fk)

        if tags:
            audio_tags[fid] = tags

    finalize_run_summary(doc)
    doc["run"]["budget_exhausted_by_class"] = budget.get("exhausted") or {}
    doc["meta"] = {
        "probe_catalog_version": PROBE_CATALOG_VERSION,
        "flows": len(flows),
        "clips_used": budget["used_clips"],
    }
    zones = zones_from_facts(doc, flows_by_id)
    return {
        "golden_facts": doc,
        "protected_zones": zones,
        "speaker_flows": {"version": 1, "flows": flows},
        "probe_report": {
            "version": 1,
            "catalog_version": PROBE_CATALOG_VERSION,
            "rows": report_rows,
        },
        "audio_tags_by_flow": audio_tags,
    }
