"""Finite adaptation loop guards for LLM stage retries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext


def adaptation_loop_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = (cfg or merged_config()).get("analysis") or {}
    defaults = {
        "max_decompose_per_stage_cycle": 1,
        "max_per_segment_shard_calls": 24,
        "max_micro_gap_fill_calls": 2,
        "max_same_adaptation_signature": 1,
        "halt_on_upstream_timeline_lint": True,
    }
    raw = analysis.get("adaptation_loop") or {}
    return {**defaults, **raw}


def _orch(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists("understanding/analysis_orchestration.json"):
        return {}
    doc = ctx.read_json("understanding/analysis_orchestration.json")
    return doc if isinstance(doc, dict) else {}


def _save_orch(ctx: RunContext, orch: dict[str, Any]) -> None:
    ctx.write_json("understanding/analysis_orchestration.json", orch, skip_handoff=True)


def adaptation_signature(strategy_key: str, **parts: Any) -> str:
    payload = {"strategy_key": strategy_key, **parts}
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class AdaptationLoopGuard:
    stage_key: str
    cfg: dict[str, Any] = field(default_factory=adaptation_loop_cfg)
    decompose_used: bool = False
    per_segment_shards_fired: int = 0
    micro_gap_calls: int = 0
    upstream_rerun_requested: bool = False
    adaptation_history: list[dict[str, Any]] = field(default_factory=list)
    _signature_counts: dict[str, int] = field(default_factory=dict)

    @classmethod
    def load(cls, ctx: RunContext, stage_key: str) -> AdaptationLoopGuard:
        orch = _orch(ctx)
        key = f"adaptation_guard_{stage_key}"
        raw = orch.get(key) or {}
        if not isinstance(raw, dict):
            raw = {}
        guard = cls(stage_key=stage_key)
        guard.decompose_used = bool(raw.get("decompose_used"))
        guard.per_segment_shards_fired = int(raw.get("per_segment_shards_fired") or 0)
        guard.micro_gap_calls = int(raw.get("micro_gap_calls") or 0)
        guard.upstream_rerun_requested = bool(raw.get("upstream_rerun_requested"))
        guard.adaptation_history = list(raw.get("adaptation_history") or [])
        guard._signature_counts = dict(raw.get("signature_counts") or {})
        return guard

    def save(self, ctx: RunContext) -> None:
        orch = _orch(ctx)
        key = f"adaptation_guard_{self.stage_key}"
        orch[key] = {
            "decompose_used": self.decompose_used,
            "per_segment_shards_fired": self.per_segment_shards_fired,
            "micro_gap_calls": self.micro_gap_calls,
            "upstream_rerun_requested": self.upstream_rerun_requested,
            "adaptation_history": self.adaptation_history[-12:],
            "signature_counts": self._signature_counts,
        }
        _save_orch(ctx, orch)

    def record_strategy(
        self,
        strategy_key: str,
        *,
        lint_errors: list[str] | None = None,
        missing_segment_ids: list[str] | None = None,
    ) -> bool:
        """Record strategy attempt. Returns False if same signature exceeded cap."""
        sig = adaptation_signature(
            strategy_key,
            missing=sorted(missing_segment_ids or [])[:8],
            lint=tuple((lint_errors or [])[:3]),
        )
        count = self._signature_counts.get(sig, 0) + 1
        self._signature_counts[sig] = count
        self.adaptation_history.append(
            {
                "strategy_key": strategy_key,
                "adaptation_signature": sig,
                "lint_errors": (lint_errors or [])[:4],
            }
        )
        max_same = int(self.cfg.get("max_same_adaptation_signature", 1))
        return count <= max_same

    def can_decompose(self) -> bool:
        if self.decompose_used:
            return False
        return True

    def mark_decompose(self, shard_count: int) -> bool:
        max_shards = int(self.cfg.get("max_per_segment_shard_calls", 24))
        if self.per_segment_shards_fired + shard_count > max_shards:
            return False
        self.decompose_used = True
        self.per_segment_shards_fired += shard_count
        return True

    def can_micro_gap_fill(self) -> bool:
        max_calls = int(self.cfg.get("max_micro_gap_fill_calls", 2))
        return self.micro_gap_calls < max_calls

    def mark_micro_gap_fill(self) -> None:
        self.micro_gap_calls += 1

    def is_exhausted(self) -> bool:
        if self.upstream_rerun_requested:
            return True
        max_same = int(self.cfg.get("max_same_adaptation_signature", 1))
        for count in self._signature_counts.values():
            if count > max_same:
                return True
        return False

    def request_upstream_rerun(self) -> None:
        self.upstream_rerun_requested = True
