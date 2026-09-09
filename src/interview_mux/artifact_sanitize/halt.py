"""sanitize_refused halt / identical-failure helpers."""

from __future__ import annotations

from typing import Any

DEFAULT_HALT_AFTER = 3

ERROR_PREFIX = "sanitize_refused:"


def sanitize_refused_message(artifact: str, errors: list[str] | None = None) -> str:
    art = str(artifact or "artifact").strip() or "artifact"
    detail = "; ".join((errors or ["unknown"])[:4])
    return f"{ERROR_PREFIX}{art}: {detail}"


def is_sanitize_refused(msg: str | BaseException | None) -> bool:
    text = str(msg or "").lower()
    return ERROR_PREFIX in text or "sanitize_refused" in text


def sanitize_refused_artifact(msg: str | BaseException | None) -> str:
    text = str(msg or "")
    if ERROR_PREFIX not in text:
        return ""
    rest = text.split(ERROR_PREFIX, 1)[1]
    return rest.split(":", 1)[0].strip()


def halt_after_for_sanitize(_artifact: str = "") -> int:
    try:
        from interview_mux.config import merged_config

        root = merged_config().get("artifact_sanitize") or {}
        if isinstance(root, dict) and root.get("halt_after") is not None:
            return max(1, int(root.get("halt_after")))
    except Exception:
        pass
    return DEFAULT_HALT_AFTER


def resume_stage_for_artifact(artifact: str) -> str:
    """Map artifact slug/rel to the thin sanitize stage id."""
    key = str(artifact or "").replace("\\", "/").lower()
    mapping = {
        "selection": "selection_order_sanitize",
        "master/selection.json": "selection_order_sanitize",
        "gap": "gap_report_sanitize",
        "gap_report": "gap_report_sanitize",
        "understanding/gap_report.json": "gap_report_sanitize",
        "air": "air_contract_sanitize",
        "air_contract": "air_contract_sanitize",
        "mastering/mastering_plan.json": "air_contract_sanitize",
        "omit": "air_contract_sanitize",
        "understanding/omit_ledger.json": "air_contract_sanitize",
        "layup": "nugget_layup_compose",
        "understanding/nugget_layup_plan.json": "nugget_layup_compose",
        "transitions": "transitions",
        "master/transitions.json": "transitions",
        "vo": "vo_synthesize",
        "vo_synthesize": "vo_synthesize",
        "mastering/vo_synthesize.json": "vo_synthesize",
        "synthesis_report": "vo_synthesize",
        "vo_pickup/synthesis_report.json": "vo_synthesize",
        "edl": "edl",
        "master/edl.json": "edl",
        "sdp": "sound_design_plan",
        "sound_design_plan": "sound_design_plan",
        "understanding/sound_design_plan.json": "sound_design_plan",
    }
    return mapping.get(key, key if key else "selection_order_sanitize")
