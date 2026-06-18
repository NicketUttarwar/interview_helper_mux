"""Resume checkpoint for GUI E2E driver."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_STATE_NAME = "state.json"


@dataclass
class DriverState:
    run_id: str | None = None
    session_dir: str | None = None
    last_stage: str | None = None
    last_gate_cleared: str | None = None
    last_action: str | None = None
    fix_round: int = 0
    master_verified: bool = False
    started: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> DriverState:
        if not path.is_file():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            run_id=data.get("run_id"),
            session_dir=data.get("session_dir"),
            last_stage=data.get("last_stage"),
            last_gate_cleared=data.get("last_gate_cleared"),
            last_action=data.get("last_action"),
            fix_round=int(data.get("fix_round") or 0),
            master_verified=bool(data.get("master_verified")),
            started=bool(data.get("started")),
            extra=dict(data.get("extra") or {}),
        )


def default_state_path(campaign_dir: Path) -> Path:
    return campaign_dir / "driver" / _STATE_NAME
