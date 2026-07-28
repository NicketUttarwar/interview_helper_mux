"""Golden fact assembly for audio probes + vernacular zones."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_run_facts(*, enforcement_mode: str = "shadow") -> dict[str, Any]:
    return {
        "version": 1,
        "generated_at": _now(),
        "source": "audio_probe_platform_v1",
        "facts": [],
        "run": {
            "has_in_flow_vernacular": False,
            "has_non_english_spans": False,
            "has_uncommon_english": False,
            "vernacular_flow_count": 0,
            "vernacular_must_keep_segment_ids": [],
            "has_high_passion": False,
            "has_pull_quote": False,
            "has_affect_burst": False,
            "has_crosstalk": False,
            "has_bleed": False,
            "has_unintelligible": False,
            "has_discontinuity": False,
            "has_payoff": False,
            "has_sensitive_disclosure": False,
            "enforcement_mode": enforcement_mode,
            "budget_exhausted_by_class": {},
        },
        "conflicts": [],
    }


def add_fact(
    doc: dict[str, Any],
    *,
    fact_id: str,
    key: str,
    value: Any,
    status: str,
    scope: str = "run",
    subject_id: str | None = None,
    confidence: float = 0.5,
    evidence: dict[str, Any] | None = None,
    fact_type: str = "binary",
) -> None:
    row: dict[str, Any] = {
        "fact_id": fact_id,
        "scope": scope,
        "type": fact_type,
        "key": key,
        "value": value,
        "confidence": confidence,
        "status": status,
        "evidence": evidence or {},
    }
    if subject_id:
        row["subject_id"] = subject_id
    doc.setdefault("facts", []).append(row)


def finalize_run_summary(doc: dict[str, Any]) -> dict[str, Any]:
    run = doc.setdefault("run", {})
    special_flows: set[str] = set()
    keywords: list[str] = []
    for f in doc.get("facts") or []:
        if not isinstance(f, dict) or f.get("status") != "asserted":
            continue
        key = str(f.get("key") or "")
        val = f.get("value")
        if key == "speaker_flow.is_special" and val is True:
            special_flows.add(str(f.get("subject_id") or ""))
            run["has_in_flow_vernacular"] = True
        elif key == "run.has_non_english_spans" and val is True:
            run["has_non_english_spans"] = True
        elif key == "speaker_flow.non_english" and val is True:
            run["has_non_english_spans"] = True
        elif key == "speaker_flow.uncommon_english" and val is True:
            run["has_uncommon_english"] = True
        elif key == "speaker_flow.passion_level" and val == "high":
            run["has_high_passion"] = True
        elif key == "speaker_flow.pull_quote" and val is True:
            run["has_pull_quote"] = True
        elif key == "speaker_flow.affect_burst" and val is True:
            run["has_affect_burst"] = True
        elif key == "speaker_flow.crosstalk" and val is True:
            run["has_crosstalk"] = True
        elif key == "speaker_flow.bleed" and val is True:
            run["has_bleed"] = True
        elif key == "speaker_flow.unintelligible" and val is True:
            run["has_unintelligible"] = True
        elif key == "speaker_flow.discontinuity" and val is True:
            run["has_discontinuity"] = True
        elif key == "speaker_flow.payoff" and val is True:
            run["has_payoff"] = True
        elif key == "speaker_flow.sensitive" and val is True:
            run["has_sensitive_disclosure"] = True
        elif key == "speaker_flow.special_keywords" and isinstance(val, list):
            keywords.extend(str(x) for x in val)
    run["vernacular_flow_count"] = len([s for s in special_flows if s])
    run["special_keywords"] = sorted(set(keywords))[:40]
    run["special_speaker_flow_ids"] = sorted(s for s in special_flows if s)
    doc["generated_at"] = _now()
    return doc


def zones_from_facts(
    doc: dict[str, Any],
    flows_by_id: dict[str, dict[str, Any]],
    *,
    primary_language: str = "en",
) -> dict[str, Any]:
    zones: list[dict[str, Any]] = []
    keywords_by_flow: dict[str, list[str]] = {}
    spans_by_flow: dict[str, list[dict[str, int]]] = {}
    for f in doc.get("facts") or []:
        if not isinstance(f, dict) or f.get("status") != "asserted":
            continue
        sid = str(f.get("subject_id") or "")
        if f.get("key") == "speaker_flow.special_keywords" and isinstance(f.get("value"), list):
            keywords_by_flow[sid] = [str(x) for x in f["value"]]
        if f.get("key") == "speaker_flow.special_spans" and isinstance(f.get("value"), list):
            spans_by_flow[sid] = [x for x in f["value"] if isinstance(x, dict)]

    z_i = 0
    for f in doc.get("facts") or []:
        if not isinstance(f, dict):
            continue
        if f.get("key") != "speaker_flow.is_special" or f.get("value") is not True:
            continue
        if f.get("status") != "asserted":
            continue
        sid = str(f.get("subject_id") or "")
        flow = flows_by_id.get(sid) or {}
        z_i += 1
        spans = spans_by_flow.get(sid) or []
        if not spans:
            spans = [
                {
                    "start_ms": int(flow.get("start_ms") or 0),
                    "end_ms": int(flow.get("end_ms") or 0),
                }
            ]
        zones.append(
            {
                "zone_id": f"pz_{z_i:03d}",
                "speaker_flow_id": sid,
                "speaker_id": flow.get("speaker_id"),
                "start_ms": int(flow.get("start_ms") or 0),
                "end_ms": int(flow.get("end_ms") or 0),
                "protection_class": "vernacular_critical",
                "triggers": ["intra_flow_code_switch_or_uncommon"],
                "retention": "must_keep",
                "understanding_level": "gloss_uncertain",
                "source_text": flow.get("text") or "",
                "keywords": keywords_by_flow.get(sid) or [],
                "spans": spans,
                "segment_ids": [],
            }
        )
    return {
        "version": 1,
        "primary_language": primary_language,
        "master_language": primary_language,
        "doctrine": "inverse_confidence_vernacular",
        "automation": "annotate_and_continue",
        "scope": {
            "speakers": "all",
            "unit": "uninterrupted_speaker_flow",
            "special": ["any_non_primary_language", "uncommon_english"],
            "exclude_one_off_miscomprehension": True,
            "delivery": "full_master_only",
        },
        "zones": zones,
        "generated_at": _now(),
    }
