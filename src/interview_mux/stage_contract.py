"""Load per-stage artifact contracts from docs/cross-cutting/stage-contracts/."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

from interview_mux.config import merged_config, repo_root

Tier = Literal["llm_full", "deterministic", "gate", "process", "meta"]


@dataclass
class InputDep:
    path: str
    hard: bool = True
    producer: str | None = None
    min_chars: int | None = None
    when: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutputDep:
    path: str
    schema: str | None = None
    staging: bool = True


@dataclass
class SufficiencyRule:
    path: str
    rule: str
    blocking: str = "progression"
    min_length: int | None = None
    min_count: int | None = None
    when: dict[str, Any] = field(default_factory=dict)
    remediation: str = "micro_gap_fill"


@dataclass
class StageContract:
    stage_id: str
    tier: Tier = "process"
    lifecycle_phases: list[str] = field(default_factory=list)
    inputs: list[InputDep] = field(default_factory=list)
    outputs: list[OutputDep] = field(default_factory=list)
    sufficiency: list[SufficiencyRule] = field(default_factory=list)
    propagation: list[str] = field(default_factory=list)
    consumers: list[str] = field(default_factory=list)
    remediation: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def contracts_dir() -> Path:
    cfg = (merged_config().get("analysis") or {}).get("artifact_contract") or {}
    rel = cfg.get("contracts_dir") or "docs/cross-cutting/stage-contracts"
    return repo_root() / rel


def _parse_input(item: dict[str, Any], *, hard: bool) -> InputDep:
    return InputDep(
        path=str(item.get("path") or ""),
        hard=hard,
        producer=item.get("producer"),
        min_chars=item.get("min_chars"),
        when=dict(item.get("when") or {}),
    )


def _parse_contract(stage_id: str, raw: dict[str, Any]) -> StageContract:
    suff_raw = raw.get("sufficiency") or []
    sufficiency = [
        SufficiencyRule(
            path=str(s.get("path") or ""),
            rule=str(s.get("rule") or "present"),
            blocking=str(s.get("blocking") or "progression"),
            min_length=s.get("min_length"),
            min_count=s.get("min_count"),
            when=dict(s.get("when") or {}),
            remediation=str(s.get("remediation") or "micro_gap_fill"),
        )
        for s in suff_raw
        if isinstance(s, dict)
    ]
    inputs_raw = raw.get("inputs") or {}
    inputs: list[InputDep] = []
    if isinstance(inputs_raw, dict):
        for item in inputs_raw.get("hard") or []:
            if isinstance(item, dict):
                inputs.append(_parse_input(item, hard=True))
        for item in inputs_raw.get("soft") or []:
            if isinstance(item, dict):
                inputs.append(_parse_input(item, hard=False))
    outputs_raw = raw.get("outputs") or []
    outputs = [
        OutputDep(
            path=str(o.get("path") or ""),
            schema=o.get("schema"),
            staging=bool(o.get("staging", True)),
        )
        for o in outputs_raw
        if isinstance(o, dict)
    ]
    prop = raw.get("propagation") or {}
    invalidates = prop.get("invalidates_stages") if isinstance(prop, dict) else []
    return StageContract(
        stage_id=stage_id,
        tier=str(raw.get("tier") or "process"),  # type: ignore[arg-type]
        lifecycle_phases=list((raw.get("lifecycle") or {}).get("phases") or []),
        inputs=inputs,
        outputs=outputs,
        sufficiency=sufficiency,
        propagation=list(invalidates or []),
        consumers=list(raw.get("consumers") or []),
        remediation=list((raw.get("remediation") or {}).get("strategies") or []),
        raw=raw,
    )


@lru_cache(maxsize=128)
def load_contract(stage_id: str) -> StageContract | None:
    path = contracts_dir() / f"{stage_id}.yaml"
    if not path.is_file():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    return _parse_contract(stage_id, raw)


def all_contract_stage_ids() -> list[str]:
    root = contracts_dir()
    if not root.is_dir():
        return []
    return sorted(p.stem for p in root.glob("*.yaml") if not p.stem.startswith("_"))


def contract_for_artifact_path(rel: str) -> StageContract | None:
    for sid in all_contract_stage_ids():
        c = load_contract(sid)
        if not c:
            continue
        for out in c.outputs:
            if out.path == rel:
                return c
    return None


def evaluate_when(when: dict[str, Any], ctx: Any) -> bool:
    if not when:
        return True
    meta = {}
    if ctx and hasattr(ctx, "artifact_exists") and ctx.artifact_exists("run_meta.json"):
        try:
            meta = ctx.read_json("run_meta.json") or {}
        except Exception:
            meta = {}
    if "selected_flow" in when:
        if str(meta.get("selected_flow") or "") != str(when["selected_flow"]):
            return False
    if "spine_enabled" in when:
        from interview_mux.interview_spine.config import spine_enabled

        if bool(when["spine_enabled"]) != spine_enabled():
            return False
    if "interview_duration_ms_gte" in when:
        threshold = int(when["interview_duration_ms_gte"])
        dur = _interview_duration_ms(ctx)
        if dur < threshold:
            return False
    if "operator_verified" in when:
        verified = False
        if ctx and ctx.artifact_exists("understanding/analysis_state.json"):
            try:
                st = ctx.read_json("understanding/analysis_state.json")
                verified = bool((st.get("meta") or {}).get("operator_verified"))
            except Exception:
                verified = False
        if bool(when["operator_verified"]) != verified:
            return False
    if "production_style" in when:
        from interview_mux.production_profile import get_production_style

        if str(get_production_style(ctx)) != str(when["production_style"]):
            return False
    return True


def _interview_duration_ms(ctx: Any) -> int:
    if not ctx or not ctx.artifact_exists("transcript/full.json"):
        return 0
    try:
        doc = ctx.read_json("transcript/full.json")
        if isinstance(doc, dict):
            dur = doc.get("duration_ms") or doc.get("audio_duration_ms")
            if isinstance(dur, (int, float)):
                return int(dur)
            items = doc.get("items") or []
            if items and isinstance(items[-1], dict):
                end = items[-1].get("end_ms") or items[-1].get("end")
                if isinstance(end, (int, float)):
                    return int(end)
    except Exception:
        return 0
    return 0


__all__ = [
    "InputDep",
    "OutputDep",
    "StageContract",
    "SufficiencyRule",
    "all_contract_stage_ids",
    "contract_for_artifact_path",
    "contracts_dir",
    "evaluate_when",
    "load_contract",
]
